#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迈创 Matrix 加速卡监控器。

通过 matrix-smi 采集天河迈创平台加速卡指标（利用率、显存、功耗、温度）。
采样块不依赖 srun，改用 $HOSTFILE 遍历方式在多节点启动后台采样。
"""

import os
import re
import glob
from typing import Dict, List, Optional
from perfbench.adapters.accelerator.base import AcceleratorMonitor
from perfbench.utils.logger import get_logger

logger = get_logger()


class MatrixMonitor(AcceleratorMonitor):
    """迈创 Matrix 加速卡监控器，通过 matrix-smi 采集设备指标。"""

    def __init__(self, interval: Optional[int] = None):
        """
        Args:
            interval: Matrix 专用采样间隔（秒），为 None 时由调用方传入全局 interval
        """
        self.interval = interval

    def get_log_subdir(self) -> str:
        return "matrix_logs"

    # ------------------------------------------------------------------
    # 采样代码生成
    # ------------------------------------------------------------------

    def generate_sampler_block(self, output_dir: str, interval: int) -> str:
        """
        生成 matrix-smi 采样器的 bash 注入块。

        通过读取 $HOSTFILE（天河调度系统提供）在所有计算节点上
        启动后台 matrix-smi 采样循环，每节点写入独立日志文件。
        若 $HOSTFILE 不存在则仅在本地节点采集。
        """
        actual_interval = self.interval if self.interval is not None else interval
        matrix_dir = f"{output_dir}/matrix_logs"
        return f"""
# ─────────────── PerfBench Matrix 采样器 开始 ───────────────
_PERFBENCH_MATRIX_DIR="{matrix_dir}"
mkdir -p "$_PERFBENCH_MATRIX_DIR"

_perfbench_matrix_sampler() {{
  _NODE=$(hostname -s)
  _LOGFILE="${{_PERFBENCH_MATRIX_DIR}}/matrix_smi_${{_NODE}}.log"
  echo "===== node: $_NODE =====" > "$_LOGFILE"
  echo "start_time: $(date "+%F %T")" >> "$_LOGFILE"
  _SAMPLE=0
  while true; do
    _SAMPLE=$((_SAMPLE + 1))
    echo "" >> "$_LOGFILE"
    echo "----- sample $_SAMPLE | $(date "+%Y%m%d_%H%M%S") -----" >> "$_LOGFILE"
    matrix-smi >> "$_LOGFILE" 2>&1 || \\
      echo "[WARN] matrix-smi failed at sample $_SAMPLE" >> "$_LOGFILE"
    sleep {actual_interval}
  done
}}

if [ -n "${{HOSTFILE:-}}" ] && [ -f "$HOSTFILE" ]; then
  # 多节点：通过 ssh 在每个节点启动采样
  _PERFBENCH_MATRIX_PIDS=""
  while IFS= read -r _HOST; do
    _HOST=$(echo "$_HOST" | awk '{{print $1}}')
    [ -z "$_HOST" ] && continue
    ssh "$_HOST" "bash -c '$(declare -f _perfbench_matrix_sampler); \\
      _PERFBENCH_MATRIX_DIR={matrix_dir}; _perfbench_matrix_sampler'" &
    _PERFBENCH_MATRIX_PIDS="$_PERFBENCH_MATRIX_PIDS $!"
  done < "$HOSTFILE"
  echo $_PERFBENCH_MATRIX_PIDS > "{output_dir}/matrix_sampler.pid"
else
  # 单节点：本地启动
  _perfbench_matrix_sampler &
  echo $! > "{output_dir}/matrix_sampler.pid"
