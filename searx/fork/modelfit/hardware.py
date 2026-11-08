# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the box has: CPU, memory, GPUs.  Read from ``/proc``, the vendors'
command-line tools and (on a Mac) ``system_profiler``; or from an override
file an orchestrator writes from the host, because inside a container the
GPU tools exist only when the device was passed through.

Every reader is a pure parser over text, so the tests feed it fixtures; the
collector around them is the only part that touches the system.
"""

from __future__ import annotations

__all__ = [
    "Gpu",
    "Hardware",
    "read_hardware",
    "parse_cpuinfo",
    "parse_meminfo",
    "parse_nvidia_smi",
    "parse_rocm_smi",
    "parse_system_profiler",
    "parse_override",
]

import json
import os
import platform
import re
import shutil
import subprocess
import typing as t

import msgspec

OVERRIDE_PATH = "/etc/searxng/hardware.json"
GB = 1024**3


class Gpu(msgspec.Struct, kw_only=True):  # pylint: disable=too-few-public-methods
    """One graphics card and its memory."""

    vendor: str = ""
    """``nvidia``, ``amd``, ``apple`` or ``intel``."""
    name: str = ""
    vram_gb: float = 0.0
    used_gb: float = 0.0


class Hardware(msgspec.Struct, kw_only=True):  # pylint: disable=too-few-public-methods
    """A box's resources, in GB (1024³ bytes)."""

    cpu_model: str = ""
    cores: int = 0
    flags: list[str] = []
    """The instruction-set flags that matter for inference: avx2, avx512, amx, neon."""
    mem_total_gb: float = 0.0
    mem_available_gb: float = 0.0
    gpus: list[Gpu] = []
    apple_unified: bool = False
    """Apple silicon: the GPU shares the RAM, of which about 70 % is usable."""
    bandwidth_gbs: float | None = None
    """Memory bandwidth in GB/s when it could be estimated, else ``None``."""
    sources: list[str] = []
    """Where each figure came from, for the panel's honesty line."""


_INTERESTING_FLAGS = ("avx2", "avx512f", "avx512_bf16", "amx_tile", "neon", "asimd", "sse4_2")


def parse_cpuinfo(text: str) -> dict[str, t.Any]:
    """``model name``, logical core count and the interesting flags from ``/proc/cpuinfo``."""
    model = ""
    cores = 0
    flags: set[str] = set()
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "model name" and not model:
            model = value
        elif key == "processor":
            cores += 1
        elif key in ("flags", "features"):
            for flag in value.split():
                if flag in _INTERESTING_FLAGS:
                    flags.add(flag)
    return {"cpu_model": model, "cores": cores, "flags": sorted(flags)}


def parse_meminfo(text: str) -> dict[str, float]:
    """``MemTotal`` and ``MemAvailable`` (kB in the file) as GB."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        if key in ("MemTotal", "MemAvailable"):
            number = value.strip().split()[0] if value.strip() else "0"
            try:
                out[key] = round(int(number) * 1024 / GB, 2)
            except ValueError:
                pass
    return {"mem_total_gb": out.get("MemTotal", 0.0), "mem_available_gb": out.get("MemAvailable", 0.0)}


def parse_nvidia_smi(text: str) -> list[Gpu]:
    """``nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits`` (MiB)."""
    gpus: list[Gpu] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2 or not parts[0]:
            continue
        try:
            total = float(parts[1]) * 1024**2 / GB
            used = float(parts[2]) * 1024**2 / GB if len(parts) > 2 and parts[2] else 0.0
        except ValueError:
            continue
        gpus.append(Gpu(vendor="nvidia", name=parts[0], vram_gb=round(total, 2), used_gb=round(used, 2)))
    return gpus


def parse_rocm_smi(text: str) -> list[Gpu]:
    """``rocm-smi --showmeminfo vram --json``:
    ``{"card0": {"VRAM Total Memory (B)": "...", "VRAM Total Used Memory (B)": "..."}}``."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    gpus: list[Gpu] = []
    if not isinstance(data, dict):
        return gpus
    for card, fields in sorted(data.items()):
        if not isinstance(fields, dict):
            continue
        total = used = 0.0
        for key, value in fields.items():
            lowered = key.lower()
            try:
                number = float(str(value).strip())
            except ValueError:
                continue
            if "total memory" in lowered and "used" not in lowered:
                total = number / GB
            elif "used memory" in lowered:
                used = number / GB
        if total:
            gpus.append(
                Gpu(
                    vendor="amd",
                    name=str(fields.get("Card series") or fields.get("Card Series") or card),
                    vram_gb=round(total, 2),
                    used_gb=round(used, 2),
                )
            )
    return gpus


_APPLE_MEM = re.compile(r"Memory:\s*([\d.]+)\s*GB", re.I)
_APPLE_CHIP = re.compile(r"Chip:\s*(.+)", re.I)
_APPLE_CORES = re.compile(r"Total Number of Cores:\s*(\d+)", re.I)


