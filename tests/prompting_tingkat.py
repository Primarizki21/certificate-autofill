"""Eksperimen Prompting LLM untuk Klasifikasi Tingkat Sertifikat.

Mengimplementasikan 5 teknik prompting sesuai instruksi:
1. Zero-Shot Prompting: Instruksi tanpa contoh acuan.
2. Few-Shot Prompting: Memberikan contoh in-context untuk membedakan lomba terbuka vs internal.
3. Chain-of-Thought (CoT): Penalaran bertahap (Penyelenggara -> Sifat Acara -> Sasaran Peserta -> Tingkat).
4. Self-Consistency: Multi-path sampling reasoning + majority voting.
5. Iterative Prompting: Dekomposisi sekuensial multi-langkah (Ekstraksi -> Analisis Skala -> Pemetaan).

Mendukung provider-neutral (Ollama, Gemini dengan x-goog-api-key, dan Mock/Offline fallback).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

# Pilihan tingkat resmi sesuai FORM_OPTIONS
TINGKAT_OPTIONS = [
    "Internasional",
    "Nasional",
    "Universitas",
    "Fakultas",
    "Departemen/Program Studi",
    "Lainnya",
]

# Pemetaan alias variasi penulisan ke nilai standar
TINGKAT_CANONICAL_MAP = {
    "INTERNASIONAL": "Internasional",
    "INTERNATIONAL": "Internasional",
    "NASIONAL": "Nasional",
    "NATIONAL": "Nasional",
    "UNIVERSITAS": "Universitas",
    "UNIVERSITY": "Universitas",
    "FAKULTAS": "Fakultas",
    "FACULTY": "Fakultas",
    "DEPARTEMEN": "Departemen/Program Studi",
    "DEPARTMENT": "Departemen/Program Studi",
    "PRODI": "Departemen/Program Studi",
    "PROGRAM STUDI": "Departemen/Program Studi",
    "DEPARTEMEN/PRODI": "Departemen/Program Studi",
    "DEPARTEMEN/PROGRAM STUDI": "Departemen/Program Studi",
    "LAINNYA": "Lainnya",
    "OTHER": "Lainnya",
}


@dataclass
class LLMCallMeta:
    """Metadata panggilan model bahasa mencakup token rinci, biaya, dan web search."""
    text: str
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    cached_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_idr: float = 0.0
    web_search_queries: list[str] = field(default_factory=list)


@dataclass
class PromptingResult:
    """Hasil ekstraksi tingkat dari teknik prompting beserta metrik token rinci & review."""
    tingkat: str | None
    raw_response: str
    technique: str
    reasoning_steps: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_review: bool = False
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    cached_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_idr: float = 0.0
    web_search_queries: list[str] = field(default_factory=list)
    call_metrics: list[dict[str, Any]] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

def clean_response(text: str) -> str:
    """Bersihkan output model dari tag markdown dan spasi berlebih."""
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")
    return text.strip()


def validate_tingkat(text: str | None) -> str | None:
    """Ekstraksi dan validasi opsi tingkat dari respons teks model."""
    if not text:
        return None
    cleaned = clean_response(text)
    upper = cleaned.upper()

    # Cek persis opsi kanonikal
    for opt in TINGKAT_OPTIONS:
        if opt.upper() == upper:
            return opt

    # Cek baris per baris bila model memberikan output terstruktur
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    for line in reversed(lines):
        line_upper = line.upper()
        # Cari pola KESIMPULAN / TINGKAT: ...
        match = re.search(r"(?:KESIMPULAN|TINGKAT|LEVEL|HASIL)\s*[:=]\s*([A-Za-z/ ]+)", line, re.IGNORECASE)
        if match:
            cand = match.group(1).strip().upper()
            if cand in TINGKAT_CANONICAL_MAP:
                return TINGKAT_CANONICAL_MAP[cand]
            for opt in TINGKAT_OPTIONS:
                if opt.upper() in cand:
                    return opt

        for opt in TINGKAT_OPTIONS:
            if opt.upper() == line_upper:
                return opt

    # Fallback substring matching berbasis prioritas
    if "INTERNASIONAL" in upper or "INTERNATIONAL" in upper:
        return "Internasional"
    if "NASIONAL" in upper or "NATIONAL" in upper:
        return "Nasional"
    if "DEPARTEMEN" in upper or "PROGRAM STUDI" in upper or "PRODI" in upper:
        return "Departemen/Program Studi"
    if "FAKULTAS" in upper or "FACULTY" in upper:
        return "Fakultas"
    if "UNIVERSITAS" in upper or "UNIVERSITY" in upper:
        return "Universitas"
    if "LAINNYA" in upper:
        return "Lainnya"

    return None


# ==============================================================================
# 1. Zero-Shot Prompting
# ==============================================================================
def build_zero_shot_prompt(raw_text: str, known_fields: dict[str, str] | None = None) -> str:
    """Membangun prompt Zero-Shot murni untuk klasifikasi tingkat tanpa contoh atau aturan panjang."""
    kegiatan = (known_fields or {}).get("nama_kegiatan_sertifikasi", "-")
    penyelenggara = (known_fields or {}).get("penyelenggara_kegiatan", "-")

    return f"""Tentukan TINGKAT KEGIATAN dari teks sertifikat berikut.

