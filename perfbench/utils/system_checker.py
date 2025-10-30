#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import platform
import subprocess
from perfbench.utils.logger import get_logger

logger = get_logger()

def check_slurm_environment(force: bool = False):
    """
    检查SLURM环境。

    逻辑：
    - 如果传入 force=True，则跳过所有检查（用于本地调试）。
    - 首先检查常见 SLURM 环境变量（仅警告，不直接失败）。
    - 其次以 SLURM 命令是否在 PATH 中为主，若命令缺失则判定为不可用。
    """
    if force:
        logger.warning("强制跳过 SLURM 环境检测（force=True）")
        return True

    # 检查SLURM相关环境变量（仅警告）
    slurm_vars = ['SLURM_ROOT', 'SLURM_CONF']
    missing_vars = []
    for var in slurm_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    if missing_vars:
        logger.warning(f"未找到 SLURM 环境变量: {', '.join(missing_vars)} （仅作警告）")

    # 最终以命令可用性为准
    if not check_slurm_commands():
        logger.error("SLURM 命令不可用（sinfo/squeue/sbatch 等），无法确定为 SLURM 登录节点")
        return False

    return True

def check_slurm_commands():
    """
    检查SLURM命令是否可用
    """
    commands = ['sinfo', 'squeue', 'sbatch', 'scancel']
    for cmd in commands:
        try:
            result = subprocess.run(['which', cmd], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
            if result.returncode != 0:
                logger.warning(f"未找到命令: {cmd}")
                return False
        except Exception as e:
            logger.error(f"检查命令时出错 {cmd}: {str(e)}")
            return False
    return True

def get_architecture():
    """
    获取系统架构信息
    """
    arch = platform.machine()
    if arch == 'x86_64':
        return 'x86_64'
    elif arch == 'aarch64':
        return 'aarch64'
    else:
        logger.warning(f"不支持的系统架构: {arch}")
        return None