fi
# ─────────────── PerfBench Matrix 采样器 结束 ───────────────
"""

    # ------------------------------------------------------------------
    # 日志解析
    # ------------------------------------------------------------------

    def parse_logs(self, out_dir: str) -> List[Dict]:
        """
        解析 out_dir/matrix_logs/ 下所有 matrix_smi_*.log 文件。

        matrix-smi 输出格式（预期）：
        每个设备一行，字段包含 ID、温度、功耗、显存使用、利用率等。
        具体列顺序可能因固件版本不同而异，此处按通用表格行解析。

        Returns:
            list[dict]: 每条记录为一个采样点的一个 Matrix 设备
        """
        log_dir = os.path.join(out_dir, self.get_log_subdir())
        pattern = os.path.join(log_dir, "matrix_smi_*.log")
        log_files = glob.glob(pattern)
        if not log_files:
            raise FileNotFoundError(
                f"未找到 matrix-smi 日志文件，模式: {pattern}"
            )

        data = []
        for file_path in log_files:
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
                    # 跳过空行、分隔线、表头
                    if (not line or line.startswith('=')
                            or line.startswith('+') or line.startswith('-')
                            or line.startswith('|') and 'ID' in line
                            or line.startswith('Matrix')
                            or '[WARN]' in line):
                        continue

                    # 尝试解析表格行（可能以 | 分隔或空格分隔）
                    row = self._parse_device_line(line)
                    if row:
                        row.update({
                            "node": node_name,
                            "time_stamp": time_stamp,
                            "sample_idx": sample_idx,
                        })
                        data.append(row)

        return data

    @staticmethod
    def _parse_device_line(line: str) -> Optional[dict]:
        """
        尝试从一行 matrix-smi 输出中提取设备指标。

        支持两种格式：
        1. 管道分隔: | 0 | 65C | 150W | 32000MiB / 65536MiB | 45% |
        2. 空格分隔: 0  65  150  1200  800  auto  250  48%  35%

        Returns:
            dict: 设备指标字典，解析失败返回 None
        """
        # 格式1: 管道分隔
        if '|' in line:
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 4:
                try:
                    device_id = re.search(r'(\d+)', parts[0])
                    if not device_id:
                        return None
                    result = {"device_id": device_id.group(1)}

                    # 逐字段提取数值
                    for part in parts[1:]:
                        temp_m = re.search(r'(\d+)\s*[Cc]', part)
                        power_m = re.search(r'(\d+\.?\d*)\s*[Ww]', part)
                        util_m = re.search(r'(\d+\.?\d*)\s*%', part)
                        mem_m = re.search(
                            r'(\d+)\s*MiB\s*/\s*(\d+)\s*MiB', part)

                        if temp_m and "temp" not in result:
                            result["temp"] = temp_m.group(1)
                        if power_m and "avg_power" not in result:
                            result["avg_power"] = power_m.group(1)
                        if mem_m:
                            used = int(mem_m.group(1))
                            total = int(mem_m.group(2))
                            result["vram_pct"] = (
                                f"{used / total * 100:.1f}%"
                                if total > 0 else "0%")
                        if util_m and "matrix_pct" not in result:
                            result["matrix_pct"] = f"{util_m.group(1)}%"

                    return result if "device_id" in result else None
                except (ValueError, IndexError):
                    return None

        # 格式2: 空格分隔（类似 hy-smi）
        parts = line.split()
        if len(parts) >= 5:
            try:
                int(parts[0])
            except ValueError:
                return None
            return {
                "device_id": parts[0],
                "temp": parts[1],
                "avg_power": parts[2],
                "sclk": parts[3] if len(parts) > 3 else None,
                "mclk": parts[4] if len(parts) > 4 else None,
                "vram_pct": parts[5] if len(parts) > 5 else None,
                "matrix_pct": parts[6] if len(parts) > 6 else None,
            }

        return None

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def get_summary(self, parsed_data: List[Dict]) -> Optional[Dict]:
        """
        从 matrix-smi 解析数据中提取加速卡利用率摘要。

        Returns:
            dict: 包含平均/峰值利用率、显存使用率、功耗、温度等；
                  数据为空时返回 None。
        """
        if not parsed_data:
            return None

        matrix_pcts, vram_pcts, powers, temps = [], [], [], []

        for row in parsed_data:
            if row.get("matrix_pct"):
                try:
                    matrix_pcts.append(
                        float(row["matrix_pct"].rstrip('%')))
                except (ValueError, AttributeError):
                    pass
            if row.get("vram_pct"):
                try:
                    vram_pcts.append(
                        float(row["vram_pct"].rstrip('%')))
                except (ValueError, AttributeError):
                    pass
            if row.get("avg_power"):
                try:
                    powers.append(
                        float(row["avg_power"].rstrip('Ww')))
                except (ValueError, AttributeError):
                    pass
            if row.get("temp"):
                try:
                    temps.append(
                        float(row["temp"].rstrip('cC')))
                except (ValueError, AttributeError):
                    pass

        if not matrix_pcts:
            return None

        nodes = set(row["node"] for row in parsed_data)
        samples = set(
            (row["node"], row["time_stamp"]) for row in parsed_data)

        return {
            "avg_matrix_pct": sum(matrix_pcts) / len(matrix_pcts),
            "max_matrix_pct": max(matrix_pcts),
            "avg_vram_pct": (
                sum(vram_pcts) / len(vram_pcts) if vram_pcts else 0.0),
            "avg_power": (
                sum(powers) / len(powers) if powers else 0.0),
            "avg_temp": (
                sum(temps) / len(temps) if temps else 0.0),
            "num_nodes": len(nodes),
            "total_samples": len(samples),
        }
