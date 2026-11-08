# SPDX-License-Identifier: AGPL-3.0-or-later
"""The model-fit helper: what model this box can run, from arithmetic over its
hardware.  Offline, no downloads, no telemetry; it prints a ceiling and a
checklist, never a URL.  See ``docs/fork/FEATURES.md`` §4.
"""

from __future__ import annotations

__all__ = [
    "Hardware",
    "Recommendation",
    "weight_gb",
    "kv_cache_gb",
    "budget_gb",
    "tokens_per_second",
    "recommend",
    "report",
    "CHECKLIST",
    "QUANT_GB_PER_B",
]

import threading
import time
import typing as t

import msgspec

from searx.fork.modelfit.hardware import Hardware, read_hardware

QUANT_GB_PER_B: dict[str, float] = {"Q4_K_M": 0.60, "Q5_K_M": 0.72, "Q6_K": 0.82, "Q8_0": 1.07, "F16": 2.0}
"""GB of weights per billion parameters, GGUF rules of thumb (small unquantised tensors included)."""

DEFAULT_BANDWIDTH_GBS = 30.0
"""Assumed when the memory type is unknown: a little under DDR4 dual-channel."""

CHECKLIST: list[tuple[str, str]] = [
    (
        "Instruction-tuned",
        "the name ends in -Instruct, -it or -chat; base models do not follow the cite-your-sources instruction.",
    ),
    ("Context length", "at least 8k: five sources plus a claim is 2–3k tokens."),
    (
        "Quantisation",
        "Q4_K_M is the sweet spot; below Q4 the model starts inventing citations; Q8 if the budget allows.",
    ),
    (
        "Structured output",
        "a model that reliably emits JSON (most 2024+ instruct models) "
        "or a server that enforces a grammar (llama.cpp, vLLM).",
    ),
    ("Tool use", "not needed for this product; do not pay for it."),
    ("Vision", "only for the vision_llm OCR backend; look for -VL or multimodal models in the 2–4B class."),
    ("Licence", "check it allows your use; this helper does not."),
]


class Recommendation(msgspec.Struct, kw_only=True):  # pylint: disable=too-few-public-methods
    """What the arithmetic says, for the preferences page and the JSON route."""

    tier: str
    """One line naming the hardware class."""
    ceiling: str
    """The largest sensible model: parameters, quantisation, context."""
    suggest: str
    """What to load first."""
    where: str
    """``gpu``, ``cpu`` or ``apple``."""
    budget_gb: float
    """Memory left for weights plus KV cache."""
    params_b: float
    """Parameter count of the suggested class, in billions."""
    quant: str
    context: int
    tokens_per_s: float | None = None
    """Rough generation speed for the suggested class (CPU and Apple only)."""
    notes: list[str] = []
    checklist: list[tuple[str, str]] = msgspec.field(default_factory=lambda: list(CHECKLIST))


def weight_gb(params_b: float, quant: str = "Q4_K_M") -> float:
    """Weights in GB for ``params_b`` billion parameters at ``quant``."""
    return round(params_b * QUANT_GB_PER_B.get(quant, QUANT_GB_PER_B["Q4_K_M"]), 2)


def kv_cache_gb(tokens: int, layers: int = 32, kv_heads: int = 8, head_dim: int = 128) -> float:
    """KV cache in GB for ``tokens`` of context, f16, assuming GQA (the Llama-3-8B shape by default)."""
    per_token = 2 * layers * kv_heads * head_dim * 2
    return round(tokens * per_token / 1024**3, 3)


def budget_gb(box: Hardware) -> tuple[float, str]:
    """``(GB for weights + KV, where)``: the best GPU's VRAM minus 0.8 GB, Apple's
    70 % of unified memory, or on CPU the available memory minus 3 GB (OS,
    SearXNG, Valkey) and never more than 70 % of the total."""
    gpu = max(box.gpus, key=lambda g: g.vram_gb, default=None)
    if gpu and gpu.vram_gb >= 4:
        return round(max(0.0, gpu.vram_gb - 0.8), 2), "gpu"
    if box.apple_unified:
        return round(box.mem_total_gb * 0.70, 2), "apple"
    available = box.mem_available_gb or box.mem_total_gb * 0.8
    return round(max(0.0, min(available - 3.0, box.mem_total_gb * 0.70)), 2), "cpu"


def tokens_per_second(bandwidth_gbs: float | None, weights_gb: float) -> float | None:
    """CPU generation is memory-bandwidth bound: tokens/s ≈ bandwidth ÷ weight bytes."""
    if not weights_gb:
        return None
    bw = bandwidth_gbs if bandwidth_gbs else DEFAULT_BANDWIDTH_GBS
    return round(bw / weights_gb, 1)


_TIERS_CPU: list[tuple[float, str, str, float, str, int]] = [
    # (min budget GB, tier text, ceiling, suggested params B, quant, context)
    # budget = min(available - 3, 70 % of total): 8 GB -> ~3, 16 GB -> ~10, 32 GB -> ~22, 64 GB -> ~44
    (0.0, "under 8 GB of RAM, no GPU", "1–2B at Q4, 4k context", 1.5, "Q4_K_M", 4096),
    (4.0, "8–16 GB of RAM, no GPU", "3–4B at Q4_K_M, 8k context", 3.0, "Q4_K_M", 8192),
    (12.0, "16–32 GB of RAM, no GPU", "7–8B at Q4_K_M, 8k context (slow) or 3–4B comfortably", 3.0, "Q4_K_M", 8192),
    (
        24.0,
        "32 GB of RAM or more, no GPU",
        "12–14B at Q4_K_M, 8k context (slow) or 7–8B at a usable speed",
        8.0,
        "Q4_K_M",
        8192,
    ),
]

