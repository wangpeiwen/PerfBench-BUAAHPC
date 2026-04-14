#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志解析器。

职责：从作业输出目录中读取调度命令产生的日志文件，解析为结构化字段。
不承担指标计算，不读取平台配置文件，不依赖调度命令（只读已有日志）。

支持的命令日志（supported_CMD）：
    sacct    - SLURM 作业统计（已实现）
    bjobs    - 申威作业状态（已实现）
    sstat    - SLURM 步骤级资源（空实现，待补全）
    sinfo    - SLURM 节点状态（空实现，待补全）
    seff     - SLURM 效率汇总（空实现，待补全）
    scontrol - SLURM 作业详情（空实现，待补全）
    cnload   - 申威负载（空实现，待补全）
"""

import os
import re
import glob
from datetime import datetime
from typing import Optional
from perfbench.utils.logger import get_logger

logger = get_logger()

# 当前已知的可解析命令列表（含空实现占位）
supported_CMD = [
    "sacct",
    "seff",
    "sinfo",
    "sstat",
    "scontrol",
    "bjobs",
    "cnload",
]


class Result:
    """
    作业结果解析中心。

    根据平台类型和命令名称，从 out_dir 中找到对应日志文件并解析为
    结构化数据列表（self.data），供上层提取运行时间等指标。

    Attributes:
        cmd_name (str):  对应的调度命令名称（如 "sacct" / "bjobs"）
        out_dir  (str):  日志文件所在目录
        interval (int):  监控采集间隔（秒）
        platform (str):  平台类型，"SLURM" 或 "Sunway"
        data     (list): 解析后的数据字典列表，每条含 time_stamp 字段
    """

    def __init__(self, cmd_name: str, out_dir: str, interval: int,
                 platform: str = "SLURM"):
        """
        Args:
            cmd_name: 该 Result 对象对应的命令名称
            out_dir:  本次测试中输出的日志文件存放路径
            interval: 监控间隔
            platform: 平台类型，可选 "SLURM" 或 "Sunway"
        """
        self.cmd_name = cmd_name
        self.out_dir = out_dir
        self.data = []
        self.interval = interval
        self.platform = platform
        self._parse_log_files()

    # ------------------------------------------------------------------
    # 内部：日志文件分发解析
    # ------------------------------------------------------------------

    def _parse_log_files(self):
        """
        根据平台类型和命令名称分发到对应的解析方法。
        """
        try:
            if self.platform == "Sunway":
                if self.cmd_name == "bjobs":
                    self.parse_bjobs()
                # 其他申威命令（cnload 等）待后续补全
            else:  # SLURM
                if self.cmd_name == "sacct":
                    self.parse_sacct()
                # sstat / sinfo / seff / scontrol 待后续补全
        except Exception as e:
            logger.error(f"日志文件解析失败: {e}")

    # ------------------------------------------------------------------
    # 公共辅助方法
    # ------------------------------------------------------------------

    def get_column_by_name(self, column_name: str) -> list:
        """
        返回带时间戳的指定列数据列表。

        Args:
            column_name: 数据字典中的字段名

        Returns:
            list[dict]: 每条含 {"time_stamp": ..., column_name: ...}
        """
        return [
            {"time_stamp": row["time_stamp"], column_name: row[column_name]}
            for row in self.data
        ]

    # ------------------------------------------------------------------
    # 运行时间提取
    # ------------------------------------------------------------------

    def get_elapsed_time(self) -> Optional[int]:
        """
        根据平台类型分发到对应的运行时间提取方法。

        Returns:
            int: 作业运行时间（秒）；无法提取时返回 None。
        """
        if self.platform == "Sunway" and self.cmd_name == "bjobs":
            return self._get_elapsed_time_sunway()
        if self.platform == "SLURM" and self.cmd_name == "sacct":
            return self._get_elapsed_time_slurm()
        logger.warning("正在尝试从错误的日志中提取作业完成时间信息")
        return None

    def _get_elapsed_time_slurm(self) -> Optional[int]:
        """提取 SLURM 平台的作业运行时间（秒）。"""
        if not self.data:
            logger.warning("sacct 数据为空")
            return None
        try:
            dt = datetime.strptime(self.data[-1]["Elapsed"], "%H:%M:%S")
            elapsed_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
            logger.info(f"SLURM 运行时间（秒）: {elapsed_seconds}")
            return elapsed_seconds
        except (KeyError, ValueError) as e:
            logger.warning(f"提取 SLURM 运行时间失败: {e}")
            return None

    def _get_elapsed_time_sunway(self) -> Optional[int]:
        """提取申威平台的作业运行时间（秒）。"""
        if not self.data:
            logger.warning("bjobs 数据为空")
            return None
        for row in reversed(self.data):
            if row.get("run_time"):
                try:
                    elapsed_seconds = int(float(row["run_time"]))
                    logger.info(f"申威运行时间（秒）: {elapsed_seconds}")
                    return elapsed_seconds
                except (ValueError, TypeError):
                    pass
        logger.warning("无法从 bjobs 数据提取运行时间")
        return None

    # ------------------------------------------------------------------
    # SLURM 日志解析（已实现）
    # ------------------------------------------------------------------

    def parse_sacct(self):
        """
        解析 out_dir 下所有 sacct_*.log 文件。

        日志格式（管道分隔）：
            JobID|JobName|State|Elapsed|MaxRSS|AllocCPUs
        """
        pattern = os.path.join(self.out_dir, "sacct_*.log")
        sacct_files = glob.glob(pattern)
        if not sacct_files:
            raise FileNotFoundError(
                f"未找到 sacct 日志文件，模式: {pattern}"
            )

        for file_path in sacct_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]

            if len(lines) <= 1:
                continue  # 跳过仅有表头或空文件

            headers = [h.strip() for h in lines[0].split('|')]
            data = lines[1].split('|')
            filename = os.path.basename(file_path)
            time_stamp = filename[6:-4]  # 去掉前缀 "sacct_" 和后缀 ".log"

            row_dict = {
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
                    row_dict[header] = data[i]

            self.data.append(row_dict)

    # ------------------------------------------------------------------
    # 申威日志解析（已实现）
    # ------------------------------------------------------------------

    def parse_bjobs(self):
        """
        解析 out_dir 下所有 bjobs_*.log 文件。

        bjobs -l 输出示例（多行自由文本）：
            Job <jobid>, Job Name <name>, Status <state>, ...
            Run time: <seconds>, ...
        """
        pattern = os.path.join(self.out_dir, "bjobs_*.log")
        bjobs_files = glob.glob(pattern)
        if not bjobs_files:
            raise FileNotFoundError(
                f"未找到 bjobs 日志文件，模式: {pattern}"
            )

        for file_path in bjobs_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]

            if not lines:
                continue

            filename = os.path.basename(file_path)
            time_stamp = filename[6:-4]  # 去掉前缀 "bjobs_" 和后缀 ".log"
            full_text = '\n'.join(lines)
            main_line = lines[0]

            row_dict = {
                "JobID": None,
                "JobName": None,
                "State": None,
                "run_time": None,
                "Memory": None,
                "time_stamp": time_stamp,
            }

            # 提取 JobID
            m = re.search(r'Job <(\d+)>', main_line)
            if m:
                row_dict["JobID"] = m.group(1)

            # 提取 JobName
            m = re.search(r'Job Name <([^>]+)>', main_line)
            if m:
                row_dict["JobName"] = m.group(1)

            # 提取状态
            m = re.search(r'Status <([^>]+)>', full_text)
            if m:
                row_dict["State"] = m.group(1)

            # 提取运行时间（秒）
            m = re.search(r'Run time\s+[=:]?\s*(\d+)', full_text, re.IGNORECASE)
            if m:
                row_dict["run_time"] = m.group(1)

            # 提取内存用量
            m = re.search(
                r'(?:Memory|Mem)\s+[=:]?\s*(\d+)\s*(?:MB|GB)?',
                full_text, re.IGNORECASE
            )
            if m:
                row_dict["Memory"] = m.group(1)

            self.data.append(row_dict)

    # ------------------------------------------------------------------
    # 空实现（占位，待后续补全）
    # ------------------------------------------------------------------

    def parse_sstat(self):
        """解析 sstat 日志（步骤级资源）。待补全。"""
        pass

    def parse_sinfo(self):
        """解析 sinfo 日志（集群节点状态）。待补全。"""
        pass

    def parse_seff(self):
        """解析 seff 日志（SLURM 效率汇总）。待补全。"""
        pass

    def parse_scontrol(self):
        """解析 scontrol 日志（作业详情）。待补全。"""
        pass
