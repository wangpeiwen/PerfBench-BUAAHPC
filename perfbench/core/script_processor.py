#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script processor module for PerfBench.

Provides functions to process SLURM and Sunway job scripts:
- Parse the user's submission script
- Create a timestamped output directory
- Generate a monitoring-enhanced script
- Submit the job via sbatch/bsub
- Start login-node monitoring
"""

import os
import subprocess
import time
from datetime import datetime
from perfbench.utils.logger import get_logger
from perfbench.utils.script_parser import parse_slurm_script
from perfbench.utils.monitoring import (
    generate_monitoring_script,
    start_monitoring_on_login,
    start_bjob_monitoring_on_login,
)

logger = get_logger()


def process_slurm_script(script_path, interval, output_dir):
    """
    处理 SLURM 作业脚本的完整流程。

    1. 解析用户提交脚本
    2. 创建带时间戳的输出目录
    3. 生成含监控代码的脚本
    4. 通过 sbatch 提交作业
    5. 启动登录节点监控

    Returns:
        (job_dir, script_info): 作业输出目录和脚本解析信息
    """
    # 1. 解析脚本
    script_info = parse_slurm_script(script_path)
    if script_info is None:
        raise RuntimeError(f"无法解析SLURM脚本: {script_path}")

    logger.info(f"脚本解析完成: job_name={script_info.get('job_name')}, nodes={script_info.get('nodes')}")

    # 2. 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_name = script_info.get('job_name', 'unknown')
    job_dir = os.path.join(output_dir, f"{job_name}_{timestamp}")
    os.makedirs(job_dir, exist_ok=True)
    logger.info(f"输出目录: {job_dir}")

    # 3. 生成监控脚本
    modified_script = generate_monitoring_script(script_path, script_info, interval, job_dir)
    logger.info(f"监控脚本已生成: {modified_script}")

    # 4. 提交作业
    jobid = _submit_slurm_job(modified_script)
    logger.info(f"作业已提交, JobID={jobid}")

    # 5. 启动登录节点监控
    start_monitoring_on_login(jobid, interval, job_dir)

    # 等待作业完成
    _wait_for_slurm_job(jobid)

    return job_dir, script_info


def process_sunway_script(script_path, interval, output_dir):
    """
    处理申威（Sunway）平台作业脚本的完整流程。

    1. 解析用户提交脚本
    2. 创建带时间戳的输出目录
    3. 通过 bsub 提交作业
    4. 启动登录节点监控（bjobs）

    Returns:
        (job_dir, script_info): 作业输出目录和脚本解析信息
    """
    # 1. 解析脚本（复用 SLURM 解析器的基本逻辑，申威脚本格式类似）
    script_info = parse_slurm_script(script_path)
    if script_info is None:
        raise RuntimeError(f"无法解析申威脚本: {script_path}")

    logger.info(f"脚本解析完成: job_name={script_info.get('job_name')}, nodes={script_info.get('nodes')}")

    # 2. 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_name = script_info.get('job_name', 'unknown')
    job_dir = os.path.join(output_dir, f"{job_name}_{timestamp}")
    os.makedirs(job_dir, exist_ok=True)
    logger.info(f"输出目录: {job_dir}")

    # 3. 提交作业
    jobid = _submit_sunway_job(script_path)
    logger.info(f"申威作业已提交, JobID={jobid}")

    # 4. 启动登录节点监控
    start_bjob_monitoring_on_login(jobid, interval, job_dir)

    # 等待作业完成
    _wait_for_sunway_job(jobid)

    return job_dir, script_info


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _submit_slurm_job(script_path):
    """通过 sbatch 提交作业，返回 JobID"""
    try:
        result = subprocess.run(
            ['sbatch', script_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"sbatch 提交失败: {result.stderr.strip()}")
        # sbatch 输出格式: "Submitted batch job 12345"
        jobid = result.stdout.strip().split()[-1]
        return jobid
    except FileNotFoundError:
        raise RuntimeError("sbatch 命令未找到，请确保在 SLURM 集群登录节点上运行")


def _submit_sunway_job(script_path):
    """通过 bsub 提交申威作业，返回 JobID"""
    try:
        result = subprocess.run(
            ['bsub', script_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"bsub 提交失败: {result.stderr.strip()}")
        # bsub 输出中提取 JobID（格式因系统而异，取第一个数字串）
        import re
        match = re.search(r'(\d+)', result.stdout)
        if not match:
            raise RuntimeError(f"无法从 bsub 输出中提取 JobID: {result.stdout.strip()}")
        return match.group(1)
    except FileNotFoundError:
        raise RuntimeError("bsub 命令未找到，请确保在申威集群登录节点上运行")


def _wait_for_slurm_job(jobid, poll_interval=10):
    """轮询等待 SLURM 作业完成"""
    logger.info(f"等待作业 {jobid} 完成...")
    while True:
        try:
            result = subprocess.run(
                ['sacct', '-j', jobid, '-n', '-o', 'State', '-P'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            state = result.stdout.strip().split('\n')[0] if result.stdout.strip() else ''
            if any(s in state for s in ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT']):
                logger.info(f"作业 {jobid} 已结束，状态: {state}")
                return state
        except Exception as e:
            logger.warning(f"查询作业状态时出错: {e}")
        time.sleep(poll_interval)


def _wait_for_sunway_job(jobid, poll_interval=10):
    """轮询等待申威作业完成"""
    logger.info(f"等待申威作业 {jobid} 完成...")
    while True:
        try:
            result = subprocess.run(
                ['bjobs', '-noheader', '-o', 'stat', jobid],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            state = result.stdout.strip()
            if any(s in state for s in ['DONE', 'EXIT', 'CANCELED', 'TERM']):
                logger.info(f"申威作业 {jobid} 已结束，状态: {state}")
                return state
        except Exception as e:
            logger.warning(f"查询申威作业状态时出错: {e}")
        time.sleep(poll_interval)
