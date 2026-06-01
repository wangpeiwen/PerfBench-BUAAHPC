#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight static analysis for ROCm ISA dump text files."""

import json
import os
import re
from typing import Dict, Iterable, Optional


INSTRUCTION_RE = re.compile(r"^\s*(?:[0-9a-fA-F]+:\s*)?([a-zA-Z_][\w.]*)\b")
VGPR_RE = re.compile(r"(?:NumVgprs|VGPR(?:s)?|vgpr_count)\D+(\d+)", re.IGNORECASE)
SGPR_RE = re.compile(r"(?:NumSgprs|SGPR(?:s)?|sgpr_count)\D+(\d+)", re.IGNORECASE)
LDS_RE = re.compile(
    r"(?:GroupSegmentFixedSize|LDS(?:Size)?|lds_size)\D+(\d+)",
    re.IGNORECASE,
)


def analyze_isa_dump(isa_dir: str, output_path: Optional[str] = None) -> dict:
    """Analyze every regular file below ``isa_dir`` and optionally write JSON."""
    files = list(_iter_files(isa_dir))
    kernel_summaries = [_analyze_file(path, isa_dir) for path in files]
    totals = _aggregate(kernel_summaries)
    summary = {
        "isa_dir": isa_dir,
        "file_count": len(files),
        "kernels": kernel_summaries,
        "totals": totals,
    }

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)

    return summary


def _iter_files(root: str) -> Iterable[str]:
    if not os.path.isdir(root):
        return []
    paths = []
    for current_root, _, filenames in os.walk(root):
        for filename in filenames:
            path = os.path.join(current_root, filename)
            if os.path.isfile(path):
                paths.append(path)
    return sorted(paths)


def _analyze_file(path: str, base_dir: str) -> dict:
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        text = handle.read()

    categories = {
        "valu": 0,
        "salu": 0,
        "vmem": 0,
        "smem": 0,
        "lds": 0,
        "branch": 0,
        "barrier": 0,
        "other": 0,
    }
    instruction_count = 0

    for line in text.splitlines():
        opcode = _extract_opcode(line)
        if not opcode:
            continue
        instruction_count += 1
        categories[_classify_opcode(opcode)] += 1

    mix = {
        key: (value / instruction_count if instruction_count else 0.0)
        for key, value in categories.items()
    }

    vgpr = _extract_first_int(VGPR_RE, text)
    sgpr = _extract_first_int(SGPR_RE, text)
    lds = _extract_first_int(LDS_RE, text)

    return {
        "kernel": _kernel_name_from_path(path),
        "file": os.path.relpath(path, base_dir),
        "size_bytes": os.path.getsize(path),
        "instruction_count": instruction_count,
        "categories": categories,
        "mix": mix,
        "metadata": {
            "vgpr_count": vgpr,
            "sgpr_count": sgpr,
            "lds_bytes": lds,
        },
        "hints": _build_hints(mix, vgpr, sgpr, lds),
    }


def _extract_opcode(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "//", ";", ".")):
        return None
    match = INSTRUCTION_RE.match(stripped)
    if not match:
        return None
    opcode = match.group(1)
    if opcode.endswith(":"):
        return None
    return opcode.lower()


def _classify_opcode(opcode: str) -> str:
    if opcode.startswith(("s_cbranch", "s_branch", "s_setpc", "s_swappc")):
        return "branch"
    if opcode.startswith(("s_barrier", "s_waitcnt", "s_sleep")):
        return "barrier"
    if opcode.startswith(("global_", "buffer_", "flat_", "scratch_")):
        return "vmem"
    if opcode.startswith(("s_load", "s_buffer_load", "s_dcache", "s_mem")):
        return "smem"
    if opcode.startswith("ds_"):
        return "lds"
    if opcode.startswith("v_"):
        return "valu"
    if opcode.startswith("s_"):
        return "salu"
    return "other"


def _extract_first_int(pattern: re.Pattern, text: str) -> Optional[int]:
    match = pattern.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _kernel_name_from_path(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _build_hints(mix: Dict[str, float], vgpr: Optional[int],
                 sgpr: Optional[int], lds: Optional[int]) -> dict:
    memory_mix = mix.get("vmem", 0.0) + mix.get("smem", 0.0) + mix.get("lds", 0.0)
    control_mix = mix.get("branch", 0.0)
    sync_mix = mix.get("barrier", 0.0)

    return {
        "compute_intensity": _level(mix.get("valu", 0.0), 0.45, 0.25),
        "memory_intensity": _level(memory_mix, 0.30, 0.15),
        "control_flow": _level(control_mix, 0.08, 0.03),
        "sync_pressure": _level(sync_mix, 0.06, 0.02),
        "register_pressure": _register_pressure(vgpr, sgpr),
        "lds_pressure": _level(float(lds or 0), 32768.0, 8192.0),
    }


def _level(value: float, high: float, medium: float) -> str:
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"


def _register_pressure(vgpr: Optional[int], sgpr: Optional[int]) -> str:
    if (vgpr is not None and vgpr >= 96) or (sgpr is not None and sgpr >= 96):
        return "high"
    if (vgpr is not None and vgpr >= 64) or (sgpr is not None and sgpr >= 64):
        return "medium"
    if vgpr is None and sgpr is None:
        return "unknown"
    return "low"


def _aggregate(kernels: list) -> dict:
    categories = {
        "valu": 0,
        "salu": 0,
        "vmem": 0,
        "smem": 0,
        "lds": 0,
        "branch": 0,
        "barrier": 0,
        "other": 0,
    }
    instruction_count = 0
    for kernel in kernels:
        instruction_count += kernel.get("instruction_count", 0)
        for key in categories:
            categories[key] += kernel.get("categories", {}).get(key, 0)

    mix = {
        key: (value / instruction_count if instruction_count else 0.0)
        for key, value in categories.items()
    }
    return {
        "instruction_count": instruction_count,
        "categories": categories,
        "mix": mix,
    }
