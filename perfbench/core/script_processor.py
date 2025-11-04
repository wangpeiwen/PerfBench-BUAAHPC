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

    # 复制修改后的脚本到script目录：script_path需要进一步处理为目录
    script_dir = os.path.dirname(script_path)
    output_script = os.path.join(script_dir, "run.slurm")
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

def submit_job(script_path: str) -> str:
    """
    提交SLURM作业并返回jobid
    - 提交前切换到脚本所在目录，保证相对路径与手动提交一致
    - 提交后切回原工作目录，不影响后续流程
    - 完善错误处理，输出详细报错信息
    """
    # 转换为绝对路径，避免相对路径歧义
    script_path = os.path.abspath(script_path)
    script_dir = os.path.dirname(script_path)
    script_name = os.path.basename(script_path)
    original_cwd = os.getcwd()  # 保存原始工作目录
    
    try:
        # 切换到脚本所在目录提交作业（模拟手动在脚本目录执行sbatch）
        os.chdir(script_dir)
        logger.info(f"提交作业 -> 目录: {script_dir}，脚本: {script_name}")
        
        # 执行sbatch命令提交作业
        result = subprocess.run(
            ['sbatch', script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True  # 提交失败时抛出CalledProcessError
        )
        
        # 解析jobid（sbatch标准输出格式：Submitted batch job 123456）
        output = result.stdout.strip()
        jobid_match = re.search(r"Submitted batch job (\d+)", output)
        if not jobid_match:
            logger.error(f"无法从sbatch输出中解析jobid: {output}")
            raise RuntimeError(f"作业提交成功，但无法解析jobid（输出: {output}）")
        
        jobid = jobid_match.group(1)
        logger.info(f"作业提交成功，jobid: {jobid}")
        return jobid
    
    except subprocess.CalledProcessError as e:
        # sbatch提交失败（脚本格式错误、资源不足等）
        error_msg = f"sbatch提交失败: {e.stderr.strip()}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
    finally:
        # 无论提交成功与否，切回原始工作目录
        os.chdir(original_cwd)