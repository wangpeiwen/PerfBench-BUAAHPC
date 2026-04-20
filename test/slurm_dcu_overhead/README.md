# PerfBench 开销测试

本目录包含用于量化 PerfBench 对被测作业 `job_elapsed_time` 扰动的测试脚本。

## 测试目的

回答核心问题：**PerfBench 的监控/采样行为是否会拖慢被测作业本身的运行时间？**

## 统计口径

- 开销百分比只基于作业级 `job_elapsed_time` 计算，baseline 为 `bare`
- `bare` 直接读取 `sacct.log` 中的 `Elapsed`
- `pb_*` 优先递归读取 PerfBench 在 `--overhead` 模式下写出的 `final_sacct.log`；若不存在，再回退到监控产生的 `sacct_*.log`
- 必要时兼容旧结果目录中的 `performance_report.json.elapsed_time`
- `timing.txt` 只记录外层 end-to-end 时间，保留用于调试，不参与开销计算

## 计入口径说明

| 来源 | 是否计入本次开销百分比 | 说明 |
|------|------------------------|------|
| 计算节点内 DCU 采样 | 是 | 只要它拖慢作业运行，就会反映到 `job_elapsed_time` |
| 登录节点轮询监控 | 是 | 只统计其对作业运行时间的净扰动 |
| Python 前后处理 / 报告生成 | 否 | 这些属于 end-to-end 时间，不纳入本分析 |

## 文件说明

| 文件 | 用途 |
|------|------|
| `overhead_bare.slurm` | 裸跑基准脚本（LAMMPS 10N×4DCU） |
| `run_overhead_test.sh` | 批量驱动脚本，自动执行 4 种模式 × N 次重复；对 `pb_*` 调用 PerfBench 时启用 `--overhead` |
| `analyze_overhead.py` | 结果分析脚本，只基于 `job_elapsed_time` 输出汇总表格、开销百分比、t 检验，并优先读取 `final_sacct.log` |
| `1m_in.lj` | LAMMPS 测例输入脚本 |

## 测试矩阵

| 模式 | DCU 采样 | 登录节点监控 | 说明 |
|------|---------|------------|------|
| bare | 无 | 无 | 直接 `sbatch`，作为 baseline |
| pb_nodcu | 无 | 有 | PerfBench 框架固定扰动，不含 DCU 采样 |
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

```text
分析目录: ../overhead_results_20260418_120000
统计口径: 仅使用 job_elapsed_time；忽略 timing.txt / end-to-end

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
| < 1% | 可忽略，工具对作业运行时间无实质影响 |
| 1% ~ 5% | 可接受，需在报告中注明 |
| > 5% | 需优化采样策略（降低频率、减少 fork 等） |

## 注意事项

- 尽量在集群空闲时段测试，减少调度波动和背景负载干扰
- 可用 `#SBATCH --nodelist=` 锁定节点，排除异构噪声
- 确认 `hy-smi` 在计算节点可用，SLURM 版本 >= 20.11（`srun --overlap` 依赖）
- 对十几秒级短作业，建议开启 PerfBench `--overhead`；它会在 `wait_for_job` 之后额外写出 `final_sacct.log`
- `pb_nodcu` 与 `bare` 的差值表示 PerfBench 框架固定扰动；`pb_dcu10/pb_dcu2` 则是框架加采样扰动
- 如机时紧张，可先只跑 `bare + pb_dcu10` 两组做快速对比
