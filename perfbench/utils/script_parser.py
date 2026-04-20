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