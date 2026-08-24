"""Worker GOT-OCR 2.0 — dipanggil sebagai SUBPROCESS oleh benchmark_got_probe.

Load model SEKALI per invokasi lalu proses banyak halaman (chunk) supaya biaya
load (~20-60s) tidak dibayar per halaman. Parent yang mengatur watchdog
RSS/VRAM; worker ini mati dibunuh -> parent resume dari txt yang sudah ada.

Run langsung (debug):
  uv run python tests/got_worker.py --pages-json <file.json> \
      --model-dir ~/.cache/got20/hf --ocr-type ocr
  # pages-json: [{"png": "<abs path>", "out": "<abs path .txt>"}, ...]
"""

import argparse
import json
import os
import sys
import time


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages-json", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--ocr-type", default="ocr",
                    help="ocr | ocr-2 (two-stage) | format; default 'ocr'")
    args = ap.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import torch
    from transformers import AutoModel, AutoTokenizer

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
    # Tanpa device_map (menghindari dependensi accelerate): load CPU lalu .to("cuda").
    kw_new = dict(trust_remote_code=True, dtype=torch.float16,
                  low_cpu_mem_usage=True, pad_token_id=tok.eos_token_id)
    kw_old = dict(trust_remote_code=True, torch_dtype=torch.float16,
                  low_cpu_mem_usage=True, pad_token_id=tok.eos_token_id)
    try:
        model = AutoModel.from_pretrained(args.model_dir, **kw_new)
    except TypeError:
        model = AutoModel.from_pretrained(args.model_dir, **kw_old)
    model = model.to("cuda").eval()
    print(f"[worker] model loaded {time.time() - t0:.1f}s "
          f"(cuda={torch.cuda.is_available()})", flush=True)

    jobs = json.load(open(args.pages_json))
    for j in jobs:
        t1 = time.time()
        res = model.chat(tok, j["png"], ocr_type=args.ocr_type) or ""
        dt = time.time() - t1
        body = str(res).strip()
        with open(j["out"], "w") as fh:
            fh.write(f"# Engine: got-ocr2-{args.ocr_type}\n# Seconds: {dt:.2f}\n\n{body}\n")
        print(f"[worker] {os.path.basename(j['out'])} {dt:.1f}s {len(body)} chars", flush=True)


if __name__ == "__main__":
    main()
