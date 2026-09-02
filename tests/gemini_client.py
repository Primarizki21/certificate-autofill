"""Google Gemini REST API client and token/cost ledger for extraction benchmarks.

Communicates with Google Generative Language REST API using only Python standard
library (urllib.request, json, time, os, dataclasses) without extra dependencies.
Includes token accounting, USD/IDR cost calculations, deterministic generationConfig,
safe JSON extraction, and rate-limiting retry logic.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Kurs referensi resmi per 2 Agustus 2026 (dapat di-override via env)
DEFAULT_EXCHANGE_RATE_IDR = 17758.0


@dataclass(frozen=True)
class GeminiPricing:
    """Tarif resmi Google Gemini (USD per 1 Million Tokens)."""
    input_rate: float
    output_rate: float
    cache_rate: float


# Tabel Tarif Resmi Standard Paid Tier
PRICING_TABLE: dict[str, GeminiPricing] = {
    "gemini-2.5-flash": GeminiPricing(input_rate=0.30, output_rate=2.50, cache_rate=0.03),
    "gemini-2.5-flash-lite": GeminiPricing(input_rate=0.10, output_rate=0.40, cache_rate=0.01),
    "gemini-3.1-flash-lite": GeminiPricing(input_rate=0.25, output_rate=1.50, cache_rate=0.025),
}


@dataclass
class GeminiCallResult:
    """Hasil pemanggilan Gemini API beserta metrik token, biaya, dan latensi."""
    response_text: str = ""
    parsed_json: dict[str, Any] | None = None
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    cached_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_idr: float = 0.0
    latency_s: float = 0.0
    model: str = ""
    status: str = "success"  # "success" | "rate_limited" | "error"
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_text": self.response_text,
            "parsed_json": self.parsed_json,
            "prompt_tokens": self.prompt_tokens,
            "candidates_tokens": self.candidates_tokens,
            "cached_tokens": self.cached_tokens,
            "thoughts_tokens": self.thoughts_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "cost_idr": self.cost_idr,
            "latency_s": self.latency_s,
            "model": self.model,
            "status": self.status,
            "error_message": self.error_message,
        }


def get_exchange_rate() -> float:
    """Ambil kurs konversi IDR/USD dari env atau nilai default."""
    raw = os.environ.get("EXCHANGE_RATE_IDR_PER_USD")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_EXCHANGE_RATE_IDR


def load_google_api_key(env_path: str | Path | None = None) -> str | None:
    """Membaca GOOGLE_API_KEY dari .env.google atau os.environ."""
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    else:
        candidates.append(Path(".env.google"))
        candidates.append(Path(__file__).resolve().parent.parent / ".env.google")

    for p in candidates:
        if p.exists() and p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("GOOGLE_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip("\"'")
                        if key:
                            return key
            except Exception:
                pass

    return os.environ.get("GOOGLE_API_KEY")


def calculate_cost(
    model: str,
    prompt_tokens: int,
    candidates_tokens: int,
    cached_tokens: int = 0,
    thoughts_tokens: int = 0,
    exchange_rate: float | None = None,
) -> tuple[float, float]:
    """Hitung estimasi biaya dalam USD dan IDR berdasarkan token usage."""
    rate = exchange_rate if exchange_rate is not None else get_exchange_rate()
    pricing = PRICING_TABLE.get(model, PRICING_TABLE["gemini-2.5-flash"])

    effective_output_tokens = candidates_tokens + thoughts_tokens

    cost_usd = (
        (prompt_tokens * pricing.input_rate)
        + (effective_output_tokens * pricing.output_rate)
        + (cached_tokens * pricing.cache_rate)
    ) / 1_000_000.0

    cost_idr = cost_usd * rate
    return cost_usd, cost_idr


def clean_json_markdown(text: str) -> str:
    """Bersihkan markdown code block jika model membungkus respons dengan ```json ... ```."""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if match:
        return match.group(1).strip()
    return stripped


class GeminiClient:
    """Client REST API Google Generative Language dengan rate limiting & token accounting."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gemini-2.5-flash",
        request_delay: float = 1.2,
        max_retries: int = 3,
        timeout_s: float = 60.0,
        exchange_rate: float | None = None,
    ) -> None:
        self.api_key = api_key or load_google_api_key()
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY tidak ditemukan! Simpan kunci di .env.google atau export GOOGLE_API_KEY."
            )
        self.default_model = default_model
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.exchange_rate = exchange_rate or get_exchange_rate()
        self._last_call_timestamp: float = 0.0

    def _sanitize_error(self, err_str: str) -> str:
        """Hapus API key dari teks error agar tidak terekspos ke log."""
        if self.api_key and self.api_key in err_str:
            return err_str.replace(self.api_key, "[REDACTED_API_KEY]")
        return err_str

    def _enforce_pacing(self) -> None:
        """Terapkan jeda antar panggilan untuk mencegah burst rate limit."""
        if self.request_delay <= 0:
            return
        now = time.perf_counter()
        elapsed = now - self._last_call_timestamp
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_call_timestamp = time.perf_counter()

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> GeminiCallResult:
        """Panggil Gemini generateContent dengan ekspektasi JSON terstruktur."""
        target_model = model or self.default_model
        endpoint_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
        )

        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        encoded_payload = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        retries = 0
        backoff_delay = 2.0

        while retries <= self.max_retries:
            self._enforce_pacing()
            req = urllib.request.Request(endpoint_url, data=encoded_payload, headers=headers)
            t_start = time.perf_counter()

            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    latency = time.perf_counter() - t_start
                    raw_body = resp.read().decode("utf-8")
                    data = json.loads(raw_body)

                    # Ekstrak text dari candidate
                    cand_text = ""
                    candidates = data.get("candidates") or []
                    if candidates:
                        first_cand = candidates[0]
                        content = first_cand.get("content") or {}
                        parts = content.get("parts") or []
                        if parts:
                            cand_text = parts[0].get("text", "")

                    # Parse JSON
                    clean_text = clean_json_markdown(cand_text)
                    parsed = None
                    try:
                        parsed = json.loads(clean_text)
                    except json.JSONDecodeError:
                        parsed = None

                    # Parse usage metadata
                    usage = data.get("usageMetadata") or {}
                    prompt_tokens = int(usage.get("promptTokenCount") or 0)
                    cand_tokens = int(usage.get("candidatesTokenCount") or 0)
                    cached_tokens = int(usage.get("cachedContentTokenCount") or 0)
                    thoughts_tokens = int(usage.get("thoughtsTokenCount") or 0)
                    total_tokens = int(usage.get("totalTokenCount") or (prompt_tokens + cand_tokens + thoughts_tokens))

                    cost_usd, cost_idr = calculate_cost(
                        model=target_model,
                        prompt_tokens=prompt_tokens,
                        candidates_tokens=cand_tokens,
                        cached_tokens=cached_tokens,
                        thoughts_tokens=thoughts_tokens,
                        exchange_rate=self.exchange_rate,
                    )

                    return GeminiCallResult(
                        response_text=clean_text,
                        parsed_json=parsed,
                        prompt_tokens=prompt_tokens,
                        candidates_tokens=cand_tokens,
                        cached_tokens=cached_tokens,
                        thoughts_tokens=thoughts_tokens,
                        total_tokens=total_tokens,
                        cost_usd=cost_usd,
                        cost_idr=cost_idr,
                        latency_s=round(latency, 4),
                        model=target_model,
                        status="success" if parsed is not None else "error",
                        error_message=None if parsed is not None else "JSON parse error from model response",
                    )

            except urllib.error.HTTPError as he:
                latency = time.perf_counter() - t_start
                status_code = he.code
                error_body = ""
                try:
                    error_body = he.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                clean_err = self._sanitize_error(f"HTTP {status_code}: {error_body[:300]}")

                # Cek header Retry-After bila ada
                retry_after_hdr = he.headers.get("Retry-After")
                sleep_time = backoff_delay
                if retry_after_hdr:
                    try:
                        sleep_time = max(float(retry_after_hdr), sleep_time)
                    except ValueError:
                        pass

                # Handle Rate Limit (429) & Service Unavailable (503)
                if status_code in (429, 503) and retries < self.max_retries:
                    retries += 1
                    sleep_time = max(sleep_time, 5.0 * retries)
                    time.sleep(sleep_time)
                    backoff_delay *= 2.0
                    continue

                return GeminiCallResult(
                    response_text="",
                    parsed_json=None,
                    latency_s=round(latency, 4),
                    model=target_model,
                    status="rate_limited" if status_code == 429 else "error",
                    error_message=clean_err,
                )

            except Exception as e:
                latency = time.perf_counter() - t_start
                clean_err = self._sanitize_error(str(e))
                if retries < self.max_retries:
                    retries += 1
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                    continue

                return GeminiCallResult(
                    response_text="",
                    parsed_json=None,
                    latency_s=round(latency, 4),
                    model=target_model,
                    status="error",
                    error_message=clean_err,
                )

        return GeminiCallResult(
            response_text="",
            parsed_json=None,
            model=target_model,
            status="error",
            error_message="Max retries exceeded",
        )
