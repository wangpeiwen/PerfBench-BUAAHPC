#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from perfbench.utils.logger import get_logger

logger = get_logger()


def start_monitoring_on_login(jobid, interval, output_dir, master_cores=None, cgsp=None, retries=3):
    """
    在神威等 LSF 系统上启动监控脚本，使用 bjobs、cnload 等命令。
    - jobid: LSF 作业 ID
    - interval: 采样间隔（秒）
    - output_dir: 日志输出目录
    - master_cores: 每节点主核数（用于并行度计算）；如果为空，将从日志或配置中推断
    """
    os.makedirs(output_dir, exist_ok=True)
    monitor_sh = os.path.join(output_dir, 'monitor_sunway.sh')
    monitor_pid = os.path.join(output_dir, 'monitor_sunway.pid')

    script = f"""#!/bin/bash
# PerfBench Sunway login-node monitoring for job {jobid}
JOBID={jobid}
INTERVAL={interval}
OUTDIR={output_dir}
MASTER_CORES={master_cores if master_cores is not None else ''}
CGSP={cgsp if cgsp is not None else ''}

mkdir -p "$OUTDIR"

start_time=$(date +%s)

trap 'echo "监控终止"; exit 0' SIGTERM

while bjobs $JOBID >/dev/null 2>&1; do
  ts=$(date +%Y%m%d_%H%M%S)
  echo -e "\n===== $ts =====" >> "$OUTDIR/cg_monitor_${JOBID}.log"
  echo "Run time: $(( $(date +%s) - start_time ))s" >> "$OUTDIR/cg_monitor_${JOBID}.log"

  # 获取作业分配节点列表
    NODE_LIST=$(bjobs -l $JOBID | grep -Po 'nodeid: \K\d+' | tr '\n' ',' | sed 's/,$//') || true
  echo "NODE_LIST: $NODE_LIST" >> "$OUTDIR/cg_monitor_${JOBID}.log"

  # 主核负载和内存
  cnload -c "$NODE_LIST" >> "$OUTDIR/cnload_c_${JOBID}_$ts.log" 2>&1 || true
  # 位图输出（从核情况）
    cnload -b -j $JOBID >> "$OUTDIR/cnload_b_job_${JOBID}_$ts.log" 2>&1 || true
    if [[ -n "$NODE_LIST" ]]; then
        cnload -b -c "$NODE_LIST" >> "$OUTDIR/cnload_b_c_${JOBID}_$ts.log" 2>&1 || true
    fi

  sleep $INTERVAL
done

echo "Job $JOBID finished, monitor exiting at $(date)" >> "$OUTDIR/cg_monitor_${JOBID}.log"
"""

    with open(monitor_sh, 'w') as f:
        f.write(script)
    os.chmod(monitor_sh, 0o755)

    import subprocess
    import time
    import sys
    # 使用 nohup 并使进程脱离父进程（preexec_fn=os.setpgrp）以免登陆节点会话结束导致监控退出
    pid = None
    attempt = 0
    while attempt < retries:
        try:
            p = subprocess.Popen(['nohup', 'bash', monitor_sh], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
            pid = p.pid
            # 简单延迟以检查进程是否立即退出
            time.sleep(0.2)
            if p.poll() is None:
                break
            attempt += 1
        except Exception as e:
            attempt += 1
            time.sleep(0.2)
    if pid is None:
        raise RuntimeError('无法启动 Sunway 监控脚本')
    with open(monitor_pid, 'w') as f:
        f.write(str(p.pid))

    logger.info(f"Sunway/LSF 登录节点监控脚本已启动 (pid={p.pid})，输出目录: {output_dir}")
    return p.pid


def generate_monitoring_script(original_script, script_info, interval, output_dir):
    """
    为 Sunway/LSF 系统生成一个最小注入脚本，插入作业节点信息记录（例如 LSB_JOBID）。
    """
    import shutil
    import os
    with open(original_script, 'r') as f:
        lines = f.readlines()
    # 确保有 shebang
    if not lines or not lines[0].startswith('#!'):
        lines.insert(0, '#!/bin/bash\n')
    # 简单插入环境记录信息（LSF 的 job id 由 LSB_JOBID 提供）
    env_setup = f"""
# PerfBench 环境信息记录（Sunway/LSF）
echo "PerfBench: job started on $(hostname)" > {output_dir}/job_node_info.txt
echo "LSB_JOBID=${{LSB_JOBID}}" >> {output_dir}/job_node_info.txt
"""
    # 将 env_setup 放在脚本顶部（shebang 之后）
    insert_pos = 1
    lines.insert(insert_pos, env_setup.lstrip())
    output_script = os.path.join(output_dir, 'modified_script.sunway.sh')
    with open(output_script, 'w') as f:
        f.write(''.join(lines))
    os.chmod(output_script, 0o755)
    return output_script
