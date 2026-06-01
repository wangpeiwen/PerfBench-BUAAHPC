# PerfBench - 超算集群性能基准测试工具

PerfBench是一款轻量级的性能基准测试工具，专为SLURM、LSF等超算调度环境设计。它能自动化地处理作业脚本、收集系统性能数据、计算并行度效率，并生成性能评估报告。

## 特性

- 🔄 **自动化脚本处理**：解析SLURM（`#SBATCH`）和LSF（`bsub` 命令行）作业脚本，自动注入性能监控代码
- 📊 **全面的性能监控**：收集CPU、内存、DCU/GPU等资源使用数据
- 🏗️ **多架构支持**：支持x86_64、aarch64、海光DCU等多种处理器/加速器架构
- 🔍 **性能分析**：计算并行度、运行效率等关键性能指标
- 📝 **自动化报告**：生成结构化的性能评估报告
- 🛡️ **轻量依赖**：仅依赖少量 Python 库（见下方依赖说明），无需网络连接，完全本地化运行
- ✅ **环境自适配**：自动检测和适配运行环境

## 系统要求

- Python 3.6+
- SLURM、LSF 或天河调度系统
- 海光 DCU 监控需要计算节点上可用 `hy-smi` 或 `rocm-smi` 命令
- SLURM 20.11+（DCU 多节点采集依赖 `srun --overlap`）
- 运行权限：需在集群登录节点上执行
- 磁盘空间：需预留足够空间存储监控数据

## 依赖说明

PerfBench 依赖以下 Python 库（通过 `pip install` 安装）：

| 库 | 版本要求 | 用途 |
|----|---------|------|
| `PyYAML` | >=5.1 | 加载 YAML 测试配置文件 |
| `reportlab` | >=3.6.0 | 生成 PDF 覆盖层（证书报告） |
| `pypdf` | >=3.0.0 | 读取 PDF 模板并合并生成最终证书 |

执行 `pip install -e .` 或 `pip install perfbench` 时会自动安装上述依赖。

## 安装

### 方式一：从源码安装

1. 克隆仓库：
```bash
git clone https://your-repo-url/perfbench.git
cd perfbench
```

2. 初始化工具：
```bash
./perfbench.py -init
```

### 方式二：直接使用

确保脚本有执行权限：
```bash
chmod +x perfbench.py
```

## 使用方法

### 推荐使用方式：交互式评测入口

发布后的常规用户推荐直接从交互式入口开始评测。该入口会按用户选择引导完成“应用软件 / 支撑软件”和“节点级 / 卡级 / kernel级”路径选择，并自动调用对应的底层评测流程：

```bash
./perfbench.py --interactive
```

交互式入口的路径映射如下：

| 用户选择 | 实际流程 | 适用场景 |
|---------|---------|---------|
| 应用软件 + 节点级/卡级 | 生成生效 YAML 后进入 `--config` 配置驱动流程 | 应用多规模可扩展性评测 |
| 支撑软件 + 节点级/卡级 | 生成生效 YAML 后进入 `--config` before/after 对比流程 | 支撑软件前后性能提升评测 |
| 应用软件 + kernel级 | 进入 `--script --kernel-profile` 流程 | 单应用 kernel ISA dump 与 profile（`rocprofv3`/`hipprof`） |
| 支撑软件 + kernel级 | 按 before/after 两个脚本顺序进入 `--script --kernel-profile` 流程 | 支撑软件前后 kernel 级观测 |

节点级和卡级会生成一份生效 YAML 配置后进入配置驱动流程；启用 DCU/Matrix 加速卡监控时，最终报告会在保留原始时序日志的同时计算规模合规性指标。kernel级路径不启动登录节点周期监控，也不启用 DCU/Matrix 加速卡时序监控，只保留 kernel ISA dump 与二次 profile（`rocprofv3`/`hipprof`）相关采集。

### 首次使用前的环境准备

#### 1. 初始化工具环境
在第一次使用时，初始化工具运行环境，安装必要的依赖库：
```bash
./perfbench.py -init
```

#### 2. 验证环境配置
运行环境检查，确保系统满足工具运行要求：
```bash
./perfbench.py -v
```

### 高级/自动化命令行入口

以下命令适用于已有配置文件、批量化脚本、自动化测试或需要绕过交互式向导的场景。

