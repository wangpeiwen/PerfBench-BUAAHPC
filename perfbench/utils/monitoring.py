# -*- coding: utf-8 -*-
"""
监控工具模块。

本模块承担两类生命周期不同的职责，通过注释分区明确边界：

【脚本准备器】（提交前逻辑）
    在作业提交前对原始 SLURM 脚本进行改写，注入环境记录语句。
    改写结果写入输出目录作为实际提交副本。
    相关函数：generate_monitoring_script()

【监控执行器】（运行期逻辑）
    在作业提交后于登录节点启动后台 shell 监控脚本，
    周期性采集调度系统状态并写入日志文件。
    相关函数：start_monitoring_on_login()（SLURM）
              start_bjob_monitoring_on_login()（申威）

后续若需替换监控方式或替换脚本注入方式，可按此分区独立修改，
不会影响另一类职责。
"""

import os
from perfbench.utils.logger import get_logger

logger = get_logger()


# ===========================================================================
# 脚本准备器（提交前逻辑）
# ===========================================================================

def generate_monitoring_script(original_script: str, script_info: dict,
                                interval: int, output_dir: str,
                                extra_injection: str = "") -> str:
    """
    生成包含监控代码的 SLURM 脚本副本。

    在所有 #SBATCH 指令之后注入环境记录 echo 行，以及（可选的）额外采样代码块。
    改写后的脚本写入 output_dir/modified_script.slurm。

    Args:
        original_script: 原始脚本路径
        script_info:     parse_slurm_script() 返回的脚本信息（当前未使用，预留接口）
        interval:        监控采集间隔（秒）
        output_dir:      输出目录
        extra_injection: 额外注入的 bash 代码段（如加速卡采样块），为空则不注入

    Returns:
        str: 改写后的脚本路径
    """
    with open(original_script, 'r') as f:
        lines = f.readlines()

    # 注入段：记录运行节点和作业 ID
    env_setup = (
        f"\n# PerfBench 环境信息记录\n"
        f'echo "PerfBench: job started on $(hostname)" > {output_dir}/job_node_info.txt\n'
        f'echo "SLURM_JOB_ID=${{SLURM_JOB_ID}}" >> {output_dir}/job_node_info.txt\n'
    )

    # 加速卡采样注入段（由外部 AcceleratorMonitor 生成）
    if extra_injection:
        env_setup += extra_injection

    # 确保存在 shebang
    if not lines or not lines[0].startswith('#!'):
        lines.insert(0, '#!/bin/bash\n')

    # 找到所有 #SBATCH 行的最后位置
    last_sbatch_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith('#SBATCH'):
            last_sbatch_idx = i

    # 插入位置：SBATCH 块之后；无 SBATCH 则插在 shebang 之后
    insert_pos = last_sbatch_idx + 1 if last_sbatch_idx != -1 else 1
    lines.insert(insert_pos, env_setup.lstrip())

    output_script = os.path.join(output_dir, "modified_script.slurm")
    with open(output_script, 'w') as f:
        f.write(''.join(lines))
    os.chmod(output_script, 0o755)

    return output_script


def generate_monitoring_code(interval: int, output_dir: str) -> str:
    """
    生成监控代码注释段（当前未被主流程调用）。

    # TODO: 当前未使用，若后续需要将监控逻辑内嵌到作业脚本中可启用。
    """
    return (
        f"# PerfBench: login-node based monitoring will be started by the tool. "
        f"Interval={interval}s\n"
    )


# ===========================================================================
# 监控执行器（运行期逻辑）
# ===========================================================================

