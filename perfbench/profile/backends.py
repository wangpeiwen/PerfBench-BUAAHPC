#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Profile backend factory."""

from perfbench.profile.base import KernelProfileConfig, ProfileBackend
from perfbench.profile.rocprofv3 import RocprofV3Backend


def get_profile_backend(config: KernelProfileConfig) -> ProfileBackend:
    backend_name = (config.backend or "rocprofv3").strip().lower()
    if backend_name == "rocprofv3":
        return RocprofV3Backend(config)
    raise ValueError(f"不支持的 profile backend: {config.backend}")
