# -*- coding: utf-8 -*-

import os
import shutil
from perfbench.utils.logger import get_logger

logger = get_logger()


def generate_monitoring_script(original_script, script_info, interval, output_dir):
    """
    生成包含监控代码的SLURM脚本
    """
    # 读取原始脚本内容
    with open(original_script, 'r') as f:
        lines = f.readlines()  # 按行读取，方便处理shebang
    
    # 为了在登录节点使用 sacct/seff/sinfo 等命令收集作业信息，
    # 这里只在作业脚本中注入一行以便记录运行节点的环境信息（可选）。
    env_setup = f"""
# PerfBench 环境信息记录（可选）
echo "PerfBench: job started on $(hostname)" > {output_dir}/job_node_info.txt
echo "SLURM_JOB_ID=${{SLURM_JOB_ID}}" >> {output_dir}/job_node_info.txt
"""

    # 找到shebang所在行（第一行），在其后插入环境配置
    modified_lines = []
    shebang_found = False
    for line in lines:
        modified_lines.append(line)
        # 检测第一行是否是shebang
        if not shebang_found and line.startswith('#!'):
            shebang_found = True
            # 在shebang后插入环境配置（去掉开头的换行，避免多余空行）
            modified_lines.append(env_setup.lstrip())
    
    # 如果原始脚本没有shebang，添加默认的#!/bin/bash（避免SLURM报错）
    if not shebang_found:
        modified_lines.insert(0, '#!/bin/bash\n')
        # 在shebang后插入环境配置
        modified_lines.insert(1, env_setup.lstrip())
    
    # 保存修改后的脚本
    output_script = os.path.join(output_dir, "modified_script.slurm")
    with open(output_script, 'w') as f:
        f.write(''.join(modified_lines))
    
    # 确保脚本有执行权限
    os.chmod(output_script, 0o755)
    
    return output_script

def generate_monitoring_code(interval, output_dir):
    """
    生成监控代码段
    """
    return f"# PerfBench: login-node based monitoring will be started by the tool. Interval={interval}s\n"


def start_monitoring_on_login(jobid, interval, output_dir):
    """
    在登录节点上启动一个后台监控脚本，定期使用 sacct/seff/sinfo/sstat 等命令采集与 jobid 相关的数据。

    生成并启动的脚本会把日志写到 output_dir，并将监控进程的 PID 写入 monitor_login.pid。
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
    # sacct 输出（汇总）
    sacct -j $JOBID --format=JobID,JobName%20,State,Elapsed,MaxRSS,AllocCPUs -P > "$OUTDIR/sacct_$ts.log" 2>&1
    # sinfo 当前集群节点状态
    sinfo -N -o "%N %t %f" > "$OUTDIR/sinfo_$ts.log" 2>&1 || true
    # sstat（步骤级别资源）
    sstat -j $JOBID --format=JobID,MaxRSS,AveRSS,MaxVMSize -P > "$OUTDIR/sstat_$ts.log" 2>&1 || true
    # scontrol 节点资源
    scontrol show job $JOBID > "$OUTDIR/scontrol_$ts.log" 2>&1 || true

    # 检查作业状态，若终止则退出循环
    state=$(sacct -j $JOBID -n -o State -P | head -n1)
    # 检查作业是否还在队列中（squeue）
    inqueue=$(squeue -j $JOBID -h | wc -l)
    if [[ "$state" =~ "COMPLETED" || "$state" =~ "FAILED" || "$state" =~ "CANCELLED" || "$state" =~ "TIMEOUT" || $inqueue -eq 0 ]]; then
        # seff 只在作业结束后调用一次
        seff $JOBID > "$OUTDIR/seff_$ts.log" 2>&1 || true
        echo "Job $JOBID finished with state $state at $ts (squeue empty: $inqueue)" > "$OUTDIR/job_end_$ts.log"
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