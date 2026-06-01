#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for validating and rewriting profile-target scripts."""

import os
from typing import List, Optional

from perfbench.profile.base import PROFILE_TARGET_MARKER, PROFILE_TOKEN


class ProfileScriptError(ValueError):
    """Raised when a script cannot be safely transformed for profiling."""


def read_script_lines(script_path: str) -> List[str]:
    with open(script_path, "r", encoding="utf-8") as handle:
        return handle.readlines()


def validate_profile_markers(script_path: str) -> None:
    """Require exactly one target marker and one profile token."""
    lines = read_script_lines(script_path)
    marker_count = sum(1 for line in lines if line.strip() == PROFILE_TARGET_MARKER)
    token_count = sum(line.count(PROFILE_TOKEN) for line in lines)

    if marker_count != 1:
        raise ProfileScriptError(
            f"脚本必须包含且仅包含一个 {PROFILE_TARGET_MARKER} 标记"
        )
    if token_count != 1:
        raise ProfileScriptError(
            f"脚本必须包含且仅包含一个 {PROFILE_TOKEN} 占位符"
        )


def write_transformed_script(lines: List[str], output_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines))
    os.chmod(output_path, 0o755)
    return output_path


def insert_after_last_directive(lines: List[str], directive_prefix: str,
                                block: str) -> List[str]:
    """Insert a shell block after scheduler directives or after shebang."""
    if not lines or not lines[0].startswith("#!"):
        lines = ["#!/bin/bash\n"] + lines
    else:
        lines = list(lines)

    last_directive_idx = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith(directive_prefix):
            last_directive_idx = idx

    insert_pos = last_directive_idx + 1 if last_directive_idx != -1 else 1
    normalized = block
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    lines.insert(insert_pos, normalized)
    return lines


def make_formal_lines(script_path: str, env_block: str,
                      launcher_path: Optional[str] = None,
                      directive_prefix: str = "#SBATCH") -> List[str]:
    """Remove the profile token and inject formal-run environment setup."""
    validate_profile_markers(script_path)
    lines = read_script_lines(script_path)
    replacement = launcher_path or ""
    lines = [line.replace(PROFILE_TOKEN, replacement) for line in lines]
    return insert_after_last_directive(lines, directive_prefix, env_block)


def make_profile_lines(script_path: str, launcher_path: str,
                       setup_block: Optional[str] = None,
                       directive_prefix: str = "#SBATCH") -> List[str]:
    """Replace the profile token with the generated launcher path."""
    validate_profile_markers(script_path)
    lines = read_script_lines(script_path)
    lines = [line.replace(PROFILE_TOKEN, launcher_path) for line in lines]
    if setup_block:
        lines = insert_after_last_directive(lines, directive_prefix, setup_block)
    return lines
