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
    解析神威/LSF 脚本中的变量定义，如 JOB_NAME、NODES、MASTER_CORES、QUEUE_NAME、LOG_DIR、INTERVAL 等。
    返回与 parse_slurm_script 相似的 info 字典以便兼容。
    """
    info = {
        'job_name': None,
        'nodes': 1,
        'master_cores': None,
        'queue_name': None,
        'log_dir': None,
        'interval': None,
        'commands': []
    }
    import re
    try:
        with open(script_path, 'r') as f:
            lines = f.readlines()
        for line in lines:
            if not line.strip() or line.strip().startswith('#'):
                continue
            # 解析像 VAR=VALUE 或 VAR="VALUE"
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\"?([^\"\n]+)\"?", line)
            if m:
                var = m.group(1).strip()
                val = m.group(2).strip()
                if var == 'JOB_NAME':
                    info['job_name'] = val
                elif var == 'NODES':
                    try:
                        info['nodes'] = int(val)
                    except Exception:
                        pass
                elif var == 'MASTER_CORES':
                    try:
                        info['master_cores'] = int(val)
                    except Exception:
                        pass
                elif var == 'QUEUE_NAME':
                    info['queue_name'] = val
                elif var == 'LOG_DIR':
                    info['log_dir'] = val
                elif var == 'INTERVAL':
                    try:
                        info['interval'] = int(val)
                    except Exception:
                        pass
            else:
                # 非变量行当作命令
                info['commands'].append(line.strip())
    except Exception as e:
        logger.error(f"解析 Sunway 脚本失败: {str(e)}")
        return None
    return info


def parse_script(script_path, scheduler: str = 'slurm'):
    """
    根据调度器类型解析脚本，返回 info 字典
    """
    if scheduler == 'lsf':
        return parse_sunway_script(script_path)
    else:
        return parse_slurm_script(script_path)

def parse_sbatch_directive(line, info):
    """
    解析SBATCH指令
    """
    line = line.replace('#SBATCH', '').strip()
    
    # 常见参数匹配规则
    patterns = {
        'job_name': r'--job-name[= ](\S+)',
        'nodes': r'--nodes[= ](\d+)',
        'tasks_per_node': r'--ntasks-per-node[= ](\d+)',
        'cpus_per_task': r'--cpus-per-task[= ](\d+)',
        'time_limit': r'--time[= ](\S+)',
        'partition': r'--partition[= ](\S+)',
        'output': r'--output[= ](\S+)',
        'error': r'--error[= ](\S+)'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, line)
        if match:
            value = match.group(1)
            # 数值类型转换
            if key in ['nodes', 'tasks_per_node', 'cpus_per_task']:
                value = int(value)
            info[key] = value