Pilihan Tingkat yang Valid:
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

Data Sertifikat:
- Nama Kegiatan: {kegiatan}
- Penyelenggara: {penyelenggara}

Teks Sertifikat:
\"\"\"
{raw_text.strip()}
\"\"\"

Jawab HANYA dengan SATU nama tingkat dari daftar pilihan valid di atas, tanpa kalimat pembuka atau penjelasan tambahan.
Jawaban:"""

# ==============================================================================
# 2. Few-Shot Prompting
# ==============================================================================
def build_few_shot_prompt(raw_text: str, known_fields: dict[str, str] | None = None) -> str:
    """Membangun prompt Few-Shot dengan contoh sintetis anonim (bebas dari nama event dataset nyata)."""
    kegiatan = (known_fields or {}).get("nama_kegiatan_sertifikasi", "-")
    penyelenggara = (known_fields or {}).get("penyelenggara_kegiatan", "-")

    return f"""Tentukan TINGKAT KEGIATAN dari sertifikat mahasiswa berdasarkan contoh-contoh berikut.

PILIHAN TINGKAT:
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

---
CONTOH 1:
Nama Kegiatan: National Competitive Programming Contest
Penyelenggara: Himpunan Mahasiswa Informatika Institut Teknologi XYZ
Teks Sertifikat: Diberikan kepada Juara 1 dalam kompetisi pemrograman terbuka tingkat mahasiswa nasional.
Tingkat: Nasional

CONTOH 2:
Nama Kegiatan: Pekan Olahraga Mahasiswa Fakultas Teknik
Penyelenggara: BEM Fakultas Teknik Universitas ABC
Teks Sertifikat: Sebagai Panitia Pelaksana Pekan Olahraga antar-program studi di lingkungan Fakultas Teknik.
Tingkat: Fakultas

CONTOH 3:
Nama Kegiatan: Pengenalan Kehidupan Kampus Mahasiswa Baru Universitas
Penyelenggara: Direktorat Kemahasiswaan Universitas ABC
Teks Sertifikat: Diberikan kepada mahasiswa baru sebagai Peserta Pengenalan Kehidupan Kampus tingkat Universitas.
Tingkat: Universitas

CONTOH 4:
Nama Kegiatan: National Data Science Challenge
Penyelenggara: BEM Fakultas Sains dan Matematika Universitas ABC
Teks Sertifikat: Sebagai Finalis dalam kompetisi sains data yang diikuti oleh mahasiswa perwakilan berbagai perguruan tinggi se-Indonesia.
Tingkat: Nasional

CONTOH 5:
Nama Kegiatan: Rapat Kerja Anggota Himpunan Departemen Kimia
Penyelenggara: Himpunan Mahasiswa Departemen Kimia
Teks Sertifikat: Sebagai Peserta Rapat Kerja Tahunan Anggota Himpunan Mahasiswa Kimia.
Tingkat: Departemen/Program Studi

CONTOH 6:
Nama Kegiatan: International Conference on Applied Technology
Penyelenggara: Institute of Global Engineers
Teks Sertifikat: For presenting a research paper in the international symposium with participants from 12 countries.
Tingkat: Internasional
---

DATA INPUT:
Nama Kegiatan: {kegiatan}
Penyelenggara: {penyelenggara}
Teks Sertifikat:
\"\"\"
{raw_text.strip()}
\"\"\"

