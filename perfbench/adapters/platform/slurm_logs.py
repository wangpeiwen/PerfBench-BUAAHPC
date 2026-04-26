#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SLURM 调度日志解析器。"""

import glob
import os
from typing import Dict, List, Optional

from perfbench.adapters.platform.logs import JobLogSummary, PlatformLogParser
from perfbench.utils.logger import get_logger

logger = get_logger()


def parse_elapsed_string(elapsed_str: str) -> Optional[int]:
    """将 SLURM 的 HH:MM:SS 或 D-HH:MM:SS 转为秒。"""
    if not elapsed_str:
        return None

    elapsed_str = str(elapsed_str).strip()
    if '-' in elapsed_str:
        days, rest = elapsed_str.split('-', 1)
        parts = rest.split(':')
        if len(parts) != 3:
            return None
        hours, minutes, seconds = parts
        return (
            int(days) * 86400
            + int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
        )

    parts = elapsed_str.split(':')
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + int(seconds)
    return None


class SlurmLogParser(PlatformLogParser):
    """解析 SLURM sacct 日志。"""

    def parse_job_logs(self, out_dir: str, interval: int = 0) -> JobLogSummary:
        samples = self.parse_sacct(out_dir)
        summary = JobLogSummary(samples=samples)
        if not samples:
            logger.warning("sacct 数据为空")
            return summary

        last = samples[-1]
        summary.job_id = last.get("JobID")
        summary.job_name = last.get("JobName")
        summary.final_state = last.get("State")
        summary.elapsed_seconds = parse_elapsed_string(last.get("Elapsed"))
        if summary.elapsed_seconds is None:
            logger.warning(f"无法解析 SLURM Elapsed: {last.get('Elapsed')}")
        return summary

    def parse_sacct(self, out_dir: str) -> List[Dict]:
        """
        解析 out_dir 下所有 sacct_*.log 文件，并在存在时追加 final_sacct.log。

        日志格式（管道分隔）：
            JobID|JobName|State|Elapsed|MaxRSS|AllocCPUs
        """
        pattern = os.path.join(out_dir, "sacct_*.log")
        sacct_files = sorted(glob.glob(pattern))
        final_sacct = os.path.join(out_dir, "final_sacct.log")
        if os.path.exists(final_sacct):
            sacct_files.append(final_sacct)

        if not sacct_files:
            raise FileNotFoundError(f"未找到 sacct 日志文件，模式: {pattern}")

        rows = []
        for file_path in sacct_files:
            with open(file_path, 'r', encoding='utf-8') as handle:
                lines = [line.strip() for line in handle if line.strip()]

            if len(lines) <= 1:
                continue

            headers = [h.strip() for h in lines[0].split('|')]
            data = lines[1].split('|')
            filename = os.path.basename(file_path)
            if filename == "final_sacct.log":
                time_stamp = "final"
            else:
                time_stamp = filename[6:-4]

            row = {
                "JobID": None,
                "JobName": None,
                "State": None,
                "Elapsed": None,
                "MaxRSS": None,
                "AllocCPUS": None,
                "time_stamp": time_stamp,
            }
            for i, header in enumerate(headers):
                if i < len(data):
                    row[header] = data[i]

            rows.append(row)

        return rows
