#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LSF 调度平台适配器。"""

import glob
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional
from perfbench.adapters.platform.base import PlatformAdapter
from perfbench.adapters.platform.logs import JobLogSummary, PlatformLogParser
from perfbench.utils.logger import get_logger

logger = get_logger()


class LsfLogParser(PlatformLogParser):
    """解析 LSF bjobs 日志。"""

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
                    f"LSF 运行时间（秒，按 bjobs 状态采样估算）: "
                    f"{summary.elapsed_seconds}"
                )

        return summary

    def parse_bjobs(self, out_dir: str) -> List[Dict]:
        """
        解析 out_dir 下所有 bjobs_*.log 文件。

        支持两类输出：
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

        目标 LSF 环境的基础 bjobs 输出只包含 STAT，不保证提供 Run time 字段。
        """
        first_seen = None
        run_start = None
        end_time = None
        terminal_states = {"DONE", "EXIT", "CANCELED", "CANCELLED", "TERM"}

        for row in sorted(rows, key=lambda item: item.get("time_stamp") or ""):
            ts = self._parse_perfbench_timestamp(row.get("time_stamp"))
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

    @staticmethod
    def _parse_perfbench_timestamp(time_stamp: str) -> Optional[datetime]:
        """将日志文件名中的 YYYYmmdd_HHMMSS 时间戳转为 datetime。"""
        try:
            return datetime.strptime(time_stamp, "%Y%m%d_%H%M%S")
        except (TypeError, ValueError):
            return None

    def _parse_bjobs_table(self, lines: List[str], row: Dict) -> None:
        """
        解析表格型 bjobs 输出：
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


class LsfAdapter(PlatformAdapter):
    """
    LSF 平台适配器，封装 bsub / bjobs / cnload 等命令集合。

    当前目标 LSF 集群的作业脚本通常是 csh/bash wrapper，内部自行调用
    bsub 提交作业；适配器直接执行 wrapper，不改写提交脚本。
    """

    # ------------------------------------------------------------------
    # 脚本解析
    # ------------------------------------------------------------------

    def parse_script(self, script_path: str) -> dict:
        """从 wrapper 内的 bsub 命令行提取参数。"""
        info = self._new_script_info()

        try:
            with open(script_path, 'r', encoding='utf-8') as handle:
                lines = handle.readlines()

            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#') or not stripped:
                    continue

                if 'bsub ' in stripped:
                    self._parse_bsub_line(stripped, info)
                    break
        except Exception as exc:
            logger.error(f"解析 LSF wrapper 脚本失败: {exc}")
            return None

        return info

    @staticmethod
    def _new_script_info() -> dict:
        return {
            'job_name': None,
            'nodes': 1,
            'tasks_per_node': 1,
            'cpus_per_task': 1,
            'num_processes': None,
            'queue': None,
            'time_limit': None,
            'partition': None,
            'output': None,
            'error': None,
            'commands': [],
        }

    @staticmethod
    def _parse_bsub_line(line: str, info: dict) -> None:
        bsub_match = re.search(r'bsub\s+(.+?)(?:[`"\']|$)', line)
        if not bsub_match:
            return
        bsub_args = bsub_match.group(1)

        patterns = {
            'job_name': r'-J\s+(\S+)',
            'nodes': r'-N\s+(\d+)',
            'num_processes': r'-n\s+(\d+)',
            'tasks_per_node': r'-np\s+(\d+)',
            'queue': r'-q\s+(\S+)',
            'time_limit': r'-timelimit\s+(\S+)',
            'output': r'-o\s+(\S+)',
            'error': r'-e\s+(\S+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, bsub_args)
            if match:
                value = match.group(1)
                if key in ('nodes', 'num_processes', 'tasks_per_node'):
                    value = int(value)
                info[key] = value

        if info.get('queue'):
            info['partition'] = info['queue']

        executable_match = re.search(r'(?:^|[\s])(\./\S+|/\S+)\s*', bsub_args)
        if executable_match:
            info['commands'].append(executable_match.group(1))

    # ------------------------------------------------------------------
    # 脚本准备（提交前逻辑）
    # ------------------------------------------------------------------

    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        LSF wrapper 无脚本改写步骤，直接返回原始脚本路径。

        Args:
            script_path: 原始脚本路径（直接提交）
            script_info: 解析得到的脚本信息（本方法不使用）
            interval:    监控间隔（本方法不使用）
            output_dir:  输出目录（本方法不使用）

        Returns:
            str: 原始脚本路径，不做修改
        """
        logger.info(f"[LSF] 不做脚本改写，直接提交原始 wrapper: {script_path}")
        return script_path

    # ------------------------------------------------------------------
    # 作业提交
    # ------------------------------------------------------------------

    def submit_job(self, script_path: str) -> str:
        """
        直接执行 LSF wrapper 脚本（脚本内部调用 bsub），从 stdout 提取 JobID。

        目标脚本是 csh/bash wrapper，内部自行调用 bsub 并输出 JobID。
        典型输出包含 "Job <12345>" 格式。
        """
        try:
            script_dir = os.path.dirname(os.path.abspath(script_path))
            result = subprocess.run(
                [os.path.abspath(script_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                cwd=script_dir,
            )
            combined = result.stdout + result.stderr
            if result.returncode != 0:
                raise RuntimeError(f"LSF wrapper 执行失败: {combined.strip()}")

            match = re.search(r'Job\s*<(\d+)>', combined)
            if not match:
                match = re.search(r'(\d+)', combined)
            if not match:
                raise RuntimeError(
                    f"无法从脚本输出中提取 JobID: {combined.strip()}"
                )
            jobid = match.group(1)
            logger.info(f"[LSF] 作业已提交, JobID={jobid}")
            return jobid
        except FileNotFoundError:
            raise RuntimeError(f"脚本不存在或无执行权限: {script_path}")
        except PermissionError:
            raise RuntimeError(
                f"脚本无执行权限，请执行: chmod +x {script_path}"
            )

    # ------------------------------------------------------------------
    # 登录节点监控
    # ------------------------------------------------------------------

    def start_monitoring(self, jobid: str, interval: int, output_dir: str) -> int:
        """
        在登录节点后台启动 bjobs / cnload 周期采集脚本。

        Returns:
            int: 监控进程 PID
        """
        pid = self._start_login_monitor(jobid, interval, output_dir)
        logger.info(f"[LSF] 登录节点监控已启动 (pid={pid})")
        return pid

    def _start_login_monitor(self, jobid: str, interval: int, output_dir: str) -> int:
        os.makedirs(output_dir, exist_ok=True)
        monitor_sh = os.path.join(output_dir, 'monitor_login_lsf.sh')
        monitor_pid_file = os.path.join(output_dir, 'monitor_login_lsf.pid')

        with open(monitor_sh, 'w', encoding='utf-8') as handle:
            handle.write(self._build_login_monitor_script(jobid, interval, output_dir))
        os.chmod(monitor_sh, 0o755)

        process = subprocess.Popen(
            [monitor_sh],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(monitor_pid_file, 'w', encoding='utf-8') as handle:
            handle.write(str(process.pid))

        logger.info(f"[LSF] login-node monitoring started (pid={process.pid}): {output_dir}")
        return process.pid

    @staticmethod
    def _build_login_monitor_script(jobid: str, interval: int, output_dir: str) -> str:
        return f"""#!/bin/bash
# PerfBench login-node monitoring for LSF job {jobid}
JOBID={jobid}
INTERVAL={interval}
OUTDIR={output_dir}

mkdir -p "$OUTDIR"

while true; do
    ts=$(date +%Y%m%d_%H%M%S)

    {{
        echo "### bjobs -w $JOBID"
        bjobs -w "$JOBID"
        echo
        echo "### bjobs -l $JOBID"
        bjobs -l "$JOBID"
    }} > "$OUTDIR/bjobs_$ts.log" 2>&1 || true

    state=$(awk '!/^(###|JOBID|---)/ && NF>1 && $1 ~ /^[0-9]+$/ {{print $2; exit}}' \\
        "$OUTDIR/bjobs_$ts.log")

    if [[ "$state" == "RUN" ]]; then
        cnload -j "$JOBID" > "$OUTDIR/cnload_$ts.log" 2>&1 || true
        cnload -b -j "$JOBID" > "$OUTDIR/cnload_bitmap_$ts.log" 2>&1 || true
        grep 'SPE[0-9]' "$OUTDIR/cnload_bitmap_$ts.log" \\
            >> "$OUTDIR/cnload_bitmap_filtered_$ts.log" 2>&1 || true
    fi

    if [[ "$state" == "DONE" || "$state" == "EXIT" || \\
          "$state" == "CANCELED" || "$state" == "TERM" ]]; then
        echo "Job $JOBID finished with state $state at $ts" \\
            > "$OUTDIR/job_end_$ts.log"
        break
    fi

    sleep "$INTERVAL"
done
"""

    # ------------------------------------------------------------------
    # 等待作业完成
    # ------------------------------------------------------------------

    def wait_for_job(self, jobid: str, poll_interval: int = 10) -> str:
        """
        轮询 bjobs 等待作业进入终态（DONE / EXIT / CANCELED / TERM）。

        Returns:
            str: 作业最终状态
        """
        logger.info(f"[LSF] 等待作业 {jobid} 完成...")
        while True:
            try:
                result = subprocess.run(
                    ['bjobs', jobid],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                lines = result.stdout.strip().splitlines()
                for line in lines:
                    parts = line.split()
                    if parts and parts[0] == jobid:
                        state = parts[1]
                        if state in ('DONE', 'EXIT', 'CANCELED', 'TERM'):
                            logger.info(f"[LSF] 作业 {jobid} 已结束，状态: {state}")
                            return state
                        break
            except Exception as e:
                logger.warning(f"[LSF] 查询作业状态时出错: {e}")
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # 日志命令名
    # ------------------------------------------------------------------

    def get_log_cmd_name(self) -> str:
        """返回 LSF 平台日志解析使用的命令名称。"""
        return "bjobs"

    def get_log_parser(self) -> LsfLogParser:
        """返回 LSF 平台调度日志解析器。"""
        return LsfLogParser()