Tingkat:"""

# ==============================================================================
# 3. Chain-of-Thought (CoT) Prompting
# ==============================================================================
def build_cot_prompt(raw_text: str, known_fields: dict[str, str] | None = None) -> str:
    """Membangun prompt Chain-of-Thought (penalaran berurutan step-by-step)."""
    kegiatan = (known_fields or {}).get("nama_kegiatan_sertifikasi", "-")
    penyelenggara = (known_fields or {}).get("penyelenggara_kegiatan", "-")

    return f"""Analisis dan tentukan TINGKAT KEGIATAN sertifikat berikut secara bertahap.

PILIHAN TINGKAT:
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

ATURAN PENALARAN (Chain of Thought):
Langkah 1 (Identifikasi Penyelenggara): Siapa unit penyelenggara acara (Universitas, BEM Fakultas, Himpunan Mahasiswa, Lembaga Eksternal/Asing)?
Langkah 2 (Identifikasi Sifat Kegiatan): Apakah kegiatan merupakan lomba/kompetisi/seminar terbuka, ataukah kegiatan internal (orientasi mahasiswa baru, turnamen fakultas, rapat kerja, kepengurusan internal)?
Langkah 3 (Penilaian Cakupan Sasaran Peserta vs Penyelenggara):
  - Terapkan aturan: Cakupan Sasaran Peserta (Scope) LEBIH UTAMA daripada Jenjang Penyelenggara.
  - Jika acara merupakan lomba/kompetisi terbuka untuk mahasiswa umum lintas perguruan tinggi se-Indonesia, maka cakupan sasaran adalah NASIONAL (meskipun penyelenggaranya adalah Fakultas atau Himpunan).
  - Jika acara adalah internal civitas, maka ikuti jenjang penyelenggara (Universitas / Fakultas / Departemen).
  - Jika bukti tidak mencukupi untuk memastikan cakupan, simpulkan sebagai 'Lainnya'.
Langkah 4 (Kesimpulan Tingkat): Ambil kesimpulan akhir dari pilihan resmi.

DATA SERTIFIKAT:
- Nama Kegiatan: {kegiatan}
- Penyelenggara: {penyelenggara}
- Teks Mentah:
\"\"\"
{raw_text.strip()}
\"\"\"