def parse_system_profiler(text: str) -> dict[str, t.Any]:
    """Chip, cores and unified memory from ``system_profiler SPHardwareDataType``."""
    out: dict[str, t.Any] = {}
    m = _APPLE_CHIP.search(text)
    if m:
        out["cpu_model"] = m.group(1).strip()
    m = _APPLE_CORES.search(text)
    if m:
        out["cores"] = int(m.group(1))
    m = _APPLE_MEM.search(text)
    if m:
        out["mem_total_gb"] = float(m.group(1))
    return out


def parse_override(text: str) -> Hardware | None:
    """An orchestrator's ``hardware.json``: ``{"cpu": {"model", "cores", "flags"},
    "memory": {"total_gb", "available_gb"}, "gpus": [{"vendor", "name", "vram_gb", "used_gb"}],
    "apple_unified": bool, "bandwidth_gbs": number}``.  Every key is optional."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    cpu: dict[str, t.Any] = data["cpu"] if isinstance(data.get("cpu"), dict) else {}
    mem: dict[str, t.Any] = data["memory"] if isinstance(data.get("memory"), dict) else {}
    gpus: list[Gpu] = []
    for g in data.get("gpus") or []:
        if isinstance(g, dict):
            try:
                gpus.append(
                    Gpu(
                        vendor=str(g.get("vendor") or ""),
                        name=str(g.get("name") or ""),
                        vram_gb=float(g.get("vram_gb") or 0),
                        used_gb=float(g.get("used_gb") or 0),
                    )
                )
            except (TypeError, ValueError):
                continue
    bandwidth = data.get("bandwidth_gbs")
    try:
        hw = Hardware(
            cpu_model=str(cpu.get("model") or ""),
            cores=int(cpu.get("cores") or 0),
            flags=[str(f) for f in (cpu.get("flags") or [])],
            mem_total_gb=float(mem.get("total_gb") or 0),
            mem_available_gb=float(mem.get("available_gb") or 0),
            gpus=gpus,
            apple_unified=bool(data.get("apple_unified", False)),
            bandwidth_gbs=float(bandwidth) if bandwidth not in (None, "") else None,
            sources=["override file"],
        )
    except (TypeError, ValueError):
        return None
    return hw


def _run(cmd: list[str], timeout: float = 5.0) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _read_cpu_and_memory(box: Hardware) -> None:
    cpuinfo = _read("/proc/cpuinfo")
    if cpuinfo:
        cpu = parse_cpuinfo(cpuinfo)
        box.cpu_model, box.cores, box.flags = cpu["cpu_model"], cpu["cores"], cpu["flags"]
        box.sources.append("/proc/cpuinfo")
    meminfo = _read("/proc/meminfo")
    if meminfo:
        mem = parse_meminfo(meminfo)
        box.mem_total_gb, box.mem_available_gb = mem["mem_total_gb"], mem["mem_available_gb"]
        box.sources.append("/proc/meminfo")
    if not box.cores:
        box.cores = os.cpu_count() or 0
    if not box.cpu_model:
        box.cpu_model = platform.processor() or platform.machine()
    if not box.mem_total_gb:
        try:
            box.mem_total_gb = round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / GB, 2)
            box.sources.append("sysconf")
        except (ValueError, OSError, AttributeError):
            pass


def _read_gpus(box: Hardware) -> None:
    nvidia = _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"])
    if nvidia:
        box.gpus.extend(parse_nvidia_smi(nvidia))
        box.sources.append("nvidia-smi")
    rocm = _run(["rocm-smi", "--showmeminfo", "vram", "--json"])
    if rocm:
        box.gpus.extend(parse_rocm_smi(rocm))
        box.sources.append("rocm-smi")


def _read_apple(box: Hardware) -> None:
    if platform.system() != "Darwin":
        return
    profile = _run(["system_profiler", "SPHardwareDataType"], timeout=15)
    if not profile:
        return
    apple = parse_system_profiler(profile)
    box.cpu_model = apple.get("cpu_model") or box.cpu_model
    box.cores = apple.get("cores") or box.cores
    box.mem_total_gb = apple.get("mem_total_gb") or box.mem_total_gb
    box.apple_unified = "apple" in box.cpu_model.lower()
    box.sources.append("system_profiler")


def read_hardware(override_path: str = OVERRIDE_PATH) -> Hardware:
    """Collect what can be read on this host.  An override file wins outright."""
    override = _read(override_path)
    if override:
        box = parse_override(override)
        if box is not None:
            return box
    box = Hardware()
    _read_cpu_and_memory(box)
    _read_gpus(box)
    _read_apple(box)
    if not box.mem_available_gb and box.mem_total_gb:
        box.mem_available_gb = round(box.mem_total_gb * 0.8, 2)
    return box
