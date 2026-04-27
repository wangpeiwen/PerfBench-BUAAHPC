# SLURM + DCU 开销测试

本目录用于在 SLURM + DCU 集群上测试 PerfBench 监控逻辑是否会改变目标作业自身的
SLURM `Elapsed` 时间。

当前 PerfBench 的采样设计分为两层：

- `--platform slurm`：启用登录节点侧采样，周期性调用 `sacct`、`sinfo`、`sstat`、
  `scontrol`，作业结束后再采集 `seff`。
- `--accelerator dcu`：把计算节点侧 DCU 采样器注入到批处理脚本中。采样器通过
  `srun --overlap` 在每个计算节点启动一个采样任务，并把 `hy-smi` 或 `rocm-smi`
  输出写到 `dcu_logs/dcu_hysmi_<node>.log`。

这个测试会把登录节点采样和计算节点 DCU 采样拆开对比：

| 模式 | 登录节点采样 | 计算节点 DCU 采样 | 用途 |
| --- | --- | --- | --- |
| `bare` | 否 | 否 | 直接 `sbatch` 的基线 |
| `pb_nodcu` | 是 | 否 | PerfBench 框架和登录节点监控开销 |
| `pb_dcu10` | 是 | 10 秒间隔 | 常规 DCU 采样开销 |
| `pb_dcu2` | 是 | 2 秒间隔 | 高频 DCU 采样压力测试 |

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `overhead_bare.slurm` | 被测负载脚本，当前为 195 节点、每节点 4 DCU 的 LAMMPS 作业 |
| `run_overhead_test.sh` | 按模式重复运行开销测试 |
| `analyze_overhead.py` | 汇总 SLURM `Elapsed` 时间并计算开销比例 |
| `1m_in.lj` | LAMMPS 输入文件 |

## 运行方法

在 SLURM 登录节点进入本仓库后运行：

```bash
cd test/slurm_dcu_overhead
bash run_overhead_test.sh 5
```

结果会写到：

```text
test/slurm_dcu_overhead/overhead_results_<timestamp>/
```

然后分析结果：

```bash
python3 analyze_overhead.py overhead_results_<timestamp>
```

常用环境变量覆盖方式：

```bash
PROJ_ROOT=/path/to/PerfBench-BUAAHPC \
WORKLOAD=/path/to/overhead_bare.slurm \
OUTPUT_ROOT=/path/to/output_parent \
LOGIN_INTERVAL=10 \
DCU_INTERVAL_STD=10 \
DCU_INTERVAL_FAST=2 \
bash run_overhead_test.sh 3
```

## 测量口径

主指标是顶层 SLURM 作业的 `Elapsed` 字段：

- `bare` 模式读取直接 `sbatch --wait` 后保存的 `sacct.log`。
- `pb_*` 模式优先读取 PerfBench 在 `--overhead` 模式下生成的 `final_sacct.log`。
- 如果 `final_sacct.log` 不存在，分析脚本会回退读取周期性 `sacct_*.log` 快照。

`timing.txt` 记录的是驱动脚本的端到端墙钟时间，但它不作为主要开销比例的计算依据，
因为其中包含 Python 启动、报告生成以及调度侧等待等额外噪声。

## 当前 PerfBench 调用方式

无 DCU 采样时，驱动脚本会显式调用：

```bash
python3 "$PERFBENCH" \
  -s "$WORKLOAD" \
  -t "$LOGIN_INTERVAL" \
  -o "$OUT_DIR" \
  --platform slurm \
  --overhead \
  --accelerator none
```

启用 DCU 采样时，调用方式为：

```bash
python3 "$PERFBENCH" \
  -s "$WORKLOAD" \
  -t "$LOGIN_INTERVAL" \
  -o "$OUT_DIR" \
  --platform slurm \
  --overhead \
  --accelerator dcu \
  --accelerator-interval 10
```

其中 `--accelerator-interval` 会分别取 `DCU_INTERVAL_STD` 和 `DCU_INTERVAL_FAST`。

## 注意事项

- 尽量在集群空闲时段测试，减少调度波动和背景负载干扰。
- 每个模式应使用相同分区、节点数量和负载脚本。
- 如果需要更严格控制，可以在 `overhead_bare.slurm` 中用 `#SBATCH --nodelist=...`
  固定节点。
- 确认计算节点上 `hy-smi` 或 `rocm-smi` 可用。
- 当前 DCU 采样路径依赖 `srun --overlap`。
- `pb_nodcu - bare` 可近似估计 PerfBench 框架和登录节点监控的固定开销。
- `pb_dcu10 - pb_nodcu`、`pb_dcu2 - pb_nodcu` 可近似估计 DCU 采样器的增量开销。
