import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
PROMPT_VERSION = "v1_aggressive"
MAX_RETRIES = 2
RETRY_DELAY_S = 3

TINGKAT_OPTIONS = [
    "Internasional",
    "Nasional",
    "Universitas",
    "Fakultas",
    "Departemen/Program Studi",
    "Lainnya",
]

TINGKAT_GT_MAP = {
    "Departemen/Prodi": "Departemen/Program Studi",
}


@dataclass
class TokenUsage:
    call_id: str
    certificate: str
    field: str
    method: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_eval_duration_ns: int
    eval_duration_ns: int
    total_duration_ns: int
    tokens_per_second: float
    prompt_version: str
    response: str
    valid: bool
    expected: str | None = None
    correct: bool | None = None


def call_ollama(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 30) -> tuple[str, dict[str, Any]]:
    url = f"{OLLAMA_BASE}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096,
            "num_predict": max_tokens,
            "temperature": 0,
        }
    }).encode()

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
            response = data.get("response", "").strip()
            return response, data
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_S)
                continue
            return "", {"error": str(e), "response": ""}


def build_prompt_tingkat(raw_text: str, known_fields: dict[str, str]) -> str:
    lines = [
        "Tentukan TINGKAT KEGIATAN dari sertifikat berikut.",
        "",
        "ATURAN WAJIB:",
        "- Jawaban HARUS persis salah satu dari opsi di bawah",
        "- JANGAN jawab selain opsi ini",
        "",
        "PETUNJUK TINGKAT:",
        "- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat FAKULTAS (BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas",
        "- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa (HIMATESDA, HIMANO), maka == Departemen/Program Studi",
        "- Jika diselenggarakan oleh BEM Universitas, Rektorat, Direktorat Kemahasiswaan, maka == Universitas",
        "- Jika kegiatan berskala nasional (lomba nasional, webinar nasional), maka == Nasional",
        "- Jika kegiatan berskala internasional (konferensi internasional), maka == Internasional",
        "- 'UNIVERSITAS AIRLANGGA' adalah institusi induk, BUKAN penentu tingkat",
        "",
        "Opsi yang diizinkan:",
    ]
    for opt in TINGKAT_OPTIONS:
        lines.append(f"- {opt}")
    lines.extend([
        "",
        "Teks sertifikat:",
        raw_text,
        "",
        "Field yang sudah diketahui:",
    ])
    for key, label in [("nama_kegiatan_sertifikasi", "Nama Kegiatan"),
                        ("penyelenggara_kegiatan", "Penyelenggara"),
                        ("raw_role", "Peran")]:
        val = known_fields.get(key, "tidak diketahui")
        if not val:
            val = "tidak diketahui"
        lines.append(f"- {label}: {val}")
    lines.extend([
        "",
        "Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):",
    ])
    return "\n".join(lines)


def build_prompt_free_text(field_label: str, raw_text: str, known_fields: dict[str, str]) -> str:
    lines = [
        f"Ekstrak {field_label} dari sertifikat berikut.",
        "",
        "ATURAN:",
        "- Jawaban HANYA nilai field, tanpa penjelasan",
        "- Maksimal 100 karakter",
        "- Jika tidak ditemukan, jawab: TIDAK_DITEMUKAN",
        "",
        "Teks sertifikat:",
        raw_text,
        "",
        "Field yang sudah diketahui:",
    ]
    for key, label in [("nama_kegiatan_sertifikasi", "Nama Kegiatan"),
                        ("penyelenggara_kegiatan", "Penyelenggara"),
                        ("raw_role", "Peran")]:
        val = known_fields.get(key, "tidak diketahui")
        if not val:
            val = "tidak diketahui"
        lines.append(f"- {label}: {val}")
    lines.extend([
        "",
        "Jawaban:",
    ])
    return "\n".join(lines)