_TIERS_GPU: list[tuple[float, str, str, float, str, int]] = [
    (0.0, "a GPU under 6 GB", "1–2B at Q4, 4k context", 1.5, "Q4_K_M", 4096),
    (5.0, "a 6 GB GPU", "3–4B at Q4 fully offloaded, 8k context", 3.0, "Q4_K_M", 8192),
    (7.0, "an 8 GB GPU", "7–8B at Q4_K_M, 8k context", 8.0, "Q4_K_M", 8192),
    (11.0, "a 12 GB GPU", "8B at Q6/Q8 or 12–14B at Q4", 14.0, "Q4_K_M", 8192),
    (15.0, "a 16 GB GPU", "14B at Q5 or 24B at Q4", 14.0, "Q5_K_M", 8192),
    (23.0, "a 24 GB GPU", "27–32B at Q4_K_M, 16k context", 32.0, "Q4_K_M", 16384),
    (47.0, "a 48 GB GPU or more", "70B at Q4_K_M, 16k context", 70.0, "Q4_K_M", 16384),
]

_TIERS_APPLE: list[tuple[float, str, str, float, str, int]] = [
    (0.0, "Apple silicon with 8 GB", "3–4B at Q4, 8k context", 3.0, "Q4_K_M", 8192),
    (11.0, "Apple silicon with 16 GB", "7–8B at Q4, 8k context", 8.0, "Q4_K_M", 8192),
    (22.0, "Apple silicon with 32–64 GB", "14B–32B at Q4", 14.0, "Q4_K_M", 8192),
    (45.0, "Apple silicon with 64 GB or more", "70B at Q4", 70.0, "Q4_K_M", 16384),
]


def _pick(
    tiers: list[tuple[float, str, str, float, str, int]], budget: float
) -> tuple[float, str, str, float, str, int]:
    chosen = tiers[0]
    for tier in tiers:
        if budget >= tier[0]:
            chosen = tier
    return chosen


def recommend(box: Hardware) -> Recommendation:
    """The recommendation for ``box``."""
    budget, where = budget_gb(box)
    tiers = {"gpu": _TIERS_GPU, "apple": _TIERS_APPLE}.get(where, _TIERS_CPU)
    _, tier, ceiling, params_b, quant, context = _pick(tiers, budget)
    weights = weight_gb(params_b, quant)
    kv = kv_cache_gb(context)
    notes: list[str] = []
    speed = None
    if where == "cpu":
        speed = tokens_per_second(box.bandwidth_gbs, weights)
        if box.bandwidth_gbs is None:
            notes.append(
                f"Memory bandwidth unknown; the speed estimate assumes {DEFAULT_BANDWIDTH_GBS:.0f} GB/s "
                "(DDR4 dual-channel is about 40)."
            )
        if (
            "avx2" not in box.flags
            and "avx512f" not in box.flags
            and "neon" not in box.flags
            and "asimd" not in box.flags
            and box.flags
        ):
            notes.append("No AVX2 flag seen: expect well under the estimated speed.")
    elif where == "apple":
        speed = tokens_per_second(box.bandwidth_gbs or 100.0, weights)
        notes.append("Apple silicon shares memory between CPU and GPU; about 70 % of it is usable for the model.")
    else:
        gpu = max(box.gpus, key=lambda g: g.vram_gb)
        notes.append(f"{gpu.name or 'GPU'} with {gpu.vram_gb:.0f} GB; 0.8 GB kept for the driver and display.")
    notes.append(
        f"Suggested class at {quant}: about {weights:.1f} GB of weights plus {kv:.1f} GB of KV cache "
        f"for {context // 1024}k context (GQA assumed)."
    )
    if weights + kv > budget:
        notes.append("That is over the budget: drop the context or the parameter count.")
    suggest = {
        1.5: "a 1.5B instruct model; summaries only, keep OCR on Tesseract",
        3.0: "a 3–4B instruct model at Q4_K_M (the default class, about 10 tok/s on a CPU)",
        8.0: "a 7–8B instruct model at Q4_K_M",
        14.0: "a 12–14B instruct model at Q4_K_M",
        32.0: "a 27–32B instruct model at Q4_K_M",
        70.0: "a 70B instruct model at Q4_K_M",
    }.get(params_b, f"a {params_b:g}B instruct model at {quant}")
    return Recommendation(
        tier=tier,
        ceiling=ceiling,
        suggest=suggest,
        where=where,
        budget_gb=budget,
        params_b=params_b,
        quant=quant,
        context=context,
        tokens_per_s=speed,
        notes=notes,
    )


_CACHE: dict[str, t.Any] = {}
_LOCK = threading.Lock()
CACHE_SECONDS = 300


def report(force: bool = False) -> dict[str, t.Any]:
    """Hardware plus recommendation as plain data, cached for five minutes
    (reading the GPU tools on every page view would be wasteful)."""
    with _LOCK:
        now = time.monotonic()
        if not force and _CACHE and now - _CACHE["at"] < CACHE_SECONDS:
            return _CACHE["data"]
        hw = read_hardware()
        rec = recommend(hw)
        data = {
            "hardware": msgspec.to_builtins(hw),
            "recommendation": msgspec.to_builtins(rec),
        }
        _CACHE.update(at=now, data=data)
        return data
