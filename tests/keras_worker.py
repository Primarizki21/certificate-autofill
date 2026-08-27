"""Worker Keras-OCR (CRAFT detection + CRNN recognition).

OCR-012 (goal user: "coba banyak engine selain LFM").
End-to-end: Keras-OCR menangani detection + recognition dalam satu pipeline.
Model: CRAFT (detection) + CRNN (recognition), ~120MB total.
TensorFlow-based — berjalan di venv terpisah ~/.cache/keras_ocr/venv.

Dipanggil sebagai subprocess oleh benchmark_keras_probe.py.
"""

import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages-json", required=True)
    args = ap.parse_args()

    import keras_ocr

    t0 = time.time()
    pipeline = keras_ocr.pipeline.Pipeline()
    print(f"[worker] Keras-OCR pipeline loaded {time.time() - t0:.1f}s", flush=True)

    jobs = json.load(open(args.pages_json))
    for j in jobs:
        t1 = time.time()
        image = keras_ocr.tools.read(j["png"])
        predictions = pipeline.recognize([image])[0]

        # predictions = list of (box, text) tuples, sorted by position
        # Sort by y-center for reading order
        def y_center(item):
            box = item[0]
            return (box[0][1] + box[2][1]) / 2
        predictions.sort(key=y_center)

        dt = time.time() - t1
        body = "\n".join(text for _, text in predictions if text.strip())
        with open(j["out"], "w") as fh:
            fh.write(f"# Engine: keras-ocr\n# Seconds: {dt:.2f}\n# Regions: {len(predictions)}\n\n{body}\n")
        print(f"[worker] {os.path.basename(j['out'])} {dt:.1f}s {len(predictions)} regions {len(body)} chars", flush=True)


if __name__ == "__main__":
    main()
