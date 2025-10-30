#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from perfbench.utils.logger import get_logger
from perfbench.utils.system_checker import check_slurm_environment, check_slurm_commands

logger = get_logger()

def validate_environment(force: bool = False):
    """
    验证工具运行环境
    - 检查SLURM环境
    - 验证必要的SLURM命令
    - 测试作业提交功能
    """
    logger.info("开始验证PerfBench运行环境...")
    
    # 检查SLURM环境
    if not check_slurm_environment(force=force):
        logger.error("SLURM环境验证失败")
        return False
    
    # 检查必要的SLURM命令
    if not check_slurm_commands():
        logger.error("SLURM命令验证失败")
        return False
    
    # 创建并提交测试作业
    test_script = create_test_job()
    if test_script:
        if submit_test_job(test_script):
            logger.info("测试作业提交成功")
            cleanup_test_job(test_script)
            return True
    
    logger.error("环境验证失败")
    return False

def create_test_job():
    """
    创建测试作业脚本
    """
    script_content = """#!/bin/bash
#SBATCH --job-name=perfbench_test
#SBATCH --nodes=1
#SBATCH --time=1:00
#SBATCH --output=perfbench_test_%j.out

sleep 10
"""
    try:
        script_path = "/tmp/perfbench_test.slurm"
        with open(script_path, "w") as f:
            f.write(script_content)
        return script_path
    except Exception as e:
        logger.error(f"创建测试作业失败: {str(e)}")
        return None

def submit_test_job(script_path):
    """
    提交测试作业
    """
    cmd = f"sbatch {script_path}"
    result = os.system(cmd)
    return result == 0

def cleanup_test_job(script_path):
    """
    清理测试作业文件
    """
    try:
        os.remove(script_path)
        output_pattern = "perfbench_test_*.out"
        os.system(f"rm -f {output_pattern}")
    except Exception as e:
        logger.warning(f"清理测试文件失败: {str(e)}")