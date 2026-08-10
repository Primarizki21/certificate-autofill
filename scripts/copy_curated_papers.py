"""
Copy curated papers from papers/ to input_marker_paper/ for Marker processing.
Maintains folder structure: group_X/X1__*
"""

CURATED = [
    # ── Group A: LLM Document Extraction (10 core + 5 exploratory) ──
    "2304.12484",   # DocParser: OCR-free IE
    "2304.14936",   # Redundancy & Biases in KIE Benchmarks
    "2305.03253",   # VicunaNER: Zero/Few-shot NER
    "2305.14450",   # Empirical Study on IE using LLMs
    "2308.09341",   # Document Automation Architectures Survey
    "2309.05429",   # Improving IE on Business Documents
    "2309.10952",   # LMDX: LM-based Document IE
    "2403.13369",   # Clinical IE for Low-resource
    "2505.17125",   # NEXT-EVAL
    "2509.22906",   # Extract-0: Specialized LM for IE
    # A exploratory
    "2402.10612",   # Rowen: Adaptive RAG
    "2502.11306",   # Smoothed Knowledge Distillation
    "2505.13535",   # IE from VRDs using LLM
    "2508.14314",   # Zero-knowledge LLM Hallucination Detection
    "2509.08381",   # Low-Resource Fine-Tuning 1B

    # ── Group B: Hybrid Rule-Based + ML (10) ──
    "2305.00795",   # SelfDocSeg
    "2306.00526",   # Layout-Aware Prompt for DocVQA
    "2308.07777",   # GraphLayoutLM
    "2309.05429",   # (cross-ref A)
    "2404.01462",   # OpenChemIE
    "2404.05225",   # LayoutLLM
    "2406.05348",   # Toward Reliable Scientific IE
    "2509.08381",   # (cross-ref A)
    "2512.13031",   # Comprehensive Eval Rule vs ML vs DL
    "2305.14450",   # (cross-ref A)

    # ── Group C: Confidence Calibration (10) ──
    "2305.14975",   # Just Ask for Calibration
    "2311.12436",   # ROC-Regularized Isotonic Regression
    "2401.13744",   # Conformal Prediction Sets
    "2406.02354",   # Label-wise Aleatoric & Epistemic
    "2406.05348",   # (cross-ref B)
    "2410.01609",   # SynJAC
    "2410.06615",   # QA-Calibration
    "2412.14737",   # Verbalized Confidence Scores
    "2604.09529",   # VL-Calibration
    "2305.14450",   # (cross-ref A)

    # ── Group D: Document Image Preprocessing (10) ──
    "2304.12484",   # (cross-ref A)
    "2307.12571",   # MataDoc: Margin-Aware Dewarping
    "2309.05429",   # (cross-ref A)
    "2309.05503",   # Long-Range Transformer
    "2312.07925",   # Polar-Doc: One-Stage Dewarping
    "2403.07553",   # GPT + Donut for Document Indexing
    "2505.20429",   # PreP-OCR Pipeline
    "2508.06988",   # TADoc: Time-Aware Dewarping
    "2508.14557",   # Internal Document Redundancy OCR
    "2508.21693",   # Line-Level OCR
    "2306.10046",   # Document Layout Annotation

    # ── Group E: Evaluation Framework (10) ──
    "2305.14450",   # (cross-ref A)
    "2310.03668",   # GoLLIE: Annotation Guidelines
    "2404.01462",   # (cross-ref B)
    "2404.19329",   # End-to-end IE Handwritten Docs
    "2406.05348",   # (cross-ref B)
    "2502.16377",   # Instruction-Tuning LLMs with Guidelines
    "2503.05488",   # KIEval
    "2504.02871",   # Synthesized Annotation Guidelines
    "2505.17125",   # (cross-ref A)
    "2510.12835",   # Repurposing Annotation Guidelines

    # ── Group F: Feedback Loop & Active Learning (5) ──
    "2302.08893",   # Active Learning for Data Streams
    "2305.00795",   # (cross-ref B)
    "2308.04332",   # RLHF-Blender
    "2309.05429",   # (cross-ref A)
    "2306.10046",   # (cross-ref D)

    # ── Group G: Model Distillation & Deployment (12) ──
    "2311.00502",   # Efficient LLM Inference on CPUs
    "2311.08883",   # Distilling Rule-based into LLMs
    "2402.10517",   # Any-Precision LLM
    "2405.17533",   # PAE: Product Attribute Extraction
    "2411.16313",   # CATP-LLM: Cost-Aware Planning
    "2501.00031",   # Distilling LLMs for Clinical IE
    "2504.13359",   # Cost-of-Pass Framework
    "2505.06461",   # CPUs Outperform GPUs
    "2507.01806",   # LoRA Fine-Tuning Without GPUs
    "2509.18101",   # Cost-Benefit On-Premise vs Commercial
    "2602.06370",   # Cost-Aware Model Selection
    "2607.07052",   # Progressive Crystallization

    # ── Group H: Layout-Aware Extraction (10) ──
    "2305.00795",   # (cross-ref B)
    "2309.05429",   # (cross-ref A)
    "2309.05503",   # (cross-ref D)
    "2403.07553",   # (cross-ref D)
    "2404.05225",   # (cross-ref B)
    "2404.10848",   # LayoutLMv3 for Relation Extraction
    "2406.06236",   # UnSupDLA
    "2410.21169",   # Document Parsing Survey
    "2501.05497",   # Spatial Info in Small LMs
    "2509.11720",   # Docling Layout Analysis (RT-DETR)

    # ── Group I: Production Architecture (8) ──
    "2302.14017",   # Full Stack Optimization Survey
    "2403.02310",   # Sarathi-Serve
    "2405.12311",   # SpotKube
    "2412.04504",   # Multi-Bin Batching
    "2412.18934",   # Dovetail: CPU/GPU Speculative Decoding
    "2502.12017",   # Serverless ML Inference
    "2505.06461",   # (cross-ref G)
    "2601.22362",   # Efficiency: Quantization, Batching
]

