#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SLURM 平台适配器。

封装 SLURM 作业脚本准备、提交、监控、等待和日志解析入口。
"""

import os
import glob
import re
import subprocess
import time
from typing import Dict, List, Optional
from perfbench.adapters.platform.base import (
    PlatformAdapter,
    write_batch_script_with_accelerator_monitoring,
)
from perfbench.adapters.accelerator.base import AcceleratorMonitor
from perfbench.adapters.accelerator.none import NullMonitor
from perfbench.adapters.platform.logs import JobLogSummary, PlatformLogParser
from perfbench.utils.logger import get_logger

logger = get_logger()


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
        summary.elapsed_seconds = self._parse_elapsed_string(last.get("Elapsed"))
        if summary.elapsed_seconds is None:
            logger.warning(f"无法解析 SLURM Elapsed: {last.get('Elapsed')}")
        return summary

    @staticmethod
    def _parse_elapsed_string(elapsed_str: str) -> Optional[int]:
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


class SlurmAdapter(PlatformAdapter):
    """SLURM 平台适配器，封装 sbatch / sacct / squeue 等命令集合。"""

    def __init__(self, accelerator_monitor: Optional[AcceleratorMonitor] = None):
        """
        Args:
            accelerator_monitor: 加速卡监控器实例，为 None 时使用 NullMonitor（不采集）
        """
        self.accelerator_monitor = accelerator_monitor or NullMonitor()

    def parse_script(self, script_path: str) -> dict:
        info = self._new_script_info()

        try:
            with open(script_path, 'r', encoding='utf-8') as handle:
                lines = handle.readlines()

            for line in lines:
                line = line.strip()
                if line.startswith('#SBATCH'):
                    self._parse_sbatch_directive(line, info)
                elif line and not line.startswith('#'):
                    info['commands'].append(line)
        except Exception as exc:
            logger.error(f"解析 SLURM 脚本失败: {exc}")
            return None

        return info

    @staticmethod
    def _new_script_info() -> dict:
        return {
            'job_name': None,
            'nodes': 1,
            'tasks_per_node': 1,
            'cpus_per_task': 1,
            'time_limit': None,
            'partition': None,
            'output': None,
            'error': None,
            'commands': [],
        }

    @staticmethod
    def _parse_sbatch_directive(line: str, info: dict) -> None:
        line = line.replace('#SBATCH', '').strip()
        patterns = {
            'job_name': r'(?:--job-name|-J)[= ](\S+)',
            'nodes': r'(?:--nodes|-N)[= ](\d+)',
            'tasks_per_node': r'--ntasks-per-node[= ](\d+)',
            'cpus_per_task': r'--cpus-per-task[= ](\d+)',
            'time_limit': r'(?:--time|-t)[= ](\S+)',
            'partition': r'(?:--partition|-p)[= ](\S+)',
            'output': r'(?:--output|-o)[= ](\S+)',
            'error': r'(?:--error|-e)[= ](\S+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, line)
            if match:
                value = match.group(1)
                if key in ('nodes', 'tasks_per_node', 'cpus_per_task'):
                    value = int(value)
                info[key] = value

    # ------------------------------------------------------------------
    # 脚本准备（提交前逻辑）
    # ------------------------------------------------------------------

    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        生成含监控代码的 SLURM 脚本副本，注入环境记录 echo 行及可选的 DCU 采样块。

        Returns:
            str: 改写后的脚本路径（output_dir/modified_script.slurm）
        """
        sampler_block = self.accelerator_monitor.generate_sampler_block(
            output_dir, interval
        )
        modified_script = write_batch_script_with_accelerator_monitoring(
            script_path,
            directive_prefix="#SBATCH",
            output_dir=output_dir,
            output_name="modified_script.slurm",
            job_id_env_name="SLURM_JOB_ID",
            accelerator_sampler_block=sampler_block,
        )
        self._redirect_slurm_output(modified_script, output_dir)
        logger.info(f"[SLURM] 监控脚本已生成: {modified_script}")
        return modified_script

    @staticmethod
    def _redirect_slurm_output(script_path: str, output_dir: str) -> None:
        """Ensure SLURM stdout/stderr files are written under output_dir."""
        output_dir = os.path.abspath(output_dir)
        stdout_path = os.path.join(output_dir, "slurm_%j.out")
        stderr_path = os.path.join(output_dir, "slurm_%j.err")

        with open(script_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()

        saw_stdout = False
        saw_stderr = False
        last_directive_idx = -1
        rewritten = []

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#SBATCH"):
                last_directive_idx = len(rewritten)
                if SlurmAdapter._is_slurm_output_directive(stripped):
                    rewritten.append(f"#SBATCH --output={stdout_path}\n")
                    saw_stdout = True
                    continue
                if SlurmAdapter._is_slurm_error_directive(stripped):
                    rewritten.append(f"#SBATCH --error={stderr_path}\n")
                    saw_stderr = True
                    continue
            rewritten.append(line)

        insert_at = last_directive_idx + 1 if last_directive_idx >= 0 else 1
        additions = []
        if not saw_stdout:
            additions.append(f"#SBATCH --output={stdout_path}\n")
        if not saw_stderr:
            additions.append(f"#SBATCH --error={stderr_path}\n")
        if additions:
            rewritten[insert_at:insert_at] = additions

        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write("".join(rewritten))

    @staticmethod
    def _is_slurm_output_directive(line: str) -> bool:
        return bool(re.match(r"^#SBATCH\s+(?:--output(?:=|\s)|-o(?:\s|$|=))", line))

    @staticmethod
    def _is_slurm_error_directive(line: str) -> bool:
        return bool(re.match(r"^#SBATCH\s+(?:--error(?:=|\s)|-e(?:\s|$|=))", line))

    # ------------------------------------------------------------------
    # 作业提交
    # ------------------------------------------------------------------

    def submit_job(self, script_path: str) -> str:
        """
        通过 sbatch 提交作业，返回 JobID。

        Raises:
            RuntimeError: sbatch 返回非零退出码或命令不存在
        """
        try:
            result = subprocess.run(
                ['sbatch', script_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"sbatch 提交失败: {result.stderr.strip()}")
            # sbatch 标准输出格式: "Submitted batch job 12345"
            jobid = result.stdout.strip().split()[-1]
            logger.info(f"[SLURM] 作业已提交, JobID={jobid}")
            return jobid
        except FileNotFoundError:
            raise RuntimeError("sbatch 命令未找到，请确保在 SLURM 集群登录节点上运行")

    # ------------------------------------------------------------------
    # 登录节点监控
    # ------------------------------------------------------------------

    def start_monitoring(self, jobid: str, interval: int, output_dir: str) -> int:
        """
        在登录节点后台启动 sacct/sinfo/sstat/scontrol 周期采集脚本。

        Returns:
            int: 监控进程 PID
        """
        pid = self._start_login_monitor(jobid, interval, output_dir)
        logger.info(f"[SLURM] 登录节点监控已启动 (pid={pid})")
        return pid

    def _start_login_monitor(self, jobid: str, interval: int, output_dir: str) -> int:
        os.makedirs(output_dir, exist_ok=True)
        monitor_sh = os.path.join(output_dir, 'monitor_login.sh')
        monitor_pid_file = os.path.join(output_dir, 'monitor_login.pid')

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

        logger.info(f"[SLURM] login-node monitoring started (pid={process.pid}): {output_dir}")
        return process.pid

    @staticmethod
    def _build_login_monitor_script(jobid: str, interval: int, output_dir: str) -> str:
        return f"""#!/bin/bash
# PerfBench login-node monitoring for SLURM job {jobid}
JOBID={jobid}
INTERVAL={interval}
OUTDIR={output_dir}

mkdir -p "$OUTDIR"

while true; do
    ts=$(date +%Y%m%d_%H%M%S)

    sacct -j "$JOBID" --format=JobID,JobName%20,State,Elapsed,MaxRSS,AllocCPUs -P \\
        > "$OUTDIR/sacct_$ts.log" 2>&1
    sinfo -N -o "%N %t %f" > "$OUTDIR/sinfo_$ts.log" 2>&1 || true
    sstat -j "$JOBID" --format=JobID,MaxRSS,AveRSS,MaxVMSize -P \\
        > "$OUTDIR/sstat_$ts.log" 2>&1 || true
    scontrol show job "$JOBID" > "$OUTDIR/scontrol_$ts.log" 2>&1 || true

    state=$(sacct -j "$JOBID" -n -o State -P | head -n1)
    inqueue=$(squeue -j "$JOBID" -h | wc -l)
    if [[ "$state" =~ "COMPLETED" || "$state" =~ "FAILED" || \\
          "$state" =~ "CANCELLED" || "$state" =~ "TIMEOUT" || \\
          $inqueue -eq 0 ]]; then
        seff "$JOBID" > "$OUTDIR/seff_$ts.log" 2>&1 || true
        echo "Job $JOBID finished with state $state at $ts (squeue empty: $inqueue)" \\
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
        轮询 sacct 等待作业进入终态（COMPLETED / FAILED / CANCELLED / TIMEOUT）。

        Returns:
            str: 作业最终状态
        """
        logger.info(f"[SLURM] 等待作业 {jobid} 完成...")
        while True:
            try:
                result = subprocess.run(
                    ['sacct', '-j', jobid, '-n', '-o', 'State', '-P'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                state = (result.stdout.strip().split('\n')[0]
                         if result.stdout.strip() else '')
                if any(s in state for s in
                       ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT']):
                    logger.info(f"[SLURM] 作业 {jobid} 已结束，状态: {state}")
                    return state
            except Exception as e:
                logger.warning(f"[SLURM] 查询作业状态时出错: {e}")
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # 日志命令名
    # ------------------------------------------------------------------

    def get_log_cmd_name(self) -> str:
        """返回 SLURM 平台日志解析使用的命令名称。"""
        return "sacct"

    def get_log_parser(self) -> SlurmLogParser:
        """返回 SLURM 平台调度日志解析器。"""
        return SlurmLogParser()

    def capture_final_logs(self, jobid: str, output_dir: str) -> None:
        """
        在作业结束后额外抓取一次最终 sacct 快照。

        主要用于短作业开销测试，避免仅依赖周期轮询日志而低估最终 Elapsed。
        """
        final_sacct_path = os.path.join(output_dir, 'final_sacct.log')
        try:
            result = subprocess.run(
                ['sacct', '-j', jobid, '--format=JobID,JobName%20,State,Elapsed,MaxRSS,AllocCPUs', '-P'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if result.returncode != 0:
                logger.warning(
                    f"[SLURM] 抓取最终 sacct 快照失败 (JobID={jobid}): {result.stderr.strip()}"
                )
                return

            with open(final_sacct_path, 'w', encoding='utf-8') as handle:
                handle.write(result.stdout)
            logger.info(f"[SLURM] 已写入最终 sacct 快照: {final_sacct_path}")
        except FileNotFoundError:
            logger.warning("[SLURM] sacct 命令未找到，跳过最终快照抓取")
        except Exception as e:
            logger.warning(f"[SLURM] 抓取最终 sacct 快照时出错: {e}")
