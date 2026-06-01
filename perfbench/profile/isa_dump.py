#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for formal-run HIP/ROCm ISA dump collection."""

import os

from perfbench.profile.base import sh_quote


def build_isa_dump_env_block(isa_dir: str) -> str:
    """Return environment setup used by formal kernel-profile runs."""
    return (
        "\n# PerfBench kernel ISA/code-object dump\n"
        f"mkdir -p {sh_quote(isa_dir)}\n"
        f"export PERFBENCH_ISA_DUMP_DIR={sh_quote(isa_dir)}\n"
        "export ROCM_DUMP_ISA=1\n"
        f"export ROCM_DUMP_ISA_DIR={sh_quote(isa_dir)}\n"
        "export GPU_DUMP_CODE_OBJECT=1\n"
        "export AMD_COMGR_SAVE_TEMPS=1\n"
        "export AMD_COMGR_EMIT_VERBOSE_LOGS=1\n"
        "export AMD_COMGR_REDIRECT_LOGS=stderr\n"
    )


def write_isa_dump_launcher(launcher_path: str, isa_dir: str) -> str:
    """Write a launcher that runs the target command and captures ISA inputs."""
    os.makedirs(os.path.dirname(os.path.abspath(launcher_path)), exist_ok=True)
    script = f"""#!/bin/bash
set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "[PerfBench] ISA dump launcher received no target command" >&2
  exit 2
fi

_PERFBENCH_ISA_DIR={sh_quote(isa_dir)}
_PERFBENCH_HOST="$(hostname -s 2>/dev/null || hostname)"
_PERFBENCH_RANK="${{SLURM_PROCID:-${{OMPI_COMM_WORLD_RANK:-${{PMI_RANK:-${{PMIX_RANK:-0}}}}}}}}"
_PERFBENCH_TAG="${{_PERFBENCH_HOST}}_rank${{_PERFBENCH_RANK}}_pid$$"
_PERFBENCH_RANK_DIR="${{_PERFBENCH_ISA_DIR}}/rank_${{_PERFBENCH_TAG}}"
_PERFBENCH_TMP_DIR="${{_PERFBENCH_RANK_DIR}}/tmp"
_PERFBENCH_MARKER="${{_PERFBENCH_RANK_DIR}}/before.marker"

mkdir -p "$_PERFBENCH_ISA_DIR" "$_PERFBENCH_RANK_DIR" "$_PERFBENCH_TMP_DIR"
: > "$_PERFBENCH_MARKER"

export PERFBENCH_ISA_DUMP_DIR="$_PERFBENCH_ISA_DIR"
export ROCM_DUMP_ISA=1
export ROCM_DUMP_ISA_DIR="$_PERFBENCH_ISA_DIR"
export GPU_DUMP_CODE_OBJECT=1
export AMD_COMGR_SAVE_TEMPS=1
export AMD_COMGR_EMIT_VERBOSE_LOGS=1
export AMD_COMGR_REDIRECT_LOGS=stderr
export TMPDIR="$_PERFBENCH_TMP_DIR"

_perfbench_disassemble_file() {{
  local input_file=$1
  local output_name=$2
  if ! command -v llvm-objdump >/dev/null 2>&1; then
    return 0
  fi
  llvm-objdump --offloading --disassemble "$input_file" \\
    > "$_PERFBENCH_ISA_DIR/${{output_name}}.isa" \\
    2> "$_PERFBENCH_ISA_DIR/${{output_name}}.err" ||
  llvm-objdump --triple=amdgcn-amd-amdhsa --disassemble "$input_file" \\
    > "$_PERFBENCH_ISA_DIR/${{output_name}}.isa" \\
    2>> "$_PERFBENCH_ISA_DIR/${{output_name}}.err" ||
  llvm-objdump --disassemble "$input_file" \\
    > "$_PERFBENCH_ISA_DIR/${{output_name}}.isa" \\
    2>> "$_PERFBENCH_ISA_DIR/${{output_name}}.err" || true

  if [ ! -s "$_PERFBENCH_ISA_DIR/${{output_name}}.isa" ]; then
    rm -f "$_PERFBENCH_ISA_DIR/${{output_name}}.isa"
  fi
}}

_perfbench_disassemble_target() {{
  local target=$1
  local resolved=""
  case "$target" in
    */*) resolved=$target ;;
    *) resolved=$(command -v "$target" 2>/dev/null || true) ;;
  esac
  if [ -n "$resolved" ] && [ -f "$resolved" ]; then
    _perfbench_disassemble_file "$resolved" "target_${{_PERFBENCH_TAG}}"
  fi
}}

_perfbench_copy_runtime_dumps() {{
  local source_dir=$1
  [ -d "$source_dir" ] || return 0
  find "$source_dir" -type f -newer "$_PERFBENCH_MARKER" \\
    \\( -name '*code_object*' -o -name '*.hsaco' -o -name '*.co' -o -name '*.o' \\) \\
    -exec cp -p {{}} "$_PERFBENCH_RANK_DIR/" \\; 2>/dev/null || true
}}

if [ "$_PERFBENCH_RANK" = "0" ]; then
  _perfbench_disassemble_target "$1"
fi

"$@"
_PERFBENCH_STATUS=$?

_perfbench_copy_runtime_dumps "$PWD"
_perfbench_copy_runtime_dumps "$_PERFBENCH_TMP_DIR"

if command -v llvm-objdump >/dev/null 2>&1; then
  for _PERFBENCH_OBJ in "$_PERFBENCH_RANK_DIR"/*; do
    [ -f "$_PERFBENCH_OBJ" ] || continue
    case "$_PERFBENCH_OBJ" in
      *.isa|*.err|*.marker) continue ;;
    esac
    _PERFBENCH_BASE=$(basename "$_PERFBENCH_OBJ")
    _perfbench_disassemble_file "$_PERFBENCH_OBJ" "dump_${{_PERFBENCH_TAG}}_${{_PERFBENCH_BASE}}"
  done
fi

exit "$_PERFBENCH_STATUS"
"""
    with open(launcher_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    os.chmod(launcher_path, 0o755)
    return launcher_path
