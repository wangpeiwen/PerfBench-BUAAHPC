#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from perfbench.utils.logger import get_logger

logger = get_logger()


def start_monitoring_on_login(jobid, interval, output_dir):
    """
    在登录节点上启动后台监控脚本，轮询 sacct/seff/sinfo/sstat 等命令并写入输出目录。
    返回后台进程 pid。
    """
    os.makedirs(output_dir, exist_ok=True)
    monitor_sh = os.path.join(output_dir, 'monitor_login.sh')
    monitor_pid = os.path.join(output_dir, 'monitor_login.pid')

    script = f"""#!/bin/bash
# PerfBench login-node monitoring for job {jobid}
JOBID={jobid}
INTERVAL={interval}
OUTDIR={output_dir}

mkdir -p "$OUTDIR"

while true; do
  ts=$(date +%Y%m%d_%H%M%S)
  sacct -j $JOBID --format=JobID,JobName%20,State,Elapsed,MaxRSS,AllocCPUs -P > "$OUTDIR/sacct_$ts.log" 2>&1
  seff $JOBID > "$OUTDIR/seff_$ts.log" 2>&1 || true
  sinfo -N -o "%N %t %f" > "$OUTDIR/sinfo_$ts.log" 2>&1 || true
  sstat -j $JOBID --format=JobID,MaxRSS,AveRSS,MaxVMSize -P > "$OUTDIR/sstat_$ts.log" 2>&1 || true

  state=$(sacct -j $JOBID -n -o State -P | head -n1)
  if [[ "$state" =~ "COMPLETED" || "$state" =~ "FAILED" || "$state" =~ "CANCELLED" || "$state" =~ "TIMEOUT" ]]; then
    echo "Job $JOBID finished with state $state at $ts" > "$OUTDIR/job_end_$ts.log"
    break
  fi

  sleep $INTERVAL
done
"""

    with open(monitor_sh, 'w') as f:
        f.write(script)
    os.chmod(monitor_sh, 0o755)

    import subprocess
    p = subprocess.Popen([monitor_sh], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(monitor_pid, 'w') as f:
        f.write(str(p.pid))

    logger.info(f"登录节点监控脚本已启动 (pid={p.pid})，输出目录: {output_dir}")
    return p.pid
