#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
空加速卡监控器（No-op）。

用于无加速卡或不启用加速卡监控的场景，所有方法返回空值。
"""

from typing import Dict, List, Optional
from perfbench.adapters.accelerator.base import AcceleratorMonitor


class NullMonitor(AcceleratorMonitor):
    """无加速卡时的空实现，所有操作为 no-op。"""

    def generate_sampler_block(self, output_dir: str, interval: int) -> str:
        return ""

    def parse_logs(self, out_dir: str) -> List[Dict]:
        return []

    def get_summary(self, parsed_data: List[Dict]) -> Optional[Dict]:
        return None

    def get_log_subdir(self) -> str:
        return ""
