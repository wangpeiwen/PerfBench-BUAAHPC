#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script processor module for PerfBench.

提供统一的作业处理函数 run_evaluation()，委托给平台适配器完成
平台相关的脚本准备、作业提交、登录节点监控和等待逻辑。

为保持向后兼容，同时保留：
- process_slurm_script()：原 SLURM 入口，内部委托给 SlurmAdapter
- process_sunway_script()：原申威入口，内部委托给 SunwayAdapter
"""

import os
from datetime import datetime
from perfbench.utils.logger import get_logger
from perfbench.utils.script_parser import parse_slurm_script
from perfbench.platform import get_platform_adapter
from perfbench.platform.base import PlatformAdapter

logger = get_logger()


# ---------------------------------------------------------------------------
# 核心统一流程
# ---------------------------------------------------------------------------

def run_evaluation(script_path: str, interval: int, output_dir: str,
                   platform_adapter: PlatformAdapter, progress):
    """
    处理作业脚本的统一流程，委托平台细节给适配器。

    执行顺序：
    1. 解析用户提交脚本
    2. 创建带时间戳的输出目录
    3. 平台适配器准备脚本（如注入监控 echo）
    4. 通过适配器提交作业
    5. 通过适配器启动登录节点监控
    6. 通过适配器轮询等待作业完成

    Args:
        script_path:      原始脚本路径
        interval:         监控采集间隔（秒）
        output_dir:       用户指定的基础输出目录
        platform_adapter: 平台适配器实例（SlurmAdapter 或 SunwayAdapter）

    Returns:
        tuple[str, dict]: (job_dir, script_info)
            - job_dir:     本次作业实际输出目录（含时间戳子目录）
            - script_info: 脚本解析信息字典
    """
    # 1. 解析脚本
    script_info = parse_slurm_script(script_path)
    if script_info is None:
        raise RuntimeError(f"无法解析作业脚本: {script_path}")
    logger.info(
        f"脚本解析完成: job_name={script_info.get('job_name')}, "
        f"nodes={script_info.get('nodes')}"
    )

    # 2. 创建输出目录
    job_dir = _create_output_dir(output_dir, script_info)

    # 3. 准备脚本（平台相关：SLURM 注入 echo，申威直接使用原脚本）
    prepared_script = platform_adapter.prepare_script(
        script_path, script_info, interval, job_dir
    )

    # 4. 提交作业
    jobid = platform_adapter.submit_job(prepared_script)
    logger.info(f"作业已提交, JobID={jobid}")
    progress.next("作业提交")

    # 5. 启动登录节点监控
    platform_adapter.start_monitoring(jobid, interval, job_dir)
    progress.next("监控中")

    # 6. 等待作业完成
    platform_adapter.wait_for_job(jobid)
    progress.next("监控完成")

    return job_dir, script_info


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _create_output_dir(base_output_dir: str, script_info: dict) -> str:
    """
    根据作业名称和当前时间戳创建唯一的输出子目录。

    Args:
        base_output_dir: 用户指定的基础输出目录
        script_info:     脚本解析信息字典，用于取 job_name

    Returns:
        str: 创建完成的输出目录路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_name = script_info.get('job_name', 'unknown')
    job_dir = os.path.join(base_output_dir, f"{job_name}_{timestamp}")
    os.makedirs(job_dir, exist_ok=True)
    logger.info(f"输出目录: {job_dir}")
    return job_dir
