"""Benchmark Runner: Evaluasi Komparatif Prompt V2 Baseline vs Candidate (EXP-ALL6F-PROMPT-007).

Membandingkan Varian Kontrol (V2 Scope-Aware 7-field + legacy rule mapper)
terhadap Varian Kandidat (V2 Scope-Aware 8-field dengan enum jenis_penyelenggara langsung dari LLM)
dan Safety Net Offline (Combined v4.2 + upgraded map_jenis_penyelenggara)
pada 104 sertifikat terpadu (certs_unified) menggunakan model gemini-3.1-flash-lite.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.master_data import FORM_OPTIONS
from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form, map_jenis_penyelenggara
from tests.gemini_client import GeminiClient, load_google_api_key
from tests.matchers import match_field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("benchmark_prompt_jp")

EXP_ID = "EXP-ALL6F-PROMPT-007"
DEFAULT_MODEL = "gemini-3.1-flash-lite"
GT_UNIFIED_CSV = "Ground_Truth_Unified_AUCC.csv"

KHP_6_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
]

ALL_7_FIELDS = KHP_6_FIELDS + ["jenis_penyelenggara"]

FIELD_GT_COLUMNS = {
    "nama_kegiatan_sertifikasi": "Nama Kegiatan Sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi": "Nomor Bukti Fisik Nomor Sertifikasi",
    "penyelenggara_kegiatan": "Penyelenggara Kegiatan",
    "waktu_mulai_pelaksanaan": "Waktu Mulai Pelaksanaan",
    "waktu_selesai_pelaksanaan": "Waktu Selesai Pelaksanaan",
    "tingkat": "Tingkat",
    "jenis_penyelenggara": "Jenis Penyelenggara",
}

VALID_TINGKAT_OPTIONS = tuple(FORM_OPTIONS.get("tingkat", [
    "Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"
]))

VALID_JP_OPTIONS = tuple(FORM_OPTIONS.get("jenis_penyelenggara", [
    "PTN di Indonesia", "PTS di Indonesia", "PT di luar negeri", "Kementerian Negara", "BUMN", "Lembaga/Yayasan lain"
]))

# --- VARIAN 1: V2 CONTROL (Scope-Aware 7-Field) ---
V2_CONTROL_SYSTEM = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama.
   - Jika tidak ada tanggal, isi null.
3. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Jika tidak ada nomor, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
5. Tingkat (tingkat):
   - Wajib salah satu nilai enum berikut persis:
     ["Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"]
   - Prinsip Utama: Cakupan Sasaran Peserta (Skala Nasional/Internasional) LEBIH UTAMA daripada Jenjang Penyelenggara.
   - Pedoman:
     * Lomba, kompetisi, hackathon, seminar, call for papers, atau event terbuka untuk mahasiswa umum lintas perguruan tinggi/nasional -> "Nasional" (MESKIPUN diselenggarakan oleh BEM Fakultas atau Himpunan Mahasiswa Departemen).
     * Konferensi, symposium, atau event berskala global/lintas negara -> "Internasional".
     * Kegiatan internal kemahasiswaan/organisasi kampus non-lomba terbuka, tentukan berdasarkan hierarki unit:
       - Rektorat / BEM Universitas / Direktorat Kemahasiswaan Universitas -> "Universitas".
       - Kepengurusan, raker, atau kepanitiaan BEM Fakultas / ormawa fakultas -> "Fakultas".
       - Kepengurusan, raker, atau kepanitiaan Himpunan Mahasiswa / Program Studi -> "Departemen/Program Studi".
       - UKM / Unit Kegiatan Mahasiswa / BSO -> "Lainnya".
     * Jika tidak diketahui atau bukti tidak cukup untuk memastikan cakupan -> "Lainnya".
6. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
"""

