#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""申威 / LSF 调度日志解析器。"""

import glob
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from perfbench.adapters.platform.logs import JobLogSummary, PlatformLogParser
from perfbench.utils.logger import get_logger

logger = get_logger()


def parse_perfbench_timestamp(time_stamp: str) -> Optional[datetime]:
    """将日志文件名中的 YYYYmmdd_HHMMSS 时间戳转为 datetime。"""
    try:
        return datetime.strptime(time_stamp, "%Y%m%d_%H%M%S")
    except (TypeError, ValueError):
        return None


class SunwayLogParser(PlatformLogParser):
    """解析申威 bjobs 日志。"""

    def parse_job_logs(self, out_dir: str, interval: int = 0) -> JobLogSummary:
        samples = self.parse_bjobs(out_dir)
        summary = JobLogSummary(samples=samples)
        if not samples:
            logger.warning("bjobs 数据为空")
            return summary

        for row in reversed(samples):
            if row.get("JobID") and summary.job_id is None:
                summary.job_id = row.get("JobID")
            if row.get("JobName") and summary.job_name is None:
                summary.job_name = row.get("JobName")
            if row.get("State") and summary.final_state is None:
                summary.final_state = row.get("State")
            if row.get("run_time"):
                try:
                    summary.elapsed_seconds = int(float(row["run_time"]))
                    break
                except (ValueError, TypeError):
                    pass

        if summary.elapsed_seconds is None:
            summary.elapsed_seconds = self.estimate_elapsed_time_from_states(samples)
            if summary.elapsed_seconds is not None:
                logger.info(
                    f"申威运行时间（秒，按 bjobs 状态采样估算）: "
                    f"{summary.elapsed_seconds}"
                )

        return summary

    def parse_bjobs(self, out_dir: str) -> List[Dict]:
        """
        解析 out_dir 下所有 bjobs_*.log 文件。

        兼容两类输出：
        - 表格型：JOBID STAT USER JOB_NAME QUEUE ...
        - 详细型：Job <id>, Job Name <name>, Status <state>, ...
        """
        pattern = os.path.join(out_dir, "bjobs_*.log")
        bjobs_files = sorted(glob.glob(pattern))
        if not bjobs_files:
            raise FileNotFoundError(f"未找到 bjobs 日志文件，模式: {pattern}")

        rows = []
        for file_path in bjobs_files:
            with open(file_path, 'r', encoding='utf-8') as handle:
                lines = [line.strip() for line in handle if line.strip()]

            if not lines:
                continue

            filename = os.path.basename(file_path)
            time_stamp = filename[6:-4]
            full_text = '\n'.join(lines)
            row = {
                "JobID": None,
                "JobName": None,
                "State": None,
                "run_time": None,
                "Memory": None,
                "time_stamp": time_stamp,
            }

            self._parse_bjobs_table(lines, row)
            self._parse_bjobs_detail(full_text, row)
            rows.append(row)

        return rows

    def estimate_elapsed_time_from_states(self, rows: List[Dict]) -> Optional[int]:
        """
        当 bjobs 日志没有运行时长字段时，用采样时间戳估算运行时间。

        申威文档确认的基础 bjobs 输出只包含 STAT，不保证提供 Run time 字段。
        """
        first_seen = None
        run_start = None
        end_time = None
        terminal_states = {"DONE", "EXIT", "CANCELED", "CANCELLED", "TERM"}

        for row in sorted(rows, key=lambda item: item.get("time_stamp") or ""):
            ts = parse_perfbench_timestamp(row.get("time_stamp"))
            if ts is None:
                continue
            if first_seen is None:
                first_seen = ts

            state = (row.get("State") or "").upper()
            if state == "RUN" and run_start is None:
                run_start = ts
            if state in terminal_states:
                end_time = ts

        start = run_start or first_seen
        if start is None or end_time is None or end_time < start:
            return None
        return int((end_time - start).total_seconds())

    def _parse_bjobs_table(self, lines: List[str], row: Dict) -> None:
        """
        解析申威文档确认的表格型 bjobs 输出：
            JOBID STAT USER JOB_NAME QUEUE FROM ...
            7546349 DONE swbuaa bash q_share sw_hpc_129 ...
        """
        for idx, line in enumerate(lines):
            if not (line.startswith("JOBID") and "STAT" in line):
                continue

            for data_line in lines[idx + 1:]:
                if not data_line or data_line.startswith("-"):
                    continue
                if data_line.startswith("###") or data_line.startswith("JOBID"):
                    continue

                parts = re.split(r'\s+', data_line.strip())
                if len(parts) < 5 or not parts[0].isdigit():
                    continue

                row["JobID"] = parts[0]
                row["State"] = parts[1]
                row["JobName"] = parts[3]
                row["Queue"] = parts[4]
                row["NodeList"] = parts[-1]
                return

    def _parse_bjobs_detail(self, full_text: str, row: Dict) -> None:
        """解析详细型 bjobs 文本，覆盖/补充表格字段。"""
        match = re.search(r'Job <(\d+)>', full_text)
        if match:
            row["JobID"] = match.group(1)

        match = re.search(r'Job Name <([^>]+)>', full_text)
        if match:
            row["JobName"] = match.group(1)

        match = re.search(r'Status <([^>]+)>', full_text)
        if match:
            row["State"] = match.group(1)

        match = re.search(r'Run time\s+[=:]?\s*(\d+)', full_text, re.IGNORECASE)
        if match:
            row["run_time"] = match.group(1)

        match = re.search(
            r'(?:Memory|Mem)\s+[=:]?\s*(\d+)\s*(?:MB|GB)?',
            full_text,
            re.IGNORECASE,
        )
        if match:
            row["Memory"] = match.group(1)