def start_monitoring_on_login(jobid: str, interval: int, output_dir: str) -> int:
    """
    在登录节点启动 SLURM 后台监控脚本。

    生成的 shell 脚本（monitor_login.sh）周期性执行：
        sacct   - 作业统计（用于最终结果解析）
        sinfo   - 集群节点状态
        sstat   - 步骤级资源（需作业正在运行）
        scontrol - 作业详情
    作业进入终态后额外执行 seff 并退出循环。

    监控进程 PID 写入 monitor_login.pid，以便后续追踪。

    Args:
        jobid:      作业 ID
        interval:   采集间隔（秒）
        output_dir: 日志输出目录

    Returns:
        int: 监控进程 PID
    """
    os.makedirs(output_dir, exist_ok=True)
    monitor_sh = os.path.join(output_dir, 'monitor_login.sh')
    monitor_pid_file = os.path.join(output_dir, 'monitor_login.pid')

    script = f"""#!/bin/bash
# PerfBench login-node monitoring for job {jobid}
JOBID={jobid}
INTERVAL={interval}
OUTDIR={output_dir}

mkdir -p "$OUTDIR"

while true; do
    ts=$(date +%Y%m%d_%H%M%S)

    # sacct 作业统计（用于最终结果解析）
    sacct -j $JOBID --format=JobID,JobName%20,State,Elapsed,MaxRSS,AllocCPUs -P \\
        > "$OUTDIR/sacct_$ts.log" 2>&1

    # sinfo 集群节点状态
    sinfo -N -o "%N %t %f" > "$OUTDIR/sinfo_$ts.log" 2>&1 || true

    # sstat 步骤级资源（需作业正在运行）
    sstat -j $JOBID --format=JobID,MaxRSS,AveRSS,MaxVMSize -P \\
        > "$OUTDIR/sstat_$ts.log" 2>&1 || true

    # scontrol 作业详情
    scontrol show job $JOBID > "$OUTDIR/scontrol_$ts.log" 2>&1 || true

    # 检查作业是否已进入终态
    state=$(sacct -j $JOBID -n -o State -P | head -n1)
    inqueue=$(squeue -j $JOBID -h | wc -l)
    if [[ "$state" =~ "COMPLETED" || "$state" =~ "FAILED" || \\
          "$state" =~ "CANCELLED" || "$state" =~ "TIMEOUT" || \\
          $inqueue -eq 0 ]]; then
        # seff 仅在作业结束后调用一次
        seff $JOBID > "$OUTDIR/seff_$ts.log" 2>&1 || true
        echo "Job $JOBID finished with state $state at $ts (squeue empty: $inqueue)" \\
            > "$OUTDIR/job_end_$ts.log"
        break
    fi

    sleep $INTERVAL
done
"""

    with open(monitor_sh, 'w') as f:
        f.write(script)
    os.chmod(monitor_sh, 0o755)

    import subprocess
    p = subprocess.Popen([monitor_sh], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    with open(monitor_pid_file, 'w') as f:
        f.write(str(p.pid))

    logger.info(f"[SLURM] 登录节点监控脚本已启动 (pid={p.pid})，输出目录: {output_dir}")
    return p.pid


def start_bjob_monitoring_on_login(jobid: str, interval: int,
                                    output_dir: str) -> int:
    """
    在登录节点启动申威（Sunway）后台监控脚本。

    生成的 shell 脚本（monitor_login_sw.sh）周期性执行：
        bjobs   - 作业状态（用于最终结果解析）
        cnload  - 主核负载和内存（主核 + 从核位图）
    作业进入终态后退出循环。

    监控进程 PID 写入 monitor_login_sw.pid，以便后续追踪。

    Args:
        jobid:      作业 ID
        interval:   采集间隔（秒）
        output_dir: 日志输出目录

    Returns:
        int: 监控进程 PID
    """
    os.makedirs(output_dir, exist_ok=True)
    monitor_sh = os.path.join(output_dir, 'monitor_login_sw.sh')
    monitor_pid_file = os.path.join(output_dir, 'monitor_login_sw.pid')

    script = f"""#!/bin/bash
# PerfBench login-node monitoring for Sunway job {jobid}
JOBID={jobid}
INTERVAL={interval}
OUTDIR={output_dir}

mkdir -p "$OUTDIR"

while true; do
    ts=$(date +%Y%m%d_%H%M%S)

    # bjobs 作业状态（用于最终结果解析）
    bjobs -l $JOBID > "$OUTDIR/bjobs_$ts.log" 2>&1 || true

    # cnload 主核负载和内存
    NODE_LIST=$(bjobs -l "$JOBID" | grep -Po 'nodeid: \\K\\d+' | tr '\\n' ',' | sed 's/,$//')
    cnload -c "$NODE_LIST" | awk '
      /^CPU/ {{printf "%-6s %-8s Load:%-5s Mem:%s\\n", $1, $2, $3, $4}}
      /Total/ {{print "主核总量: "$2" 使用率: "$3}}
    ' >> "$OUTDIR/cnload_$ts.log" 2>&1 || true

    # 从核位图采集
    cnload -b -j "$JOBID" > "$OUTDIR/cnload_bitmap_$ts.log" 2>&1 || true
    grep 'SPE[0-9]' "$OUTDIR/cnload_bitmap_$ts.log" \\
        >> "$OUTDIR/cnload_bitmap_filtered_$ts.log" 2>&1 || true

    # 检查作业是否已进入终态
    state=$(bjobs $JOBID 2>/dev/null | awk '!/^(JOBID|---)/ && NF>1 {{print $2; exit}}')
    if [[ "$state" == "DONE" || "$state" == "EXIT" || \\
          "$state" == "CANCELED" || "$state" == "TERM" ]]; then
        echo "Job $JOBID finished with state $state at $ts" \\
            > "$OUTDIR/job_end_$ts.log"
        break
    fi

    sleep $INTERVAL
done
"""

    with open(monitor_sh, 'w') as f:
        f.write(script)
    os.chmod(monitor_sh, 0o755)

    import subprocess
    p = subprocess.Popen([monitor_sh], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    with open(monitor_pid_file, 'w') as f:
        f.write(str(p.pid))

    logger.info(
        f"[Sunway] 登录节点申威监控脚本已启动 (pid={p.pid})，输出目录: {output_dir}"
    )
    return p.pid
