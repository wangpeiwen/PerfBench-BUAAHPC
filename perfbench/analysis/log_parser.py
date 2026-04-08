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
    "hysmi",
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
                elif self.cmd_name == "hysmi":
                    self.parse_hysmi()
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

    def get_elapsed_time(self) -> int | None:
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

    def _get_elapsed_time_slurm(self) -> int | None:
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

    def _get_elapsed_time_sunway(self) -> int | None:
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

    # ------------------------------------------------------------------
    # 海光 DCU (hy-smi) 日志解析
    # ------------------------------------------------------------------

    def parse_hysmi(self):
        """
        解析 out_dir/dcu_logs/ 下所有 dcu_hysmi_*.log 文件。

        日志格式（每个文件对应一个计算节点）：
            ===== node: node001 =====
            start_time: 2025-04-08 10:00:00

            ----- sample 1 | 20250408_100005 -----
            ==========================System Management Interface ====...
            ================================================================
            DCU  Temp   AvgPwr  SCLK     MCLK    Fan   Perf  PwrCap  VRAM%  DCU%
            1    48.0c  23.0W   1319Mhz  800Mhz  0.0%  auto  300.0W    0%   0%
            ...
            ================================================================
            =================================End of SMI Log==============...

        解析结果存入 self.data，每条记录为一个采样点的一个 DCU 设备。
        """
        dcu_log_dir = os.path.join(self.out_dir, "dcu_logs")
        pattern = os.path.join(dcu_log_dir, "dcu_hysmi_*.log")
        hysmi_files = glob.glob(pattern)
        if not hysmi_files:
            raise FileNotFoundError(
                f"未找到 hy-smi 日志文件，模式: {pattern}"
            )

        for file_path in hysmi_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 提取节点名
            node_match = re.search(r'===== node: (\S+) =====', content)
            node_name = node_match.group(1) if node_match else "unknown"

            # 按采样分隔符切分
            sample_blocks = re.split(
                r'----- sample (\d+) \| (\d{8}_\d{6}) -----',
                content
            )
            # split 结果: [前言, idx1, ts1, block1, idx2, ts2, block2, ...]
            i = 1
            while i + 2 < len(sample_blocks):
                sample_idx = int(sample_blocks[i])
                time_stamp = sample_blocks[i + 1]
                block_text = sample_blocks[i + 2]
                i += 3

                for line in block_text.splitlines():
                    line = line.strip()
                    if not line or line.startswith('=') or line.startswith('DCU'):
                        continue
                    parts = line.split()
                    if len(parts) < 9:
                        continue
                    try:
                        int(parts[0])
                    except ValueError:
                        continue

                    self.data.append({
                        "node": node_name,
                        "time_stamp": time_stamp,
                        "sample_idx": sample_idx,
                        "dcu_id": parts[0],
                        "temp": parts[1],
                        "avg_power": parts[2],
                        "sclk": parts[3],
                        "mclk": parts[4],
                        "fan": parts[5],
                        "perf": parts[6],
                        "power_cap": parts[7],
                        "vram_pct": parts[8] if len(parts) > 8 else None,
                        "dcu_pct": parts[9] if len(parts) > 9 else None,
                    })

    def get_dcu_summary(self) -> dict | None:
        """
        从 hy-smi 数据中提取 DCU 利用率摘要。

        Returns:
            dict: 包含平均/峰值 DCU 利用率、显存使用率、功耗、温度等汇总信息；
                  数据为空时返回 None。
        """
        if not self.data or self.cmd_name != "hysmi":
            return None

        dcu_pcts = []
        vram_pcts = []
        powers = []
        temps = []

        for row in self.data:
            # DCU 利用率: "0%" / "94%"
            if row.get("dcu_pct"):
                try:
                    dcu_pcts.append(float(row["dcu_pct"].rstrip('%')))
                except (ValueError, AttributeError):
                    pass
            # 显存使用率: "0%" / "85%"
            if row.get("vram_pct"):
                try:
                    vram_pcts.append(float(row["vram_pct"].rstrip('%')))
                except (ValueError, AttributeError):
                    pass
            # 功耗: "23.0W"
            if row.get("avg_power"):
                try:
                    powers.append(float(row["avg_power"].rstrip('Ww')))
                except (ValueError, AttributeError):
                    pass
            # 温度: "48.0c"
            if row.get("temp"):
                try:
                    temps.append(float(row["temp"].rstrip('cC')))
                except (ValueError, AttributeError):
                    pass

        if not dcu_pcts:
            return None

        nodes = set(row["node"] for row in self.data)
        samples = set((row["node"], row["time_stamp"]) for row in self.data)

        return {
            "avg_dcu_pct": sum(dcu_pcts) / len(dcu_pcts),
            "max_dcu_pct": max(dcu_pcts),
            "avg_vram_pct": sum(vram_pcts) / len(vram_pcts) if vram_pcts else 0.0,
            "avg_power": sum(powers) / len(powers) if powers else 0.0,
            "avg_temp": sum(temps) / len(temps) if temps else 0.0,
            "num_nodes": len(nodes),
            "total_samples": len(samples),
        }