#### 1. 提交监控作业
提交SLURM脚本并启动性能监控：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output
```

对于 LSF 平台，使用 `--platform lsf`（脚本为 csh/bash wrapper，内部自行调用 `bsub`）：
```bash
./perfbench.py -s /path/to/submit_script.csh -t 60 -o /path/to/output --platform lsf
```

#### 2. 启用加速卡监控
通过 `--accelerator` 参数指定加速卡类型（当前支持 `dcu` / `matrix`），在所有计算节点自动采集：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output --accelerator dcu
```

指定加速卡独立的采样间隔（秒）：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output --accelerator dcu --accelerator-interval 10
```

在配置驱动的节点级/卡级应用评测和支撑软件评测中，启用加速卡监控后会自动计算规模合规性：单卡利用率达到 `scale_compliance.active_util_threshold` 判定为 active；单个采样点中 active 卡数占分配卡数的比例达到 `scale_compliance.scale_fraction_threshold` 判定为该采样点覆盖规模；整次运行的覆盖采样点比例达到 `scale_compliance.coverage_threshold` 判定为规模合规。

#### 3. 启用 Kernel ISA Dump 与二次 Profile
在 SLURM + DCU/ROCm 环境中，可通过 `--kernel-profile` 在正式评测后额外提交一次 profile 专用作业。kernel profile 路径不启动登录节点周期监控，也不启用 DCU/Matrix 加速卡时序监控。正式评测作业会用 PerfBench 的 ISA dump launcher 包裹目标命令，启用 `GPU_DUMP_CODE_OBJECT`、`AMD_COMGR_SAVE_TEMPS` 等 dump 开关，并在可用时用 `llvm-objdump` 反汇编生成 `.isa`；二次 profile 作业通过所选 profile 后端采集 kernel/HIP trace、counter 或 stat，耗时不计入正式评测结果。

用户脚本中需要用标记指定要 profile 的计算命令：
```bash
# PERFBENCH_PROFILE_TARGET
srun -n 256 __PERFBENCH_PROFILE__ ./solver input.dat
```

运行示例：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output \
  --platform slurm --kernel-profile \
  --profile-counters "SQ_WAVES,GRBM_GUI_ACTIVE;SQ_INSTS_VALU"
```

如果当前 DTK 环境只提供 `hipprof`，可显式选择 hipprof 后端：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output \
  --platform slurm --kernel-profile \
  --profile-backend hipprof
```

仓库内提供了一个基于 LAMMPS/DCU 的短作业 smoke test，用于在 SLURM + 海光 DCU 机器上快速验证当前 kernel 级观测链路：
```bash
python3 perfbench.py \
  -s test/slurm_dcu_overhead/kernel_smoke_profile.slurm \
  -t 10 \
  -o /tmp/perfbench_kernel_smoke \
  --platform slurm \
  --kernel-profile \
  --profile-counters "SQ_WAVES,GRBM_GUI_ACTIVE"
```


#### 4. 显示版本信息
```bash
./perfbench.py --version
```

### 命令行参数详解

| 参数 | 缩写 | 说明 | 示例 |
|------|------|------|------|
| `-init` | - | 初始化工具环境，安装依赖库 | `./perfbench.py -init` |
| `-v` | - | 运行工具适配性测试 | `./perfbench.py -v` |
| `--interactive` | - | 启动命令行交互式评测入口，按主路径和粒度生成/调用既有评测流程 | `./perfbench.py --interactive` |
| `-s, --script` | - | 指定SLURM/LSF作业脚本路径 | `-s script.slurm/script.sh` |
| `-t, --interval` | - | 设置性能数据采集间隔（秒）；`--script` 模式必需，`--config` 模式可覆盖 `global.monitor_interval` | `-t 60` |
| `-o, --output` | - | 指定输出目录路径（必需） | `-o /tmp/output` |
| `--platform` | - | 调度平台类型（`slurm` / `lsf` / `tianhe`） | `--platform lsf` |
| `--accelerator` | - | 启用加速卡监控类型（`dcu` / `matrix` / `none`）；kernel profile 路径不支持 | `--accelerator dcu` |
| `--accelerator-interval` | - | 加速卡采样间隔（秒），默认使用 `-t` 值 | `--accelerator-interval 10` |
| `--kernel-profile` | - | 在 `--script` 模式下启用 ISA dump + 二次 profile（首版仅 SLURM/DCU） | `--kernel-profile` |
| `--profile-backend` | - | kernel profile 后端，当前支持 `rocprofv3` 和 `hipprof` | `--profile-backend hipprof` |
| `--profile-counters` | - | `rocprofv3` counter 组，分号分隔多组；`hipprof` 后端忽略该参数 | `"SQ_WAVES;GRBM_GUI_ACTIVE"` |
| `--profile-rank-scope` | - | profile 的 MPI rank 范围（`rank0` / `all`），默认 `rank0` | `--profile-rank-scope all` |
| `--profile-output-subdir` | - | kernel profile 输出子目录名，默认 `kernel_profile` | `--profile-output-subdir kp` |
| `--config` | - | 测试配置文件路径（.yaml/.yml），启用多规模/支撑软件评测 | `--config test.yaml` |
| `--init-config` | - | 生成 YAML 测试配置模板文件到当前目录 | `--init-config` |
| `--force` | - | 跳过环境检测，仅用于调试 | `--force` |
| `--version` | - | 显示工具版本信息 | `./perfbench.py --version` |

### 完整使用示例

```bash
# 推荐入口：完成首次初始化和环境验证后，直接进入交互式评测
./perfbench.py --interactive

