#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROCm rocprofv3 backend for kernel dump and profile runs."""

import csv
import json
import os
from typing import Dict, Iterable, List, Optional

from perfbench.profile.base import (
    KernelProfileConfig,
    ProfileBackend,
    parse_counter_groups,
    sh_quote,
)
from perfbench.profile.isa_dump import (
    build_isa_dump_env_block,
    write_isa_dump_launcher,
)
from perfbench.profile.isa_analyzer import analyze_isa_dump
from perfbench.profile.script_transform import (
    make_formal_lines,
    make_profile_lines,
    validate_profile_markers,
    write_transformed_script,
)


class RocprofV3Backend(ProfileBackend):
    """Initial DCU/ROCm backend using rocprofv3."""

    def __init__(self, config: KernelProfileConfig):
        super().__init__(config)
        self.counter_groups = parse_counter_groups(config.counters)

    def preflight(self, script_path: str) -> None:
        validate_profile_markers(script_path)
        if self.config.rank_scope not in ("rank0", "all"):
            raise ValueError("--profile-rank-scope 仅支持 rank0 或 all")

    def inject_formal_run(self, script_path: str, job_dir: str) -> str:
        profile_dir = self._profile_dir(job_dir)
        isa_dir = os.path.join(job_dir, "isa_dump")
        launcher_path = os.path.join(profile_dir, "perfbench_isa_dump_launcher.sh")
        write_isa_dump_launcher(launcher_path, isa_dir)
        formal_script = os.path.join(profile_dir, "formal_script.slurm")
        env_block = build_isa_dump_env_block(isa_dir)
        lines = make_formal_lines(script_path, env_block, sh_quote(launcher_path))
        return write_transformed_script(lines, formal_script)

    def inject_profile_run(self, script_path: str, profile_dir: str) -> str:
        launcher_path = os.path.join(profile_dir, "perfbench_profile_launcher.sh")
        rocprof_dir = os.path.join(profile_dir, "rocprof")
        self._write_launcher(launcher_path, rocprof_dir)

        profile_script = os.path.join(profile_dir, "profile_script.slurm")
        setup_block = (
            "\n# PerfBench kernel profile run metadata\n"
            f"export PERFBENCH_PROFILE_RUN=1\n"
            f"export PERFBENCH_ROCPROF_OUTPUT_DIR={sh_quote(rocprof_dir)}\n"
        )
        lines = make_profile_lines(script_path, sh_quote(launcher_path), setup_block)
        return write_transformed_script(lines, profile_script)

    def parse_outputs(self, job_dir: str, profile_dir: str) -> dict:
        isa_path = os.path.join(profile_dir, "isa_static_summary.json")
        isa_summary = analyze_isa_dump(
            os.path.join(job_dir, "isa_dump"),
            output_path=isa_path,
        )

        rocprof_dir = os.path.join(profile_dir, "rocprof")
        profile_outputs = self._parse_rocprof_outputs(rocprof_dir)
        summary = {
            "backend": "rocprofv3",
            "rank_scope": self.config.rank_scope,
            "counter_groups": self.counter_groups,
            "isa_dump": isa_summary,
            "rocprof": profile_outputs,
            "errors": [],
        }

        summary_path = os.path.join(profile_dir, "kernel_profile_summary.json")
        os.makedirs(profile_dir, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
        return summary

    def _profile_dir(self, job_dir: str) -> str:
        return os.path.join(job_dir, self.config.output_subdir)

    def _write_launcher(self, launcher_path: str, rocprof_dir: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(launcher_path)), exist_ok=True)
        counter_args = self._counter_args_text()
        rank_guard = ""
        if self.config.rank_scope == "rank0":
            rank_guard = """
_PERFBENCH_RANK="${SLURM_PROCID:-${OMPI_COMM_WORLD_RANK:-${PMI_RANK:-0}}}"
if [ "$_PERFBENCH_RANK" != "0" ]; then
  exec "$@"
fi
"""

        script = f"""#!/bin/bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "[PerfBench] profile launcher received no target command" >&2
  exit 2
fi

{rank_guard}
if ! command -v rocprofv3 >/dev/null 2>&1; then
  echo "[PerfBench] rocprofv3 not found in PATH" >&2
  exit 127
fi

_PERFBENCH_ROCPROF_DIR={sh_quote(rocprof_dir)}
mkdir -p "$_PERFBENCH_ROCPROF_DIR"
_PERFBENCH_HOST="$(hostname -s 2>/dev/null || hostname)"
_PERFBENCH_RANK_LABEL="${{SLURM_PROCID:-${{OMPI_COMM_WORLD_RANK:-${{PMI_RANK:-0}}}}}}"
_PERFBENCH_OUT="perfbench_${{_PERFBENCH_HOST}}_rank${{_PERFBENCH_RANK_LABEL}}_pid$$"

exec rocprofv3 \\
  --kernel-trace \\
  --stats \\
  --output-directory "$_PERFBENCH_ROCPROF_DIR" \\
  --output-file "$_PERFBENCH_OUT" \\
  --output-format csv \\
{counter_args}  -- "$@"
"""
        with open(launcher_path, "w", encoding="utf-8") as handle:
            handle.write(script)
        os.chmod(launcher_path, 0o755)
        return launcher_path

    def _counter_args_text(self) -> str:
        if not self.counter_groups:
            return ""
        parts = []
        for group in self.counter_groups:
            parts.append(f"--pmc {sh_quote(group)}")
        return "  " + " \\\n  ".join(parts) + " \\\n"

    def _parse_rocprof_outputs(self, rocprof_dir: str) -> dict:
        csv_files = list(_iter_csv_files(rocprof_dir))
        files = []
        kernels: Dict[str, dict] = {}
        for path in csv_files:
            file_summary = self._parse_csv_file(path, rocprof_dir, kernels)
            files.append(file_summary)

        return {
            "dir": rocprof_dir,
            "file_count": len(csv_files),
            "files": files,
            "kernels": sorted(kernels.values(), key=lambda item: item["kernel"]),
        }

    def _parse_csv_file(self, path: str, base_dir: str,
                        kernels: Dict[str, dict]) -> dict:
        row_count = 0
        columns: List[str] = []
        with open(path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            for row in reader:
                row_count += 1
                kernel_name = _extract_kernel_name(row)
                if kernel_name:
                    _merge_kernel_row(kernels, kernel_name, row)

        return {
            "file": os.path.relpath(path, base_dir),
            "rows": row_count,
            "columns": columns,
        }


def _iter_csv_files(root: str) -> Iterable[str]:
    if not os.path.isdir(root):
        return []
    paths = []
    for current_root, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.lower().endswith(".csv"):
                paths.append(os.path.join(current_root, filename))
    return sorted(paths)


def _extract_kernel_name(row: dict) -> Optional[str]:
    candidates = (
        "KernelName",
        "Kernel_Name",
        "Kernel Name",
        "kernel_name",
        "Kernel",
        "Name",
        "Name_ID",
    )
    for key in candidates:
        value = row.get(key)
        if value:
            return str(value).strip()
    return None


def _merge_kernel_row(kernels: Dict[str, dict], kernel_name: str, row: dict) -> None:
    entry = kernels.setdefault(
        kernel_name,
        {
            "kernel": kernel_name,
            "samples": 0,
            "metrics": {},
        },
    )
    entry["samples"] += 1

    for key, value in row.items():
        number = _parse_float(value)
        if number is None:
            continue
        metric = entry["metrics"].setdefault(
            key,
            {
                "count": 0,
                "sum": 0.0,
                "min": number,
                "max": number,
            },
        )
        metric["count"] += 1
        metric["sum"] += number
        metric["min"] = min(metric["min"], number)
        metric["max"] = max(metric["max"], number)

    for metric in entry["metrics"].values():
        metric["mean"] = (
            metric["sum"] / metric["count"]
            if metric["count"]
            else None
        )


def _parse_float(value) -> Optional[float]:
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None