def validate_tingkat(value: str) -> str | None:
    clean = value.strip().rstrip(".")
    if not clean:
        return None
    clean_upper = clean.upper()
    valid_upper = [o.upper() for o in TINGKAT_OPTIONS]
    if clean_upper in valid_upper:
        idx = valid_upper.index(clean_upper)
        return TINGKAT_OPTIONS[idx]
    for opt in TINGKAT_OPTIONS:
        opt_u = opt.upper()
        if opt_u in clean_upper or clean_upper in opt_u:
            return opt
    if "DEPARTEMEN" in clean_upper or "PRODI" in clean_upper:
        return "Departemen/Program Studi"
    if "NASIONAL" in clean_upper:
        return "Nasional"
    if "UNIVERSITAS" in clean_upper:
        return "Universitas"
    if "INTERNASIONAL" in clean_upper:
        return "Internasional"
    if "LAINNYA" in clean_upper or "LAIN" in clean_upper or clean_upper == "OTHER":
        return "Lainnya"
    return None


def validate_free_text(value: str) -> str | None:
    clean = value.strip().rstrip(".")
    if not clean:
        return None
    clean_upper = clean.upper()
    clean_compact = clean_upper.replace(" ", "").replace("_", "").replace("-", "")
    reject_patterns = [
        "TIDAKDITEMUKAN", "TIDAKTAHU", "TIDAKDIKETAHUI", "TIDAKADA",
        "NOTFOUND", "PENDING", "UNKNOWN", "NONE", "NULL", "TIDAK",
        "TIDAKDAPAT", "SAYATAHU", "TIDAKBISA",
    ]
    if clean_compact in reject_patterns or clean_upper in ("-", "--"):
        return None
    if len(clean) < 3:
        return None
    import re as _re
    clean = _re.sub(r"\s+", " ", clean)
    return clean[:100]


def log_call(call: TokenUsage, log_path: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    calls = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            try:
                calls = json.load(f)
            except json.JSONDecodeError:
                calls = []
    calls.append(asdict(call))
    with open(log_path, "w") as f:
        json.dump(calls, f, indent=2)


def build_token_usage_summary(log_path: str) -> dict:
    if not os.path.exists(log_path):
        return {}
    with open(log_path) as f:
        calls = json.load(f)
    if not calls:
        return {}
    total_prompt = sum(c["prompt_tokens"] for c in calls)
    total_completion = sum(c["completion_tokens"] for c in calls)
    total_all = total_prompt + total_completion
    durations = [c["total_duration_ns"] for c in calls if c["total_duration_ns"] > 0]
    avg_latency_ms = (sum(durations) / len(durations) / 1_000_000) if durations else 0
    tps_values = [c["tokens_per_second"] for c in calls if c["tokens_per_second"] > 0]
    avg_tps = (sum(tps_values) / len(tps_values)) if tps_values else 0
    by_field = {}
    for c in calls:
        f = c["field"]
        if f not in by_field:
            by_field[f] = {"calls": 0, "total_prompt_tokens": 0,
                           "total_completion_tokens": 0, "total_duration_ns": 0}
        by_field[f]["calls"] += 1
        by_field[f]["total_prompt_tokens"] += c["prompt_tokens"]
        by_field[f]["total_completion_tokens"] += c["completion_tokens"]
        by_field[f]["total_duration_ns"] += c["total_duration_ns"]
    for f in by_field:
        n = by_field[f]["calls"]
        by_field[f]["avg_prompt_tokens"] = round(by_field[f]["total_prompt_tokens"] / n, 1)
        by_field[f]["avg_completion_tokens"] = round(by_field[f]["total_completion_tokens"] / n, 1)
        by_field[f]["avg_latency_ms"] = round(by_field[f]["total_duration_ns"] / n / 1_000_000, 1)
    by_cert = {}
    for c in calls:
        cert = c["certificate"]
        if cert not in by_cert:
            by_cert[cert] = {"calls": 0, "total_tokens": 0}
        by_cert[cert]["calls"] += 1
        by_cert[cert]["total_tokens"] += c["prompt_tokens"] + c["completion_tokens"]
    return {
        "method": "hybrid_pp_llm",
        "model": calls[0].get("model", "unknown"),
        "prompt_version": calls[0].get("prompt_version", "unknown"),
        "total_calls": len(calls),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_all,
        "avg_latency_ms": round(avg_latency_ms, 1),
        "avg_tokens_per_second": round(avg_tps, 1),
        "by_field": by_field,
        "by_certificate": by_cert,
    }
