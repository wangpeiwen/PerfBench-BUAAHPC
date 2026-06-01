#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Profile backend interfaces and common kernel-profile configuration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


PROFILE_TARGET_MARKER = "# PERFBENCH_PROFILE_TARGET"
PROFILE_TOKEN = "__PERFBENCH_PROFILE__"


@dataclass
class KernelProfileConfig:
    """User-facing profile configuration normalized from CLI arguments."""

    backend: str = "rocprofv3"
    counters: Optional[str] = None
    rank_scope: str = "rank0"
    output_subdir: str = "kernel_profile"


class ProfileBackend(ABC):
    """Abstract profile backend used by the single-script flow."""

    def __init__(self, config: KernelProfileConfig):
        self.config = config

    @abstractmethod
    def preflight(self, script_path: str) -> None:
        """Validate user input before any scheduler job is submitted."""

    @abstractmethod
    def inject_formal_run(self, script_path: str, job_dir: str) -> str:
        """Create a formal-run script with low-overhead ISA dump enabled."""

    @abstractmethod
    def inject_profile_run(self, script_path: str, profile_dir: str) -> str:
        """Create a profile-only script and helper launcher."""

    @abstractmethod
    def parse_outputs(self, job_dir: str, profile_dir: str) -> dict:
        """Parse backend outputs and return a structured summary."""


def parse_counter_groups(counter_text: Optional[str]) -> List[str]:
    """Parse semicolon-separated counter groups for rocprof-like tools."""
    if not counter_text:
        return ["SQ_WAVES,GRBM_GUI_ACTIVE"]

    groups = []
    for group in counter_text.split(";"):
        counters = [
            item.strip()
            for item in group.split(",")
            if item.strip()
        ]
        if counters:
            groups.append(",".join(counters))
    return groups or ["SQ_WAVES,GRBM_GUI_ACTIVE"]


def sh_quote(value: str) -> str:
    """Quote a string for POSIX shell scripts."""
    return "'" + str(value).replace("'", "'\"'\"'") + "'"