import os
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE / "papers"
OUTPUT_DIR = BASE / "input_marker_paper"


def main():
    curated_set = set(CURATED)
    found = {}
    missing = []

    for group_dir in sorted(PAPERS_DIR.iterdir()):
        if not group_dir.is_dir():
            continue
        for sub_dir in sorted(group_dir.iterdir()):
            if not sub_dir.is_dir():
                continue
            for pdf_file in sub_dir.iterdir():
                if not pdf_file.name.endswith(".pdf"):
                    continue
                arxiv_id = pdf_file.stem
                if arxiv_id in curated_set:
                    found[arxiv_id] = {
                        "src": pdf_file,
                        "group": group_dir.name,
                        "sub": sub_dir.name,
                    }

    # Check which curated IDs have no PDF
    for arxiv_id in sorted(curated_set):
        if arxiv_id not in found:
            missing.append(arxiv_id)

    # Copy found PDFs
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    copied = 0
    for arxiv_id, info in sorted(found.items()):
        target_dir = OUTPUT_DIR / info["group"] / info["sub"]
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(info["src"], target_dir / info["src"].name)
        copied += 1

    # Report
    print(f"Kurasi: {len(curated_set)} ArXiv ID unik (termasuk {len(curated_set) - copied} cross-ref duplikat)")
    print(f"PDF ditemukan & di-copy: {copied} ke {OUTPUT_DIR}")

    total_unique_physical = len({i for i in curated_set if i in found})
    print(f"PDF unik (tanpa cross-ref): {total_unique_physical}")

    if missing:
        print(f"\nPeringatan: ID berikut ada di kurasi tapi tidak ditemukan PDF-nya:")
        pretty_ids = "\n  ".join(missing)
        print(f"  {pretty_ids}")
    else:
        print("\nSemua paper kurasi punya PDF!")

    print(f"\nFolder output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
