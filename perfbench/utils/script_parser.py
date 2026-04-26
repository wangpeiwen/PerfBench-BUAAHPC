#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from perfbench.utils.logger import get_logger

logger = get_logger()

def parse_slurm_script(script_path):
    """
    解析SLURM脚本，提取关键信息
    """
    info = {
        'job_name': None,
        'nodes': 1,
        'tasks_per_node': 1,
        'cpus_per_task': 1,
        'time_limit': None,
        'partition': None,
        'output': None,
        'error': None,
        'commands': []
    }
    
    try:
        with open(script_path, 'r') as f:
            lines = f.readlines()
            
        for line in lines:
            line = line.strip()
            
            # 解析SLURM指令
            if line.startswith('#SBATCH'):
                parse_sbatch_directive(line, info)
            # 收集执行命令
            elif line and not line.startswith('#'):
                info['commands'].append(line)
        
    except Exception as e:
        logger.error(f"解析脚本失败: {str(e)}")
        return None
        
    return info

def parse_sunway_script(script_path):
    """
    解析申威（Sunway）平台 csh/bash wrapper 脚本，从 bsub 命令行提取关键信息。

    申威脚本典型格式：
        setenv SUBSTAT "`bsub -p -b -o log -q q_share -J job_name -n 4374 -cgsp 64 ...`"
    """
    info = {
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
        'commands': []
    }

    try:
        with open(script_path, 'r') as f:
            lines = f.readlines()

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue

            if 'bsub ' in stripped:
                _parse_bsub_line(stripped, info)
                break

    except Exception as e:
        logger.error(f"解析申威脚本失败: {str(e)}")
        return None

    return info


def _parse_bsub_line(line, info):
    """
    从 bsub 命令行中提取参数。

    支持格式：
        bsub ... -J job_name -n 4374 -q q_share -cgsp 64 ...
    """
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


def parse_sbatch_directive(line, info):
    """
    解析SBATCH指令
    """
    line = line.replace('#SBATCH', '').strip()
    
    patterns = {
        'job_name': r'(?:--job-name|-J)[= ](\S+)',
        'nodes': r'(?:--nodes|-N)[= ](\d+)',
        'tasks_per_node': r'--ntasks-per-node[= ](\d+)',
        'cpus_per_task': r'--cpus-per-task[= ](\d+)',
        'time_limit': r'(?:--time|-t)[= ](\S+)',
        'partition': r'(?:--partition|-p)[= ](\S+)',
        'output': r'(?:--output|-o)[= ](\S+)',
        'error': r'(?:--error|-e)[= ](\S+)'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, line)
        if match:
            value = match.group(1)
            if key in ['nodes', 'tasks_per_node', 'cpus_per_task']:
                value = int(value)
            info[key] = value