# 首次使用前：初始化工具
./perfbench.py -init

# 首次使用前：验证环境
./perfbench.py -v

# 高级入口：直接提交 SLURM 作业进行监控（60秒采集间隔）
./perfbench.py -s ./examples/test_programs/sample.slurm -t 60 -o /tmp/perfbench_results

# 高级入口：直接提交 LSF 作业进行监控
./perfbench.py -s ./examples/test_programs/sample.sh -t 60 -o /tmp/perfbench_results --platform lsf

# 高级入口：在海光 DCU 集群上提交作业并采集 DCU 指标（10秒采样间隔）
./perfbench.py -s ./examples/test_programs/sample.slurm -t 60 -o /tmp/perfbench_results --accelerator dcu --accelerator-interval 10

# 高级入口：在 SLURM + DCU/ROCm 环境中执行 kernel profile
./perfbench.py -s ./examples/test_programs/profile_marked.slurm -t 60 -o /tmp/perfbench_results --platform slurm --kernel-profile

# 高级入口：生成 YAML 多规模测试配置模板
./perfbench.py --init-config

# 高级入口：使用配置文件进行多规模可扩展性评测（应用软件）
./perfbench.py --config test_config_template.yaml -o /tmp/multi_scale_results

# 高级入口：使用配置文件进行支撑软件前后对比评测
./perfbench.py --config support_test.yaml -o /tmp/support_results

# 高级入口：使用配置文件并覆盖登录节点监控采样间隔
./perfbench.py --config support_test.yaml -o /tmp/support_results -t 30

# 配置驱动流程支持节点级/卡级/内部核级并行度认定：
# global.granularity 可设置为 node、board 或 core
./perfbench.py --config test_config_template.yaml -o /tmp/results
```

配置驱动模式默认使用 YAML 中的 `global.monitor_interval` 作为登录节点监控采样间隔；未设置时默认 60 秒。命令行 `-t/--interval` 会覆盖该配置。`global.granularity` 的 `node` 表示按节点数认定并行规模，`board` 表示按加速卡/核组认定，`core` 表示按处理器内部核认定。内部核级的规模计算使用 `hardware_registry.json` 中的 `boards_per_node` 和 `cores_per_card`，公式为 `节点数 × 每节点卡数/核组数 × 每卡内部核数`。多规模和支撑软件评测会按平台适配器统一流程解析脚本、注入监控、提交作业、等待完成，并从调度日志中解析每次运行的 `elapsed_seconds` 作为规模聚合与 before/after 指标计算输入。若启用加速卡监控，配置驱动报告还会按分配卡数计算平均活跃比例、规模覆盖率、通过率和合规判定。

## 输出说明

工具执行完成后，会在指定的输出目录下创建一个带时间戳的文件夹，格式为 `perfbench_YYYYMMDD_HHMMSS`，其中包含：

| 文件/目录 | 说明 |
|---------|------|
| `modified_script.slurm` | 修改后的SLURM脚本（注入了监控代码） |
| `slurm_<jobid>.out` | SLURM 标准输出（PerfBench 会将 `#SBATCH -o/--output` 重定向到当前结果目录） |
| `slurm_<jobid>.err` | SLURM 标准错误（PerfBench 会将 `#SBATCH -e/--error` 重定向到当前结果目录） |
| `monitor_data/` | 登录节点周期性能监控数据文件（kernel profile 路径不生成） |
| `dcu_logs/` | 海光 DCU 监控日志（启用 DCU 监控时生成，每节点一个文件；kernel profile 路径不启用） |
| `perfbench.log` | 详细的执行日志 |
| `performance_report.json` | 结构化的性能数据分析报告 |
| `efficiency_report.pdf` | PDF格式的可视化报告（如生成） |
| `test_plan.md` | 测试大纲（`--config` 模式自动生成，符合§3.1） |
| `test_report.md` | 完整评测报告（`--config` 模式自动生成，符合§3.2；启用加速卡监控时包含规模合规性表） |
| `test_report.json` | 结构化评测结果（`--config` 模式自动生成；包含每次运行的 `accelerator_summary` 和 `scale_compliance` 字段） |
| `isa_dump/` | ROCm/HIP code object、Comgr 临时文件和 `llvm-objdump` 生成的 `.isa` 文件（启用 `--kernel-profile` 时生成） |
| `kernel_profile/perfbench_isa_dump_launcher.sh` | 正式作业目标命令的 ISA/code object dump launcher |
| `kernel_profile/profile_script.slurm` | 二次 profile 专用作业脚本 |
| `kernel_profile/rocprof/` | `rocprofv3` 输出目录 |
| `kernel_profile/hipprof/` | `hipprof` 输出目录 |
| `kernel_profile/isa_static_summary.json` | PerfBench 对 ISA dump 的轻量静态分析摘要 |
| `kernel_profile/kernel_profile_summary.json` | ISA 静态摘要、profile 作业信息和所选 profile 后端输出汇总 |