Format Jawaban Wajib:
Langkah 1: ...
Langkah 2: ...
Langkah 3: ...
Langkah 4: ...
TINGKAT: [Pilih SATU dari daftar pilihan resmi]"""


# ==============================================================================
# 4. Self-Consistency Runner
# ==============================================================================
def _extract_meta(res: Any) -> LLMCallMeta:
    if isinstance(res, LLMCallMeta):
        return res
    return LLMCallMeta(text=str(res))


def run_self_consistency(
    raw_text: str,
    known_fields: dict[str, str] | None,
    call_llm_func: Callable[[str, float], str | LLMCallMeta],
    n_samples: int = 3,
    temperature: float = 0.5,
) -> PromptingResult:
    """Menjalankan self-consistency sampling dengan majority voting."""
    if n_samples < 1:
        raise ValueError("n_samples harus >= 1")

    prompt = build_cot_prompt(raw_text, known_fields)
    votes: list[str] = []
    raw_samples: list[str] = []

    prompt_tokens = 0
    candidates_tokens = 0
    cached_tokens = 0
    thoughts_tokens = 0
    total_tokens = 0
    cost_usd = 0.0
    cost_idr = 0.0
    web_queries: list[str] = []
    call_metrics: list[dict[str, Any]] = []

    for idx in range(n_samples):
        call_res = call_llm_func(prompt, temperature)
        meta = _extract_meta(call_res)
        prompt_tokens += meta.prompt_tokens
        candidates_tokens += meta.candidates_tokens
        cached_tokens += meta.cached_tokens
        thoughts_tokens += meta.thoughts_tokens
        total_tokens += meta.total_tokens
        cost_usd += meta.cost_usd
        cost_idr += meta.cost_idr
        web_queries.extend(meta.web_search_queries)
        call_metrics.append({
            "step": f"sample_{idx + 1}",
            "prompt_tokens": meta.prompt_tokens,
            "candidates_tokens": meta.candidates_tokens,
            "cached_tokens": meta.cached_tokens,
            "thoughts_tokens": meta.thoughts_tokens,
            "total_tokens": meta.total_tokens,
            "cost_usd": meta.cost_usd,
            "cost_idr": meta.cost_idr,
            "web_queries": meta.web_search_queries,
        })

        raw_samples.append(meta.text)
        parsed = validate_tingkat(meta.text)
        if parsed:
            votes.append(parsed)
    if not votes:
        return PromptingResult(
            tingkat=None,
            raw_response="\n---\n".join(raw_samples),
            technique="self-consistency",
            samples=raw_samples,
            confidence=0.0,
            needs_review=True,
            prompt_tokens=prompt_tokens,
            candidates_tokens=candidates_tokens,
            cached_tokens=cached_tokens,
            thoughts_tokens=thoughts_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            cost_idr=cost_idr,
            web_search_queries=web_queries,
            call_metrics=call_metrics,
            metadata={"error": "no_valid_votes", "n_samples": n_samples},
        )

    counts = Counter(votes)
    top_candidates = counts.most_common(2)

    # Deteksi tie secara eksplisit jika dua kandidat teratas memiliki suara sama
    is_tie = len(top_candidates) > 1 and top_candidates[0][1] == top_candidates[1][1]
    if is_tie:
        winner = None
        confidence = top_candidates[0][1] / len(votes)
        needs_review = True
    else:
        winner, win_count = top_candidates[0]
        confidence = win_count / len(votes)
        # Invariant wajib: confidence < 0.85 atau hasil ambigu WAJIB needs_review = True
        needs_review = bool(confidence < 0.85 or winner in (None, "Lainnya"))

    return PromptingResult(
        tingkat=winner,
        raw_response=raw_samples[0] if raw_samples else "",
        technique="self-consistency",
        samples=raw_samples,
        confidence=confidence,
        needs_review=needs_review,
        prompt_tokens=prompt_tokens,
        candidates_tokens=candidates_tokens,
        cached_tokens=cached_tokens,
        thoughts_tokens=thoughts_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        cost_idr=cost_idr,
        web_search_queries=web_queries,
        call_metrics=call_metrics,
        metadata={
            "total_valid_votes": len(votes),
            "is_tie": is_tie,
        },
    )


# ==============================================================================
# 5. Iterative Prompting (Sequential Decomposition)
# ==============================================================================
def run_iterative_prompting(
    raw_text: str,
    known_fields: dict[str, str] | None,
    call_llm_func: Callable[[str, float], str | LLMCallMeta],
) -> PromptingResult:
    """Menjalankan Iterative Prompting dengan 3 langkah sekuensial interaktif."""
    steps_log: list[str] = []
    prompt_tokens = 0
    candidates_tokens = 0
    cached_tokens = 0
    thoughts_tokens = 0
    total_tokens = 0
    cost_usd = 0.0
    cost_idr = 0.0
    web_queries: list[str] = []
    call_metrics: list[dict[str, Any]] = []

    def _do_step(step_name: str, prompt: str) -> str:
        nonlocal prompt_tokens, candidates_tokens, cached_tokens, thoughts_tokens, total_tokens, cost_usd, cost_idr
        call_res = call_llm_func(prompt, 0.0)
        meta = _extract_meta(call_res)
        prompt_tokens += meta.prompt_tokens
        candidates_tokens += meta.candidates_tokens
        cached_tokens += meta.cached_tokens
        thoughts_tokens += meta.thoughts_tokens
        total_tokens += meta.total_tokens
        cost_usd += meta.cost_usd
        cost_idr += meta.cost_idr
        web_queries.extend(meta.web_search_queries)
        call_metrics.append({
            "step": step_name,
            "prompt_tokens": meta.prompt_tokens,
            "candidates_tokens": meta.candidates_tokens,
            "cached_tokens": meta.cached_tokens,
            "thoughts_tokens": meta.thoughts_tokens,
            "total_tokens": meta.total_tokens,
            "cost_usd": meta.cost_usd,
            "cost_idr": meta.cost_idr,
            "web_queries": meta.web_search_queries,
        })
        return meta.text

    # Step 1: Identifikasi Penyelenggara & Jenis Kegiatan
    prompt_step1 = f"""Tugas Langkah 1: Identifikasi nama kegiatan, penyelenggara, dan jenis kegiatan dari teks sertifikat berikut.
