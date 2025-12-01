#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Abstraction over different job schedulers (SLURM/LSF), providing helper functions
for job submission and parsing returned job IDs.
"""
import subprocess
import re
from perfbench.utils.logger import get_logger
from perfbench.utils.system_checker import detect_scheduler

logger = get_logger()


def submit_job(script_path: str) -> str:
    """
    根据当前检测到的调度器提交作业，并返回 jobid（字符串）。
    """
    sched = detect_scheduler()
    if sched == 'slurm':
        return submit_job_slurm(script_path)
    elif sched == 'lsf':
        return submit_job_lsf(script_path)
    else:
        raise RuntimeError('无法检测到作业调度器（SLURM或LSF）')


from typing import Optional

def wait_for_job_completion(jobid: str, poll_interval: int = 10, scheduler: Optional[str] = None):
    """
    阻塞等待指定作业完成。根据不同调度器选择轮询命令。
    返回 True 表示作业完成（无论成功/失败），False 表示出现错误。
    """
    import time
    import subprocess
    import shutil

    if scheduler is None:
        scheduler = detect_scheduler()
    if scheduler == 'slurm':
        # 使用 squeue 检查
        try:
            while True:
                # squeue 命令返回 0 即存在，非 0 即不存在（completed/failed/cancelled）
                ret = subprocess.run(['squeue', '-j', str(jobid), '-h'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if ret.returncode != 0 or not ret.stdout:
                    # 未在队列中，作业已经结束
                    return True
                time.sleep(poll_interval)
        except Exception as e:
            logger.error(f"等待 SLURM 作业完成时出错: {e}")
            return False
    elif scheduler == 'lsf':
        # bjobs 命令
        try:
            while True:
                ret = subprocess.run(['bjobs', str(jobid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if ret.returncode != 0:
                    # bjobs 返回非 0 表示作业不再存在
                    return True
                time.sleep(poll_interval)
        except Exception as e:
            logger.error(f"等待 LSF 作业完成时出错: {e}")
            return False
    else:
        logger.error('未知调度器，无法等待作业')
        return False


def submit_job_slurm(script_path: str) -> str:
    """Submit using sbatch and return job id."""
    import os
    import subprocess
    import re

    script_path = os.path.abspath(script_path)
    script_dir = os.path.dirname(script_path)
    script_name = os.path.basename(script_path)
    original_cwd = os.getcwd()
    try:
        os.chdir(script_dir)
        logger.info(f"使用 SLURM 提交作业: {script_name} -> {script_dir}")
        result = subprocess.run(['sbatch', script_name],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                check=True)
        output = result.stdout.strip()
        jobid_match = re.search(r"Submitted batch job (\d+)", output)
        if not jobid_match:
            raise RuntimeError(f"无法解析 sbatch 输出: {output}")
        return jobid_match.group(1)
    finally:
        os.chdir(original_cwd)


def submit_job_lsf(script_path: str) -> str:
    """Submit using bsub and return job id.

    For LSF (Sunway), `script_path` may be a script that is designed to be run via bsub.
    We will call `bsub < script_path` (or call `bsub` with the script name) and parse the returned Job ID.
    """
    import os
    import subprocess

    script_path = os.path.abspath(script_path)
    script_dir = os.path.dirname(script_path)
    script_name = os.path.basename(script_path)
    original_cwd = os.getcwd()
    try:
        os.chdir(script_dir)
        logger.info(f"使用 LSF 提交作业: {script_name} -> {script_dir}")
        # Try `bsub < script` first
        try:
            # Redirect script as stdin to bsub: bsub < script.sh
            with open(script_name, 'r') as fp:
                result = subprocess.run(['bsub'],
                                        stdin=fp,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        check=True)
        except Exception:
            # Fallback: call bsub with script as argument (bsub script.sh)
            result = subprocess.run(['bsub', script_name],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True,
                                    check=True)
        output = result.stdout.strip() + '\n' + result.stderr.strip()
        # LSF bsub 输出通常像: "Job <12345> is submitted to queue ..."
        jobid_match = re.search(r"Job <(\d+)>", output)
        if not jobid_match:
            raise RuntimeError(f"无法解析 bsub 输出: {output}")
        return jobid_match.group(1)
    finally:
        os.chdir(original_cwd)
