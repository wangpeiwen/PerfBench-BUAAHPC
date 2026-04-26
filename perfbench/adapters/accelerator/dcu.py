#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海光 DCU (hy-smi) 加速卡监控器。

封装 DCU 采样脚本生成、hy-smi 日志解析和摘要计算，使加速卡监控逻辑
与调度平台解耦。
"""

import os
import re
import glob
from typing import Dict, List, Optional
from perfbench.adapters.accelerator.base import AcceleratorMonitor
from perfbench.utils.logger import get_logger

logger = get_logger()


class DcuMonitor(AcceleratorMonitor):
    """海光 DCU 监控器，通过 hy-smi / rocm-smi 采集设备指标。"""

    def __init__(self, interval: Optional[int] = None):
        """
        Args:
            interval: DCU 专用采样间隔（秒），为 None 时由调用方传入全局 interval
        """
        self.interval = interval

    def get_log_subdir(self) -> str:
        return "dcu_logs"

    # ------------------------------------------------------------------
    # 采样代码生成
    # ------------------------------------------------------------------

    def generate_sampler_block(self, output_dir: str, interval: int) -> str:
        """
        生成 DCU (hy-smi) 采样器的 bash 注入块。

        通过 srun --overlap 在所有计算节点上启动后台采样循环，
        每节点写入独立日志文件到 {output_dir}/dcu_logs/。
        """
        actual_interval = self.interval if self.interval is not None else interval
        dcu_dir = f"{output_dir}/dcu_logs"
        return f"""
# ─────────────── PerfBench DCU 采样器 开始 ───────────────
_PERFBENCH_DCU_DIR="{dcu_dir}"
mkdir -p "$_PERFBENCH_DCU_DIR"
_PERFBENCH_NUM_NODES=${{SLURM_JOB_NUM_NODES:-1}}
srun --nodes=$_PERFBENCH_NUM_NODES --ntasks=$_PERFBENCH_NUM_NODES \\
     --ntasks-per-node=1 --overlap bash -c '
_NODE=$(hostname -s)
_LOGFILE="'"$_PERFBENCH_DCU_DIR"'""/dcu_hysmi_$_NODE.log"
echo "===== node: $_NODE =====" > "$_LOGFILE"
echo "start_time: $(date "+%F %T")" >> "$_LOGFILE"
_SAMPLE=0
while true; do
  _SAMPLE=$((_SAMPLE + 1))
  echo "" >> "$_LOGFILE"
  echo "----- sample $_SAMPLE | $(date "+%Y%m%d_%H%M%S") -----" >> "$_LOGFILE"
  hy-smi >> "$_LOGFILE" 2>&1 || \\
    rocm-smi >> "$_LOGFILE" 2>&1 || \\
    echo "[WARN] hy-smi/rocm-smi failed at sample $_SAMPLE" >> "$_LOGFILE"
  sleep {actual_interval}
done
' &
_PERFBENCH_DCU_PID=$!
echo $_PERFBENCH_DCU_PID > "{output_dir}/dcu_sampler.pid"
# ─────────────── PerfBench DCU 采样器 结束 ───────────────
"""

    # ------------------------------------------------------------------
    # 日志解析
    # ------------------------------------------------------------------

    def parse_logs(self, out_dir: str) -> List[Dict]:
        """
        解析 out_dir/dcu_logs/ 下所有 dcu_hysmi_*.log 文件。

        Returns:
            list[dict]: 每条记录为一个采样点的一个 DCU 设备
        """
        dcu_log_dir = os.path.join(out_dir, self.get_log_subdir())
        pattern = os.path.join(dcu_log_dir, "dcu_hysmi_*.log")
        hysmi_files = glob.glob(pattern)
        if not hysmi_files:
            raise FileNotFoundError(
                f"未找到 hy-smi 日志文件，模式: {pattern}"
            )

        data = []
        for file_path in hysmi_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            node_match = re.search(r'===== node: (\S+) =====', content)
            node_name = node_match.group(1) if node_match else "unknown"

            sample_blocks = re.split(
                r'----- sample (\d+) \| (\d{8}_\d{6}) -----',
                content
            )
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

                    data.append({
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

        return data

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def get_summary(self, parsed_data: List[Dict]) -> Optional[Dict]:
        """
        从 hy-smi 解析数据中提取 DCU 利用率摘要。

        Returns:
            dict: 包含平均/峰值 DCU 利用率、显存使用率、功耗、温度等；
                  数据为空时返回 None。
        """
        if not parsed_data:
            return None

        dcu_pcts, vram_pcts, powers, temps = [], [], [], []

        for row in parsed_data:
            if row.get("dcu_pct"):
                try:
                    dcu_pcts.append(float(row["dcu_pct"].rstrip('%')))
                except (ValueError, AttributeError):
                    pass
            if row.get("vram_pct"):
                try:
                    vram_pcts.append(float(row["vram_pct"].rstrip('%')))
                except (ValueError, AttributeError):
                    pass
            if row.get("avg_power"):
                try:
                    powers.append(float(row["avg_power"].rstrip('Ww')))
                except (ValueError, AttributeError):
                    pass
            if row.get("temp"):
                try:
                    temps.append(float(row["temp"].rstrip('cC')))
                except (ValueError, AttributeError):
                    pass

        if not dcu_pcts:
            return None

        nodes = set(row["node"] for row in parsed_data)
        samples = set((row["node"], row["time_stamp"]) for row in parsed_data)

        return {
            "avg_dcu_pct": sum(dcu_pcts) / len(dcu_pcts),
            "max_dcu_pct": max(dcu_pcts),
            "avg_vram_pct": sum(vram_pcts) / len(vram_pcts) if vram_pcts else 0.0,
            "avg_power": sum(powers) / len(powers) if powers else 0.0,
            "avg_temp": sum(temps) / len(temps) if temps else 0.0,
            "num_nodes": len(nodes),
            "total_samples": len(samples),
        }
