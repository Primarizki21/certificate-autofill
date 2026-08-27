"""Worker TrOCR (encoder-decoder transformer) + RapidOCR detection.

OCR-011 TrOCR recognition + RapidOCR PP-OCR detection (bukan end-to-end —
TrOCR TIDAK punya detection sendiri). Setiap halaman:
  1. RapidOCR detect-only → bounding boxes (PP-OCR detection ONNX, cepat ~0.3s).
  2. Crop setiap box dari page PNG.
  3. Batch TrOCR (microsoft/trocr-base-printed, 333M) → recognition.
  4. Gabung teks per box sesuai urutan y.

Dipanggil sebagai subprocess oleh benchmark_trocr_probe.py.
"""

import argparse
import json
import os
import sys
import time
import numpy as np
from PIL import Image


def _detect_boxes(rapid, img_path: str) -> list:
    """RapidOCR detect → list of (box_coords, crop_pil)."""
    img = Image.open(img_path).convert("RGB")
    img_np = np.array(img)
    result, _ = rapid(img_np)
    crops = []
    if not result:
        return crops
    for line in result:
        box, text, score = line
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x0, x1 = max(0, int(min(xs))), min(img.width, int(max(xs)))
        y0, y1 = max(0, int(min(ys))), min(img.height, int(max(ys)))
        if x1 > x0 and y1 > y0:
            crop = img.crop((x0, y0, x1, y1))
            crops.append({"box": box, "crop": crop, "y_center": (y0 + y1) / 2})
    crops.sort(key=lambda c: c["y_center"])
    return crops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages-json", required=True)
    ap.add_argument("--model-name", default="microsoft/trocr-base-printed")
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    from rapidocr_onnxruntime import RapidOCR

    t0 = time.time()
    rapid = RapidOCR()
    print(f"[worker] RapidOCR loaded {time.time() - t0:.1f}s", flush=True)

    t1 = time.time()
    # use_fast=False: bypass tokenizer auto-conversion di transformers >=5.x
    processor = TrOCRProcessor.from_pretrained(args.model_name, use_fast=False)
    model = VisionEncoderDecoderModel.from_pretrained(args.model_name)
    model = model.eval()
    if torch.cuda.is_available():
        model = model.to("cuda")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[worker] TrOCR loaded {time.time() - t1:.1f}s (device={device})", flush=True)

    jobs = json.load(open(args.pages_json))
    for j in jobs:
        t2 = time.time()
        crops = _detect_boxes(rapid, j["png"])

        texts = []
        for i in range(0, len(crops), args.batch_size):
            batch_crops = [c["crop"] for c in crops[i:i + args.batch_size]]
            pixel_values = processor(images=batch_crops, return_tensors="pt").pixel_values
            pixel_values = pixel_values.to(device)
            with torch.no_grad():
                generated = model.generate(pixel_values, max_new_tokens=128)
            decoded = processor.batch_decode(generated, skip_special_tokens=True)
            texts.extend(decoded)

        dt = time.time() - t2
        body = "\n".join(t.strip() for t in texts if t.strip())
        with open(j["out"], "w") as fh:
            fh.write(f"# Engine: trocr-base-printed\n# Seconds: {dt:.2f}\n# Regions: {len(crops)}\n\n{body}\n")
        print(f"[worker] {os.path.basename(j['out'])} {dt:.1f}s {len(crops)} regions {len(body)} chars", flush=True)


if __name__ == "__main__":
    main()