### 性能报告内容

生成的报告包含以下关键性能指标：

- **硬件信息**：运行的计算硬件名称
- **节点数量**：作业使用的计算节点数
- **应用名称**：作业名称
- **核心数量**：使用的CPU核心总数
- **并行效率**：计算得出的并行度效率（相对于基准配置）
- **运行时间**：作业总运行时间
- **DCU 指标**（启用 DCU 监控时）：平均/峰值 DCU 利用率、显存使用率、功耗、温度
- **规模合规性**（配置驱动且启用加速卡监控时）：分配卡数、平均活跃比例、规模覆盖率、通过率和合规判定

## 工作流程

```
┌─────────────────────────┐
│   读取用户提交脚本      │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   监控脚本生成          │
│ (注入性能采集代码)      │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   提交监控作业          │
│ (sbatch/bsub提交)       │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   实时性能监控          │
│ (采集系统资源数据)      │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   监控完成              │
│ (等待作业结束)          │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   报告生成              │
│ (分析数据、计算效率)    │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   输出结果文件          │
└─────────────────────────┘
```

## 注意事项

- ⚠️ **必须在SLURM集群登录节点上运行**：工具需要与SLURM命令（如sbatch、sacct）进行交互
- 💾 **预留足够磁盘空间**：长时间的性能监控会产生大量数据
- 🔄 **定期清理历史数据**：建议定期清理旧的监控结果以节省存储
- 🔐 **权限检查**：确保对输出目录有写入权限
- 🧪 **调试模式**：使用 `--force` 参数可跳过环境检查，仅用于开发调试

## Kernel 级 Dump/Profile 说明

`--kernel-profile` 当前只支持 `--script` 单作业模式和 `--platform slurm`。它会拆成两次调度作业：

- 第一次为正式评测作业：按原流程计时和生成正式报告，同时通过 `perfbench_isa_dump_launcher.sh` 包裹脚本中 `__PERFBENCH_PROFILE__` 标记的目标命令，启用 `GPU_DUMP_CODE_OBJECT=1`、`AMD_COMGR_SAVE_TEMPS=1`，收集 code object / Comgr 临时文件，并在 `llvm-objdump` 可用时生成 `.isa`。
- 第二次为 profile 专用作业：不参与正式计时，通过脚本中的 `__PERFBENCH_PROFILE__` 占位符调用共享目录下的 launcher，并由所选 profile 后端采集 kernel/HIP trace、stats 或 counter。`rocprofv3` 后端支持 `--profile-counters`，`hipprof` 后端默认使用 `--stats --hip-trace`。

PerfBench 对 dump 下来的 ISA 只做文本级静态分析，包括 kernel 文件数量、指令数量、VALU/SALU/VMEM/SMEM/LDS/branch/barrier 粗分类比例，以及可识别的 VGPR/SGPR/LDS 元信息。这些结果只能作为性能倾向线索，不能替代 profile 后端给出的实际耗时、实际 occupancy、cache miss 或 stall 信息。PerfBench 不自研 standalone kernel replay，counter 采集中的 replay/multi-pass 行为由所选 profile 后端内部处理。

