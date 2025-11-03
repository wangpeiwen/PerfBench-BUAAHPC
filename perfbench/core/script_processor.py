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

logger = get_logger()


def process_slurm_script(script_path, interval, output_path):
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
    
    # 解析原始脚本
    script_info = parse_slurm_script(script_path)
    
    # 生成修改后的脚本（只做最小的环境注入，实际监控在登录节点运行）
    modified_script = monitoring.generate_monitoring_script(script_path, script_info, interval, job_dir)

    # 复制修改后的脚本到script目录
    output_script = os.path.join(script_path, "run.slurm")
    shutil.copy2(modified_script, output_script)

    # 提交作业并获取 jobid
    jobid = submit_job(output_script)

    # 在登录节点启动监控器（使用 sacct/seff/sinfo）
    try:
        monitoring.start_monitoring_on_login(jobid, interval, job_dir)
    except Exception as e:
        logger.warning(f"启动登录节点监控失败: {e}")
    
    logger.info(f"作业处理完成，输出目录: {job_dir}")
    return job_dir

def submit_job(script_path):
    """
    提交SLURM作业并返回 jobid
    """
    try:
        output = subprocess.check_output(['sbatch', script_path], stderr=subprocess.STDOUT, text=True)
        # sbatch 输出示例: "Submitted batch job 123456"
        m = re.search(r"Submitted batch job (\d+)", output)
        if not m:
            logger.error(f"无法解析 sbatch 输出: {output}")
            raise RuntimeError("作业提交失败：无法解析 jobid")
        jobid = m.group(1)
        logger.info(f"作业已提交，jobid={jobid}")
        return jobid
    except subprocess.CalledProcessError as e:
        logger.error(f"提交作业时出错: {e.output}")
        raise RuntimeError("作业提交失败")