V2_CONTROL_USER = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 7 field berikut dalam format JSON:
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya" atau null,
  "raw_role": string atau null
}}
"""

# --- VARIAN 2: V2 CANDIDATE (Scope-Aware 8-Field with Jenis Penyelenggara Enum) ---
V2_CANDIDATE_SYSTEM = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama.
   - Jika tidak ada tanggal, isi null.
3. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Jika tidak ada nomor, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
5. Tingkat (tingkat):
   - Wajib salah satu nilai enum berikut persis:
     ["Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"]
   - Prinsip Utama: Cakupan Sasaran Peserta (Skala Nasional/Internasional) LEBIH UTAMA daripada Jenjang Penyelenggara.
   - Pedoman:
     * Lomba, kompetisi, hackathon, seminar, call for papers, atau event terbuka untuk mahasiswa umum lintas perguruan tinggi/nasional -> "Nasional" (MESKIPUN diselenggarakan oleh BEM Fakultas atau Himpunan Mahasiswa Departemen).
     * Konferensi, symposium, atau event berskala global/lintas negara -> "Internasional".
     * Kegiatan internal kemahasiswaan/organisasi kampus non-lomba terbuka, tentukan berdasarkan hierarki unit:
       - Rektorat / BEM Universitas / Direktorat Kemahasiswaan Universitas -> "Universitas".
       - Kepengurusan, raker, atau kepanitiaan BEM Fakultas / ormawa fakultas -> "Fakultas".
       - Kepengurusan, raker, atau kepanitiaan Himpunan Mahasiswa / Program Studi -> "Departemen/Program Studi".
       - UKM / Unit Kegiatan Mahasiswa / BSO -> "Lainnya".
     * Jika tidak diketahui atau bukti tidak cukup untuk memastikan cakupan -> "Lainnya".
6. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
7. Jenis Penyelenggara (jenis_penyelenggara):
   - Wajib salah satu nilai enum master berikut persis:
     ["PTN di Indonesia", "PTS di Indonesia", "PT di luar negeri", "Kementerian Negara", "BUMN", "Lembaga/Yayasan lain"]
   - Pedoman Klasifikasi:
     * "PTN di Indonesia": Perguruan Tinggi Negeri di Indonesia (termasuk fakultas, departemen, prodi, laboratorium, BEM, HIMA, UKM di bawahnya seperti UNAIR, UI, UGM, ITB, ITS, UB, IPB, UNS, UNHAS, USU, UNSRI, USK, UNESA, UNY, dll.) serta perguruan tinggi kedinasan negeri (misal PKN STAN, Polstat STIS).
     * "PTS di Indonesia": Perguruan Tinggi Swasta di Indonesia (termasuk fakultas, departemen, prodi, BEM, HIMA di bawahnya seperti Telkom University / IT Telkom, Universitas Islam Bandung / Unisba, Universitas Islam Kalimantan / Uniska, Universitas Pelita Harapan / UPH, Universitas Kristen Satya Wacana / UKSW, Universitas Muhammadiyah Semarang / UNIMUS, Politeknik Caltex Riau, dsb.).
     * "PT di luar negeri": Perguruan tinggi atau universitas di luar wilayah Indonesia (misal University of Tennessee, National University of Singapore, dsb.).
     * "Kementerian Negara": Lembaga kementerian atau Lembaga Pemerintah Non-Kementerian (LPNK) resmi Republik Indonesia (misal Kemendiktisaintek, Kemkominfo, Kemenkeu). Catatan: kementerian internal BEM mahasiswa tetap dikategorikan sebagai PTN/PTS tempat BEM bernaung.
     * "BUMN": Badan Usaha Milik Negara Republik Indonesia (Pertamina, PLN, Bank Mandiri, Telkom Indonesia, BRI, dsb.).
     * "Lembaga/Yayasan lain": Organisasi nirlaba, yayasan, asosiasi profesi luar kampus, startup, platform edukasi, atau komunitas swasta (misal AIESEC, Literasi Psikologi Indonesia, Institut français d'Indonésie, Dicoding, dsb.).
     * Jika tidak dapat dipastikan, gunakan "Lembaga/Yayasan lain".
"""

