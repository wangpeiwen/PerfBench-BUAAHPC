# PerfBench 开销测试

本目录包含用于量化 PerfBench 工具自身开销的测试脚本。

## 测试目的

回答核心问题：**PerfBench 的监控行为对被测作业的运行时间和资源占用有多大扰动？**

## 开销来源

| 层级 | 来源 | 位置 |
|------|------|------|
| 计算节点内 | `srun --overlap` 启动 DCU 采样 + `hy-smi` 周期 fork | 与用户作业共享资源 |
| 登录节点 | sacct/sinfo/sstat/scontrol 周期轮询 | SLURM 控制器 |
| Python 前后处理 | 脚本解析、日志解析、报告生成 | 登录节点 |

## 文件说明

| 文件 | 用途 |
|------|------|
| `overhead_bare.slurm` | 裸跑基准脚本（LAMMPS 10N×4DCU），加了首尾时间戳 |
| `run_overhead_test.sh` | 批量驱动脚本，自动执行 4 种模式 × N 次重复 |
| `analyze_overhead.py` | 结果分析脚本，输出汇总表格、开销百分比、t 检验 |
| `run.slurm` | 原始 LAMMPS 作业脚本（参考） |

## 测试矩阵

| 模式 | DCU 采样 | 登录节点监控 | 说明 |
|------|---------|------------|------|
| bare | 无 | 无 | 直接 sbatch，作为 baseline |
| pb_nodcu | 无 | 有 | 仅登录节点轮询开销 |
| pb_dcu10 | 10s 间隔 | 有 | 标准采样频率 |
| pb_dcu2 | 2s 间隔 | 有 | 高频采样，压力测试 |

## 使用方法

### 1. 运行测试

```bash
cd /public/home/buaahpc/retro/PerfBench-BUAAHPC/test/slurm_dcu_overhead

# 每种模式跑 5 次（默认）
bash run_overhead_test.sh

# 或指定重复次数
bash run_overhead_test.sh 3
```

结果输出到 `../overhead_results_<timestamp>/` 目录。

### 2. 分析结果

```bash
python3 analyze_overhead.py ../overhead_results_<timestamp>
```

输出示例：

```
========================================================================
模式                 次数    均值(s)   标准差(s)     开销(%)
------------------------------------------------------------------------
裸跑 (baseline)         5      120.3       2.15   baseline
PerfBench 无DCU         5      120.8       1.98     +0.42%
PerfBench DCU-10s       5      121.5       2.33     +1.00%
PerfBench DCU-2s        5      123.1       2.67     +2.33%
========================================================================
```

## 判据

| 开销范围 | 结论 |
|---------|------|
| < 1% | 可忽略，工具对测量结果无实质影响 |
| 1% ~ 5% | 可接受，需在报告中注明 |
| > 5% | 需优化采样策略（降低频率、减少 fork 等） |

## 注意事项

- 尽量在集群空闲时段测试，减少排队和负载波动干扰
- 可用 `#SBATCH --nodelist=` 锁定节点排除异构噪声
- 确认 `hy-smi` 在计算节点可用，SLURM 版本 >= 20.11（`srun --overlap` 依赖）
- 4 种模式 × 5 次 = 20 次 LAMMPS 作业，预留足够机时
- 如机时紧张，可先只跑 bare + pb_dcu10 两组做快速对比