Teks Sertifikat:
\"\"\"
{raw_text.strip()}
\"\"\"

Jawab dalam format ringkas:
- Nama Kegiatan: ...
- Penyelenggara: ...
- Jenis Kegiatan: (Lomba/Kompetisi / Seminar / Kepanitiaan / Kepengurusan / Pelatihan / Lainnya)"""
    resp_step1 = _do_step("step_1_extraction", prompt_step1)
    steps_log.append(f"Step 1 Output:\n{resp_step1}")

    # Step 2: Analisis Cakupan Sasaran Peserta (Scope Analysis)
    prompt_step2 = f"""Berdasarkan informasi kegiatan berikut:
{resp_step1}

Teks Pendukung:
\"\"\"
{raw_text[:600].strip()}
\"\"\"

Tugas Langkah 2: Analisis cakupan sasaran peserta kegiatan.
Apakah kegiatan ini:
A. Terbuka untuk mahasiswa se-Indonesia (Skala Nasional)
B. Acara internal fakultas / antar-departemen di satu fakultas
C. Acara internal satu program studi / himpunan
D. Acara tingkat universitas
E. Melibatkan peserta/institusi internasional

Jelaskan analisis sasaran peserta secara singkat (1-2 kalimat)."""
    resp_step2 = _do_step("step_2_scope_analysis", prompt_step2)
    steps_log.append(f"Step 2 Output:\n{resp_step2}")

    # Step 3: Pemetaan Final ke Pilihan Resmi
    prompt_step3 = f"""Berdasarkan analisis sebelumnya:
Ringkasan Kegiatan:
{resp_step1}

Analisis Sasaran:
{resp_step2}

Tugas Langkah 3: Tentukan TINGKAT KEGIATAN akhir.
PILIHAN RESMI (Wajib pilih salah satu):
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

Aturan Khusus:
Jika jenis kegiatan adalah lomba/kompetisi terbuka untuk mahasiswa umum lintas kampus, petakan sebagai 'Nasional' meskipun penyelenggaranya adalah BEM Fakultas atau Himpunan Mahasiswa.

TINGKAT:"""
    resp_step3 = _do_step("step_3_final_mapping", prompt_step3)
    steps_log.append(f"Step 3 Output:\n{resp_step3}")

    final_tingkat = validate_tingkat(resp_step3)

    # Pisahkan penilaian kesesuaian semantik (agreement) dari confidence
    s2_lower = resp_step2.lower()
    semantic_agreement = False
    if final_tingkat == "Nasional" and ("nasional" in s2_lower or "se-indonesia" in s2_lower or "terbuka" in s2_lower):
        semantic_agreement = True
    elif final_tingkat == "Fakultas" and ("fakultas" in s2_lower or "dekan" in s2_lower):
        semantic_agreement = True
    elif final_tingkat == "Universitas" and ("universitas" in s2_lower or "rektorat" in s2_lower):
        semantic_agreement = True
    elif final_tingkat == "Departemen/Program Studi" and ("departemen" in s2_lower or "prodi" in s2_lower or "himpunan" in s2_lower):
        semantic_agreement = True
    elif final_tingkat == "Internasional" and ("internasional" in s2_lower or "international" in s2_lower):
        semantic_agreement = True

    # Hitung confidence konservatif (tidak circular)
    if not final_tingkat:
        confidence = 0.0
    elif final_tingkat == "Lainnya":
        confidence = 0.40
    elif semantic_agreement:
        confidence = 0.80
    else:
        confidence = 0.50

    # Invariant wajib sistem: confidence < 0.85 otomatis memicu review
    needs_review = bool(confidence < 0.85 or final_tingkat in (None, "Lainnya"))
    return PromptingResult(
        tingkat=final_tingkat,
        raw_response=resp_step3,
        technique="iterative",
        reasoning_steps=steps_log,
        confidence=confidence,
        needs_review=needs_review,
        prompt_tokens=prompt_tokens,
        candidates_tokens=candidates_tokens,
        cached_tokens=cached_tokens,
        thoughts_tokens=thoughts_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        cost_idr=cost_idr,
        web_search_queries=web_queries,
        call_metrics=call_metrics,
        metadata={"step1": resp_step1, "step2": resp_step2, "step3": resp_step3},
    )