`test/slurm_dcu_overhead/kernel_smoke_profile.slurm` 和 `test/slurm_dcu_overhead/kernel_smoke_in.lj` 是面向该功能的短作业示例。脚本默认从 `SLURM_SUBMIT_DIR` 下查找输入文件；若不在仓库根目录提交，可设置 `PERFBENCH_REPO_ROOT=/path/to/PerfBench-BUAAHPC` 或 `PERFBENCH_LAMMPS_INPUT=/path/to/kernel_smoke_in.lj`。

## 加速卡监控说明

PerfBench 通过独立的加速卡监控层支持不同类型的加速器指标采集，当前已实现海光 DCU（`hy-smi`/`rocm-smi`）和迈创 Matrix（`matrix-smi`）。加速卡监控与调度平台（SLURM / LSF / 天河）解耦；在配置驱动评测中，解析后的时序数据还会用于规模合规性计算。

### 启用方式

提交时添加 `--accelerator dcu` 或 `--accelerator matrix`。

### 工作原理

- 在作业脚本副本中注入 DCU 采样块（原始脚本不修改）
- 通过 `srun --overlap` 在所有计算节点上启动后台 `hy-smi` 采样循环
- 每个节点写入独立日志文件到共享文件系统的 `{output_dir}/dcu_logs/dcu_hysmi_{hostname}.log`（无跨节点通信）
- 主作业脚本通过 `trap ... EXIT INT TERM` 在退出时主动 kill 采样进程并 wait，确保最后一条记录写入完整后再退出
- PerfBench 解析所有节点日志，汇总加速卡利用率、显存、功耗、温度等指标，并在配置驱动评测中计算 active fraction、scale coverage 和合规判定

### 采集指标

| 指标 | 来源 | 说明 |
|------|------|------|
| DCU% | `hy-smi` 默认输出 | 计算引擎利用率 |
| VRAM% | `hy-smi` 默认输出 | 显存使用率 |
| AvgPwr | `hy-smi` 默认输出 | 平均功耗 (W) |
| Temp | `hy-smi` 默认输出 | 温度 (°C) |
| SCLK/MCLK | `hy-smi` 默认输出 | 系统/显存时钟频率 |

### 配置项


```json
{
}
```


## 天河迈创平台支持

PerfBench 支持天河迈创超算平台的自研调度系统（msub/mqueue/mdel）和迈创加速卡（matrix-smi）。

### 启用方式

通过 `--platform tianhe` 参数指定天河平台：
```bash
./perfbench.py -s /path/to/script.sh -t 60 -o /path/to/output --platform tianhe
```

启用迈创加速卡监控：
```bash
./perfbench.py -s /path/to/script.sh -t 60 -o /path/to/output --platform tianhe --accelerator matrix
```

### 脚本格式

天河平台作业脚本使用 `#MSUB` 注释头：
```bash
#!/bin/bash
#MSUB -J my_job
#MSUB -N 2
#MSUB -c 20
#MSUB -m matrix
#MSUB -q main

# 用户计算代码
mpirun ./my_app
```

### 调度命令

| 命令 | 用途 |
|------|------|
| `msub` | 提交作业 |
| `mqueue` | 查询作业状态 |
| `mdel` | 删除/取消作业 |
| `minfo` | 查看节点信息 |
| `mres` | 资源申请 |

### 迈创加速卡监控

| 指标 | 来源 | 说明 |
|------|------|------|
| Matrix% | `matrix-smi` | 加速卡计算利用率 |
| VRAM% | `matrix-smi` | 显存使用率 |
| AvgPwr | `matrix-smi` | 平均功耗 (W) |
| Temp | `matrix-smi` | 温度 (°C) |

## 故障排除

### 问题：未检测到SLURM环境
**解决方案**：
- 确认当前节点是SLURM集群的登录节点
- 检查SLURM命令是否在PATH中：`which sbatch`
- 尝试使用 `--force` 参数：`./perfbench.py -init --force`

### 问题：脚本解析失败
**解决方案**：
- SLURM 脚本：检查是否包含标准 `#SBATCH` 指令（`--job-name`, `--nodes` 等）
- LSF 脚本：确保脚本中有未注释的 `bsub` 命令行，工具从中提取 `-J`（作业名）、`-n`（进程数）等参数
- 查看详细日志：`perfbench.log`