V2_CANDIDATE_USER = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 8 field berikut dalam format JSON:
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "jenis_penyelenggara": "PTN di Indonesia"|"PTS di Indonesia"|"PT di luar negeri"|"Kementerian Negara"|"BUMN"|"Lembaga/Yayasan lain" atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya" atau null,
  "raw_role": string atau null
}}
"""

VARIANTS = {
    "V1_CONTROL_7F": {
        "label": "Prompt V2 Scope-Aware 7-Field (Baseline Kontrol + Legacy Rule Mapper)",
        "prompt_type": "control_7f",
    },
    "V2_CANDIDATE_8F": {
        "label": "Prompt V2 Scope-Aware 8-Field (Kandidat: End-to-End LLM Jenis Penyelenggara)",
        "prompt_type": "candidate_8f",
    },
    "V3_OFFLINE_SAFETYNET": {
        "label": "Combined v4.2 Offline Safety-Net (Upgraded Rule Mapper)",
        "prompt_type": "offline_rule",
    },
}


def load_raw_text(stem: str, fname: str) -> str:
    candidates = [
        Path(f"docs/experiments/EXP-INDRA-LLM-001/raw_ocr/{stem}.txt"),
        Path(f"docs/experiments/EXP-OCR-INDRA-001/raw_ocr/indra/{stem}.txt"),
        Path(f"docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts/{stem}.txt"),
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8")

    for f_dir in ["certs_unified", "certs_test", "Sertifikat_Ground_Truth"]:
        pdf_path = Path(f_dir) / fname
        if pdf_path.exists():
            import fitz
            doc = fitz.open(pdf_path)
            return " ".join(page.get_text() for page in doc)
    return ""


def clean_json_markdown(text: str) -> str:
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if match:
        return match.group(1).strip()
    return stripped


def normalize_parsed_output(parsed: dict[str, Any] | None) -> dict[str, str | None]:
    out: dict[str, str | None] = {fld: None for fld in ALL_7_FIELDS}
    out["raw_role"] = None
    if not parsed or not isinstance(parsed, dict):
        return out

    for k in ("nama_kegiatan_sertifikasi", "nomor_bukti_fisik_nomor_sertifikasi", "penyelenggara_kegiatan", "raw_role"):
        val = parsed.get(k)
        if val is not None and isinstance(val, str):
            s = val.strip()
            if s and s.lower() not in ("null", "none", "-", ""):
                out[k] = s

    for k in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        val = parsed.get(k)
        if val and isinstance(val, str):
            s = val.strip()
            if s and s.lower() not in ("null", "none", "-", ""):
                out[k] = s

    t_raw = parsed.get("tingkat")
    if t_raw and isinstance(t_raw, str):
        t_clean = t_raw.strip()
        matched = next((opt for opt in VALID_TINGKAT_OPTIONS if opt.lower() == t_clean.lower()), None)
        out["tingkat"] = matched or "Lainnya"

    jp_raw = parsed.get("jenis_penyelenggara")
    if jp_raw and isinstance(jp_raw, str):
        jp_clean = jp_raw.strip()
        if jp_clean and jp_clean.lower() not in ("null", "none", "-", ""):
            matched_jp = next((opt for opt in VALID_JP_OPTIONS if opt.lower() == jp_clean.lower()), None)
            if matched_jp:
                out["jenis_penyelenggara"] = matched_jp
            else:
                low = jp_clean.lower()
                if "luar negeri" in low or "foreign" in low or "overseas" in low:
                    out["jenis_penyelenggara"] = "PT di luar negeri"
                elif "ptn" in low or "negeri" in low:
                    out["jenis_penyelenggara"] = "PTN di Indonesia"
                elif "pts" in low or "swasta" in low:
                    out["jenis_penyelenggara"] = "PTS di Indonesia"
                elif "kementerian" in low or "ministry" in low:
                    out["jenis_penyelenggara"] = "Kementerian Negara"
                elif "bumn" in low or "state-owned" in low:
                    out["jenis_penyelenggara"] = "BUMN"
                else:
                    out["jenis_penyelenggara"] = "Lembaga/Yayasan lain"

    return out


def evaluate_single(pred: dict[str, str | None], gt: dict[str, str]) -> dict[str, Any]:
    eval_res = {}
    for fld in ALL_7_FIELDS:
        gt_col = FIELD_GT_COLUMNS[fld]
        expected = str(gt.get(gt_col) or "").strip()
        actual = pred.get(fld)

        if fld == "jenis_penyelenggara":
            exp_norm = expected.strip().lower()
            act_norm = str(actual or "").strip().lower()
            exact = bool(exp_norm and exp_norm == act_norm)
            eval_res[fld] = {
                "expected": expected,
                "actual": actual,
                "exact": exact,
                "fuzzy": exact,
                "match_type": "EXACT" if exact else "MISMATCH",
            }
            continue

        if not expected or expected in ("-", "--", "—", "null", "none"):
            is_none_match = actual is None or str(actual).strip() in ("", "-", "None")
            eval_res[fld] = {
                "expected": expected,
                "actual": actual,
                "exact": is_none_match,
                "fuzzy": is_none_match,
                "match_type": "EXACT" if is_none_match else "MISMATCH",
            }
            continue

        m = match_field(expected, actual, fld)
        eval_res[fld] = {
            "expected": expected,
            "actual": actual,
            "exact": bool(m.get("exact")),
            "fuzzy": bool(m.get("fuzzy")),
            "match_type": "EXACT" if m.get("exact") else ("FUZZY" if m.get("fuzzy") else "MISMATCH"),
        }
    return eval_res


def run_benchmark(
    out_dir: Path,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "llm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    api_key = load_google_api_key()
    client = GeminiClient(api_key=api_key)

    gt_path = Path(GT_UNIFIED_CSV)
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    with open(gt_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_gt = list(reader)

    if limit is not None and limit > 0:
        all_gt = all_gt[:limit]

    print("=" * 85)
    print(f"BENCHMARK PROMPT EXP-ALL6F-PROMPT-007 (MODEL: {model})")
    print(f"Total Dokumen: {len(all_gt)} | Varian: {len(VARIANTS)}")
    print("=" * 85)

    results_by_variant = {}
    detailed_rows = []

    for v_key, v_info in VARIANTS.items():
        print(f"\nMenjalankan [{v_key}] — {v_info['label']}...")
        v_cache_dir = cache_dir / v_key
        v_cache_dir.mkdir(parents=True, exist_ok=True)

        eval_list = []
        lats = []
        prompt_tok_list = []
        cand_tok_list = []
        total_tok_list = []
        cost_usd_list = []
        cost_idr_list = []

        for idx, gt_row in enumerate(all_gt, start=1):
            fname = gt_row["Nama File"]
            stem = os.path.splitext(fname)[0]
            raw_text = load_raw_text(stem, fname)

            pred_fields = {}
            call_res = None

            if v_info["prompt_type"] == "control_7f":
                c_file = v_cache_dir / f"{stem}.json"
                if c_file.exists():
                    saved = json.loads(c_file.read_text(encoding="utf-8"))
                    pred_fields = saved["extracted"]
                    call_meta = saved.get("meta", {})
                    lats.append(call_meta.get("latency_s", 0.0))
                    prompt_tok_list.append(call_meta.get("prompt_tokens", 0))
                    cand_tok_list.append(call_meta.get("candidates_tokens", 0))
                    total_tok_list.append(call_meta.get("total_tokens", 0))
                    cost_usd_list.append(call_meta.get("cost_usd", 0.0))
                    cost_idr_list.append(call_meta.get("cost_idr", 0.0))
                else:
                    prompt = V2_CONTROL_USER.format(raw_ocr_text=raw_text)
                    t0 = time.perf_counter()
                    call_res = client.generate_json(
                        prompt=prompt,
                        system_instruction=V2_CONTROL_SYSTEM,
                        model=model,
                        temperature=0.0,
                    )
                    lat = time.perf_counter() - t0
                    norm = normalize_parsed_output(call_res.parsed_json)
                    # Legacy rule mapper determination for jenis_penyelenggara
                    pred_jp = map_jenis_penyelenggara(raw_text.upper(), norm.get("tingkat"))
                    norm["jenis_penyelenggara"] = pred_jp
                    pred_fields = norm

                    lats.append(lat)
                    prompt_tok_list.append(call_res.prompt_tokens)
                    cand_tok_list.append(call_res.candidates_tokens)
                    total_tok_list.append(call_res.total_tokens)
                    cost_usd_list.append(call_res.cost_usd)
                    cost_idr_list.append(call_res.cost_idr)

                    c_file.write_text(json.dumps({
                        "stem": stem,
                        "variant": v_key,
                        "extracted": pred_fields,
                        "meta": call_res.to_dict() if call_res else {},
                    }, indent=2), encoding="utf-8")

            elif v_info["prompt_type"] == "candidate_8f":
                c_file = v_cache_dir / f"{stem}.json"
                if c_file.exists():
                    saved = json.loads(c_file.read_text(encoding="utf-8"))
                    pred_fields = saved["extracted"]
                    call_meta = saved.get("meta", {})
                    lats.append(call_meta.get("latency_s", 0.0))
                    prompt_tok_list.append(call_meta.get("prompt_tokens", 0))
                    cand_tok_list.append(call_meta.get("candidates_tokens", 0))
                    total_tok_list.append(call_meta.get("total_tokens", 0))
                    cost_usd_list.append(call_meta.get("cost_usd", 0.0))
                    cost_idr_list.append(call_meta.get("cost_idr", 0.0))
                else:
                    prompt = V2_CANDIDATE_USER.format(raw_ocr_text=raw_text)
                    t0 = time.perf_counter()
                    call_res = client.generate_json(
                        prompt=prompt,
                        system_instruction=V2_CANDIDATE_SYSTEM,
                        model=model,
                        temperature=0.0,
                    )
                    lat = time.perf_counter() - t0
                    norm = normalize_parsed_output(call_res.parsed_json)
                    pred_fields = norm

                    lats.append(lat)
                    prompt_tok_list.append(call_res.prompt_tokens)
                    cand_tok_list.append(call_res.candidates_tokens)
                    total_tok_list.append(call_res.total_tokens)
                    cost_usd_list.append(call_res.cost_usd)
                    cost_idr_list.append(call_res.cost_idr)

                    c_file.write_text(json.dumps({
                        "stem": stem,
                        "variant": v_key,
                        "extracted": pred_fields,
                        "meta": call_res.to_dict() if call_res else {},
                    }, indent=2), encoding="utf-8")

            elif v_info["prompt_type"] == "offline_rule":
                t0 = time.perf_counter()
                f_raw = extract_certificate_fields(raw_text)
                combined = apply_combined_v4_2(f_raw, raw_text)
                mapped = map_fields_to_form(combined, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
                lat = time.perf_counter() - t0

                pred_fields = {fld: getattr(mapped.get(fld), "value", None) for fld in ALL_7_FIELDS}
                lats.append(lat)
                prompt_tok_list.append(0)
                cand_tok_list.append(0)
                total_tok_list.append(0)
                cost_usd_list.append(0.0)
                cost_idr_list.append(0.0)

            # Evaluate against Ground Truth
            single_eval = evaluate_single(pred_fields, gt_row)
            eval_list.append(single_eval)

            for fld in ALL_7_FIELDS:
                detailed_rows.append({
                    "variant": v_key,
                    "stem": stem,
                    "field": fld,
                    "expected": single_eval[fld]["expected"],
                    "actual": single_eval[fld]["actual"],
                    "exact": single_eval[fld]["exact"],
                    "fuzzy": single_eval[fld]["fuzzy"],
                    "match_type": single_eval[fld]["match_type"],
                    "latency_s": round(lats[-1], 4),
                })

            if idx % 20 == 0 or idx == len(all_gt):
                print(f"  Processed {idx}/{len(all_gt)} dokumen...")

        # Aggregate metrics
        n_docs = len(eval_list)
        per_field = {}
        for fld in ALL_7_FIELDS:
            exact_cnt = sum(1 for e in eval_list if e[fld]["exact"])
            fuzzy_cnt = sum(1 for e in eval_list if e[fld]["fuzzy"])
            per_field[fld] = {
                "exact_count": exact_cnt,
                "exact_pct": round((exact_cnt / n_docs) * 100, 2),
                "fuzzy_count": fuzzy_cnt,
                "fuzzy_pct": round((fuzzy_cnt / n_docs) * 100, 2),
            }

        macro_6f_exact = round(sum(per_field[f]["exact_pct"] for f in KHP_6_FIELDS) / len(KHP_6_FIELDS), 2)
        macro_6f_fuzzy = round(sum(per_field[f]["fuzzy_pct"] for f in KHP_6_FIELDS) / len(KHP_6_FIELDS), 2)
        macro_7f_exact = round(sum(per_field[f]["exact_pct"] for f in ALL_7_FIELDS) / len(ALL_7_FIELDS), 2)
        macro_7f_fuzzy = round(sum(per_field[f]["fuzzy_pct"] for f in ALL_7_FIELDS) / len(ALL_7_FIELDS), 2)

        results_by_variant[v_key] = {
            "label": v_info["label"],
            "macro_6f_exact": macro_6f_exact,
            "macro_6f_fuzzy": macro_6f_fuzzy,
            "macro_7f_exact": macro_7f_exact,
            "macro_7f_fuzzy": macro_7f_fuzzy,
            "per_field": per_field,
            "latency": {
                "mean_s": round(sum(lats) / len(lats), 3) if lats else 0.0,
                "total_s": round(sum(lats), 2),
            },
            "tokens": {
                "total_tokens": sum(total_tok_list),
                "avg_tokens": round(sum(total_tok_list) / n_docs, 1) if n_docs else 0,
                "total_cost_usd": round(sum(cost_usd_list), 4),
                "total_cost_idr": round(sum(cost_idr_list), 2),
                "cost_idr_per_doc": round(sum(cost_idr_list) / n_docs, 2) if n_docs else 0,
            },
        }

    # Write deliverables
    # 1. per_cert_results.csv
    with open(out_dir / "per_cert_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["variant", "stem", "field", "expected", "actual", "exact", "fuzzy", "match_type", "latency_s"])
        writer.writeheader()
        writer.writerows(detailed_rows)

    # 2. comparison_table.csv
    with open(out_dir / "comparison_table.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Variant", "Label", "6F Exact (%)", "6F Fuzzy (%)",
            "Jenis Penyelenggara (%)", "7F Exact (%)", "Avg Latency (s)",
            "Avg Tok/Doc", "Biaya Total (IDR)", "Biaya/Doc (IDR)",
            "Tingkat (%)", "Penyelenggara (%)", "Kegiatan (%)", "Nomor (%)",
        ])
        for vk, res in results_by_variant.items():
            pf = res["per_field"]
            writer.writerow([
                vk, res["label"], res["macro_6f_exact"], res["macro_6f_fuzzy"],
                pf["jenis_penyelenggara"]["exact_pct"], res["macro_7f_exact"],
                res["latency"]["mean_s"], res["tokens"]["avg_tokens"],
                res["tokens"]["total_cost_idr"], res["tokens"]["cost_idr_per_doc"],
                pf["tingkat"]["exact_pct"], pf["penyelenggara_kegiatan"]["exact_pct"],
                pf["nama_kegiatan_sertifikasi"]["exact_pct"], pf["nomor_bukti_fisik_nomor_sertifikasi"]["exact_pct"],
            ])

    # 3. metrics.json
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(results_by_variant, f, indent=2)

    # 4. manifest.json
    manifest = {
        "campaign_id": "CAMP-PROMPT-OPT",
        "experiment_id": EXP_ID,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "n_documents": len(all_gt),
        "gt_file": GT_UNIFIED_CSV,
        "variants": list(VARIANTS.keys()),
        "status": "PASS" if results_by_variant["V2_CANDIDATE_8F"]["macro_6f_exact"] >= results_by_variant["V1_CONTROL_7F"]["macro_6f_exact"] else "FAIL",
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # 5. prompt_registry.md
    with open(out_dir / "prompt_registry.md", "w", encoding="utf-8") as f:
        f.write(f"# Prompt Registry: {EXP_ID}\n\n")
        f.write("Registry perbandingan teks prompt baseline (Control V2) terhadap kandidat baru (Candidate V2 8-Field).\n\n")
        f.write("## 1. V1_CONTROL_7F (Baseline Control)\n")
        f.write("```text\n[SYSTEM INSTRUCTION]\n" + V2_CONTROL_SYSTEM + "\n\n[USER TEMPLATE]\n" + V2_CONTROL_USER + "\n```\n\n")
        f.write("## 2. V2_CANDIDATE_8F (Candidate Treatment)\n")
        f.write("```text\n[SYSTEM INSTRUCTION]\n" + V2_CANDIDATE_SYSTEM + "\n\n[USER TEMPLATE]\n" + V2_CANDIDATE_USER + "\n```\n\n")
        f.write("## 3. Analisis Perubahan (Diff Summary)\n")
        f.write("- Penambahan Aturan #7 pada System Instruction: Klasifikasi formal 6 enum master `jenis_penyelenggara` (PTN, PTS, PT Luar Negeri, Kementerian, BUMN, Lembaga/Yayasan).\n")
        f.write("- Penambahan field `jenis_penyelenggara` pada skema output JSON di User Template.\n")

    # 6. summary.md
    with open(out_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write(f"# Summary Laporan Eksperimen: {EXP_ID}\n\n")
        f.write(f"- **Waktu**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"- **Model**: `{model}`\n")
        f.write(f"- **Dataset**: `{GT_UNIFIED_CSV}` ($N={len(all_gt)}$)\n\n")
        f.write("## 1. Tabel Komparasi Utama\n\n")
        f.write("| Varian | 6F Exact (%) | 6F Fuzzy (%) | **Jenis Penyelenggara (%)** | 7F Exact (%) | Latensi Rata-rata | Tok/Doc | Biaya/Doc (IDR) |\n")
        f.write("|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n")
        for vk, res in results_by_variant.items():
            pf = res["per_field"]
            f.write(f"| `{vk}` | {res['macro_6f_exact']:.2f}% | {res['macro_6f_fuzzy']:.2f}% | **{pf['jenis_penyelenggara']['exact_pct']:.2f}%** | {res['macro_7f_exact']:.2f}% | {res['latency']['mean_s']:.2f}s | {res['tokens']['avg_tokens']:,} | Rp{res['tokens']['cost_idr_per_doc']:.2f} |\n")

        f.write("\n## 2. Rincian Akurasi per Field (Exact Match %)\n\n")
        f.write("| Field Evaluasi | " + " | ".join(f"`{k}`" for k in VARIANTS.keys()) + " |\n")
        f.write("|---|" + "|".join([":---:"] * len(VARIANTS)) + "|\n")
        for fld in ALL_7_FIELDS:
            line = f"| **{fld}** | "
            line += " | ".join(f"{results_by_variant[k]['per_field'][fld]['exact_pct']:.2f}%" for k in VARIANTS.keys())
            line += " |\n"
            f.write(line)

    print(f"\nDeliverables berhasil dibuat di: {out_dir}")
    return results_by_variant


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run EXP-ALL6F-PROMPT-007 Benchmark")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--limit", type=int, default=None, help="Limit documents for testing")
    args = parser.parse_args()

    out_dir = Path("docs/experiments") / EXP_ID
    run_benchmark(out_dir=out_dir, model=args.model, limit=args.limit)
