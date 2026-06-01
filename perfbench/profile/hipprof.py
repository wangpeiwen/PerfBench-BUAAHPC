#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DTK hipprof backend for kernel dump and HIP trace runs."""

import csv
import json
import os
from typing import Iterable, List

from perfbench.profile.base import KernelProfileConfig, ProfileBackend, sh_quote
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


class HipprofBackend(ProfileBackend):
    """DCU/DTK backend using hipprof for HIP API trace and statistics."""

    def __init__(self, config: KernelProfileConfig):
        super().__init__(config)
        self.profile_options = ["--stats", "--hip-trace"]

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
        launcher_path = os.path.join(profile_dir, "perfbench_hipprof_launcher.sh")
        hipprof_dir = os.path.join(profile_dir, "hipprof")
        self._write_launcher(launcher_path, hipprof_dir)

        profile_script = os.path.join(profile_dir, "profile_script.slurm")
        setup_block = (
            "\n# PerfBench hipprof profile run metadata\n"
            "export PERFBENCH_PROFILE_RUN=1\n"
            f"export PERFBENCH_HIPPROF_OUTPUT_DIR={sh_quote(hipprof_dir)}\n"
        )
        lines = make_profile_lines(script_path, sh_quote(launcher_path), setup_block)
        return write_transformed_script(lines, profile_script)

    def parse_outputs(self, job_dir: str, profile_dir: str) -> dict:
        isa_path = os.path.join(profile_dir, "isa_static_summary.json")
        isa_summary = analyze_isa_dump(
            os.path.join(job_dir, "isa_dump"),
            output_path=isa_path,
        )

        hipprof_dir = os.path.join(profile_dir, "hipprof")
        summary = {
            "backend": "hipprof",
            "rank_scope": self.config.rank_scope,
            "profile_options": self.profile_options,
            "isa_dump": isa_summary,
            "hipprof": self._parse_hipprof_outputs(hipprof_dir),
            "errors": [],
            "notes": [
                "hipprof backend uses --stats --hip-trace by default",
                "--profile-counters is not mapped to hipprof PMC options",
            ],
        }

        summary_path = os.path.join(profile_dir, "kernel_profile_summary.json")
        os.makedirs(profile_dir, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
        return summary

    def _profile_dir(self, job_dir: str) -> str:
        return os.path.join(job_dir, self.config.output_subdir)

    def _write_launcher(self, launcher_path: str, hipprof_dir: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(launcher_path)), exist_ok=True)
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
  echo "[PerfBench] hipprof launcher received no target command" >&2
  exit 2
fi

{rank_guard}
if ! command -v hipprof >/dev/null 2>&1; then
  echo "[PerfBench] hipprof not found in PATH" >&2
  exit 127
fi

_PERFBENCH_HIPPROF_DIR={sh_quote(hipprof_dir)}
mkdir -p "$_PERFBENCH_HIPPROF_DIR"
_PERFBENCH_HOST="$(hostname -s 2>/dev/null || hostname)"
_PERFBENCH_RANK_LABEL="${{SLURM_PROCID:-${{OMPI_COMM_WORLD_RANK:-${{PMI_RANK:-0}}}}}}"
_PERFBENCH_OUT="perfbench_${{_PERFBENCH_HOST}}_rank${{_PERFBENCH_RANK_LABEL}}_pid$$.csv"

exec hipprof \\
  --stats \\
  --hip-trace \\
  -d "$_PERFBENCH_HIPPROF_DIR" \\
  -o "$_PERFBENCH_HIPPROF_DIR/$_PERFBENCH_OUT" \\
  "$@"
"""
        with open(launcher_path, "w", encoding="utf-8") as handle:
            handle.write(script)
        os.chmod(launcher_path, 0o755)
        return launcher_path

    def _parse_hipprof_outputs(self, hipprof_dir: str) -> dict:
        files = []
        csv_summaries = []
        for path in _iter_files(hipprof_dir):
            rel_path = os.path.relpath(path, hipprof_dir)
            file_info = {
                "file": rel_path,
                "size_bytes": os.path.getsize(path),
                "kind": _classify_file(path),
            }
            files.append(file_info)
            if path.lower().endswith(".csv"):
                csv_summaries.append(_summarize_csv(path, hipprof_dir))

        by_kind = {}
        for item in files:
            by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1

        return {
            "dir": hipprof_dir,
            "file_count": len(files),
            "by_kind": by_kind,
            "files": files,
            "csv_summaries": csv_summaries,
        }


def _iter_files(root: str) -> Iterable[str]:
    if not os.path.isdir(root):
        return []
    paths: List[str] = []
    for current_root, _, filenames in os.walk(root):
        for filename in filenames:
            paths.append(os.path.join(current_root, filename))
    return sorted(paths)


def _classify_file(path: str) -> str:
    name = os.path.basename(path).lower()
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".json"):
        return "json"
    if name.endswith(".db") or name.endswith(".sqlite"):
        return "database"
    if name.endswith(".html") or name.endswith(".htm"):
        return "html"
    return "other"


def _summarize_csv(path: str, base_dir: str) -> dict:
    row_count = 0
    columns = []
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        for _row in reader:
            row_count += 1
    return {
        "file": os.path.relpath(path, base_dir),
        "rows": row_count,
        "columns": columns,
    }
