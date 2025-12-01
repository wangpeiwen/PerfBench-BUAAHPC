#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import re
import subprocess
from datetime import datetime
from perfbench.utils.logger import get_logger
from perfbench.utils.script_parser import parse_slurm_script
from perfbench.utils import monitoring
from perfbench.utils import scheduler
from perfbench.utils.system_checker import detect_scheduler

logger = get_logger()


def process_slurm_script(script_path, interval, output_path, wait=False):
    """
    处理SLURM脚本
    - 解析原始脚本
    - 创建输出目录
    - 生成监控脚本
    - 提交作业
    """
    # 增加进度展示
    logger.info(f"开始处理SLURM脚本: {script_path}")
    
    # 验证输入文件存在
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"脚本文件不存在: {script_path}")
    
    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = os.path.join(output_path, f"perfbench_{timestamp}")
    os.makedirs(job_dir, exist_ok=True)
    
    # 检测调度器并根据调度器选择脚本解析方式
    scheduler_type = detect_scheduler() or 'slurm'
    script_info = None
    try:
        from perfbench.utils.script_parser import parse_script
        script_info = parse_script(script_path, scheduler=scheduler_type)
    except Exception:
        # 回退到 slurm 解析以保持兼容
        script_info = parse_slurm_script(script_path)
    
    # 生成修改后的脚本（只做最小的环境注入，实际监控在登录节点运行）
    scheduler_type = detect_scheduler()
    if scheduler_type == 'lsf':
        from perfbench.utils import monitor_sunway as sunway_monitor
        modified_script = sunway_monitor.generate_monitoring_script(script_path, script_info, interval, job_dir)
    else:
        modified_script = monitoring.generate_monitoring_script(script_path, script_info, interval, job_dir)

    # 复制修改后的脚本到script目录
    script_dir = os.path.dirname(script_path)
    # 不再使用固定文件名 run.slurm，避免覆盖用户文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scheduler_type = detect_scheduler()
    if scheduler_type == 'lsf':
        output_script = os.path.join(script_dir, f"run.perfbench_{timestamp}.sh")
    else:
        output_script = os.path.join(script_dir, f"run.perfbench_{timestamp}.slurm")
    shutil.copy2(modified_script, output_script)

    # 提交作业并获取 jobid（根据集群类型自动选择提交方式）
    jobid = scheduler.submit_job(output_script)

    # 在登录节点启动监控器（使用 sacct/seff/sinfo）
    try:
        # 根据调度器类型选择相应的监控脚本生成器/启动器
        if scheduler_type == 'lsf':
                # Sunway/LSF 系统（cnload / bjobs），把 master_cores 和 cgsp 参数传递给监控脚本
                from perfbench.utils import monitor_sunway as sunway_monitor
                mc = script_info.get('master_cores') if script_info else None
                cgsp = None
                # 尝试从脚本命令中查找 cgsp 或 -cgsp 设定
                if script_info and 'commands' in script_info:
                    for c in script_info['commands']:
                        if 'cgsp' in c or '-cgsp' in c:
                            cgsp = c
                            break
                sunway_monitor.start_monitoring_on_login(jobid, interval, job_dir, master_cores=mc, cgsp=cgsp)
        else:
            monitoring.start_monitoring_on_login(jobid, interval, job_dir)
    except Exception as e:
        logger.warning(f"启动登录节点监控失败: {e}")
    
    # 如果用户选择等待作业完成，则阻塞并等待
    if wait:
        logger.info(f"等待作业 {jobid} 完成...")
        scheduler.wait_for_job_completion(jobid, poll_interval=interval, scheduler=scheduler_type)
        logger.info(f"作业 {jobid} 已完成。")
        # 如果是 LSF (Sunway), 可以自动后处理 cnload 位图数据
        if scheduler_type == 'lsf':
            from perfbench.utils.result_handler import postprocess_cnload_job
            csv_path = postprocess_cnload_job(job_dir, interval=interval)
            logger.info(f"cnload 后处理完成，CSV 路径: {csv_path}")

    logger.info(f"作业处理完成，输出目录: {job_dir}")
    return job_dir, script_info