### 问题：监控数据不完整
**解决方案**：
- 增加采集间隔时间（-t 参数），减少数据压力
- 确保输出目录有足够的磁盘空间
- 检查作业是否正常完成

### 问题：DCU 监控日志为空或未生成
**解决方案**：
- 确认计算节点上 `hy-smi` 或 `rocm-smi` 命令可用：`which hy-smi`
- 检查 SLURM 版本是否 >= 20.11（`srun --overlap` 需要此版本）
- 查看 `dcu_logs/` 目录下是否有 `[WARN]` 标记的失败记录
- 若需要 `module load` 才能使用 `hy-smi`，请在作业脚本中提前加载对应模块

## 研究论文

本项目产出两篇互补的研究论文：

| 论文 | 标题 | 方向 | 目录 |
|------|------|------|------|
| Paper A | Low-Perturbation Performance Testing with Scale Compliance Verification | 芯片级观测 + 规模合规性验证 | `paper-a/` |
| Paper B | Test First, Profile Later: Three-Phase Script Injection for Core-Level Performance Diagnosis | 核级注入诊断（三阶段分离） | `paper-b/` |

## 项目结构

```
perfbench/
├── perfbench.py              # 主程序入口
├── setup.py                  # Python包配置
├── README.md                 # 本文件
├── config/                   # 配置文件目录
├── examples/                 # 示例脚本（预留目录，当前版本不包含）
├── perfbench/
│   ├── __init__.py
│   ├── __main__.py           # CLI主程序
│   ├── interactive_cli.py    # 命令行交互式评测入口
│   ├── hardware_config.json  # 硬件基线配置文件
│   ├── core/                 # 核心功能模块
│   │   ├── initializer.py    # 环境初始化
│   │   ├── job_runner.py      # 作业运行器（run_evaluation）
│   │   ├── script_flow.py     # --script 单作业评测流程
│   │   └── validator.py      # 环境验证器
│   ├── libs/                 # 不同架构的库文件（预留能力，当前版本不包含）
│   ├── report/               # 报告生成模块
│   │   ├── certificate_generator.py  # PDF 证书海报生成
│   │   ├── test_plan_generator.py    # 测试大纲自动生成（符合§3.1）
│   │   └── full_report_generator.py  # 完整评测报告生成（符合§3.2）
│   ├── adapters/             # 适配层（平台 + 加速卡，完全解耦）
│   │   ├── platform/         # 平台适配层
│   │   │   ├── base.py       # 抽象基类 PlatformAdapter
│   │   │   ├── slurm.py      # SLURM 平台适配器
│   │   │   ├── lsf.py        # LSF 平台适配器
│   │   │   └── tianhe.py     # 天河迈创平台适配器（msub/mqueue/mdel）
│   │   └── accelerator/      # 加速卡监控层
│   │       ├── base.py       # 抽象基类 AcceleratorMonitor
│   │       ├── dcu.py        # 海光 DCU (hy-smi) 监控器
│   │       ├── matrix.py     # 迈创 Matrix (matrix-smi) 监控器
│   │       └── none.py       # 空实现（无加速卡）
│   ├── hardware_registry.json # 处理器核数认定配置表（配置化，支持动态扩展）
│   ├── test_config_template.yaml # 多规模测试配置模板（YAML）
│   ├── orchestrator/          # 编排引擎（多规模/支撑软件评测）
│   │   ├── config_flow.py     # --config 配置驱动评测流程
│   │   ├── config_loader.py   # 测试配置加载器（YAML 格式）
│   │   ├── multi_scale.py     # 多规模自动提交编排器
│   │   └── before_after.py    # 支撑软件前后对比编排器
│   ├── analysis/             # 领域分析层
│   │   ├── metrics.py        # 指标计算器（并行度查表/效率，对标规范公式）
│   │   ├── scalability.py    # 可扩展性计算（强/弱可扩展并行效率）
│   │   ├── scale_compliance.py # 规模合规性计算（active fraction / coverage）
│   │   ├── accuracy.py       # 数值模拟精度（绝对误差/相对误差/RMSE）
│   │   ├── improvement.py    # 支撑软件性能提升率（6个公式）
│   │   └── config_reader.py  # 硬件配置读取器
│   └── utils/                # 工具函数
│       ├── logger.py         # 日志管理
│       └── system_checker.py # 系统环境检查
```

## 许可证

MIT License - 详见项目根目录的 LICENSE 文件

## 联系方式

遇到问题或有建议？请提交Issue或Pull Request。
