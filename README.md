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

### 基本命令

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

#### 3. 提交监控作业
提交SLURM脚本并启动性能监控：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output
```

对于 LSF 平台，使用 `--platform lsf`（脚本为 csh/bash wrapper，内部自行调用 `bsub`）：
```bash
./perfbench.py -s /path/to/submit_script.csh -t 60 -o /path/to/output --platform lsf
```

#### 5. 启用加速卡监控
通过 `--accelerator` 参数指定加速卡类型（当前支持 `dcu` / `matrix`），在所有计算节点自动采集：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output --accelerator dcu
```

指定加速卡独立的采样间隔（秒）：
```bash
./perfbench.py -s /path/to/script.slurm -t 60 -o /path/to/output --accelerator dcu --accelerator-interval 10
```

> 如果 `platform_config.json` 中已设置 `"accelerator_type": "dcu"`，则无需 `--accelerator` 参数，工具会自动启用。

#### 6. 显示版本信息
```bash
./perfbench.py --version
```

### 命令行参数详解

| 参数 | 缩写 | 说明 | 示例 |
|------|------|------|------|
| `-init` | - | 初始化工具环境，安装依赖库 | `./perfbench.py -init` |
| `-v` | - | 运行工具适配性测试 | `./perfbench.py -v` |
| `-s, --script` | - | 指定SLURM/LSF作业脚本路径 | `-s script.slurm/script.sh` |
| `-t, --interval` | - | 设置性能数据采集间隔（秒，必需） | `-t 60` |
| `-o, --output` | - | 指定输出目录路径（必需） | `-o /tmp/output` |
| `--platform` | - | 调度平台类型（`slurm` / `lsf` / `tianhe`） | `--platform lsf` |
| `--accelerator` | - | 加速卡类型（`dcu` / `matrix` / `none`），覆盖配置文件 | `--accelerator dcu` |
| `--accelerator-interval` | - | 加速卡采样间隔（秒），默认使用 `-t` 值 | `--accelerator-interval 10` |
| `--config` | - | 测试配置文件路径（.yaml/.json），启用多规模/支撑软件评测 | `--config test.yaml` |
| `--granularity` | - | 测试粒度：`board`（板卡级，默认）/ `core`（内部核级） | `--granularity core` |
| `--init-config` | - | 生成测试配置模板文件到当前目录 | `--init-config` |
| `--force` | - | 跳过环境检测，仅用于调试 | `--force` |
| `--version` | - | 显示工具版本信息 | `./perfbench.py --version` |

### 完整使用示例

```bash
# 初始化工具
./perfbench.py -init

# 验证环境
./perfbench.py -v

# 提交SLURM作业进行监控（60秒采集间隔）
./perfbench.py -s ./examples/test_programs/sample.slurm -t 60 -o /tmp/perfbench_results

# 提交 LSF 作业进行监控
./perfbench.py -s ./examples/test_programs/sample.sh -t 60 -o /tmp/perfbench_results --platform lsf

# 在海光 DCU 集群上提交作业并采集 DCU 指标（10秒采样间隔）
./perfbench.py -s ./examples/test_programs/sample.slurm -t 60 -o /tmp/perfbench_results --accelerator dcu --accelerator-interval 10

# 生成多规模测试配置模板
./perfbench.py --init-config

# 使用配置文件进行多规模可扩展性评测（应用软件）
./perfbench.py --config test_config_template.yaml -o /tmp/multi_scale_results

# 使用配置文件进行支撑软件前后对比评测
./perfbench.py --config support_test.yaml -o /tmp/support_results

# 指定内部核级粒度（覆盖配置文件中的 granularity）
./perfbench.py --config test_config_template.yaml --granularity core -o /tmp/results
```

## 输出说明

工具执行完成后，会在指定的输出目录下创建一个带时间戳的文件夹，格式为 `perfbench_YYYYMMDD_HHMMSS`，其中包含：

| 文件/目录 | 说明 |
|---------|------|
| `modified_script.slurm` | 修改后的SLURM脚本（注入了监控代码） |
| `monitor_data/` | 性能监控数据文件 |
| `dcu_logs/` | 海光 DCU 监控日志（启用 DCU 监控时生成，每节点一个文件） |
| `perfbench.log` | 详细的执行日志 |
| `performance_report.json` | 结构化的性能数据分析报告 |
| `efficiency_report.pdf` | PDF格式的可视化报告（如生成） |
| `test_plan.md` | 测试大纲（`--config` 模式自动生成，符合§3.1） |
| `test_report.md` | 完整评测报告（`--config` 模式自动生成，符合§3.2） |
| `test_report.json` | 结构化评测结果（`--config` 模式自动生成） |

### 性能报告内容

生成的报告包含以下关键性能指标：

- **平台信息**：运行的超算平台名称
- **节点数量**：作业使用的计算节点数
- **应用名称**：作业名称
- **核心数量**：使用的CPU核心总数
- **并行效率**：计算得出的并行度效率（相对于基准配置）
- **运行时间**：作业总运行时间
- **DCU 指标**（启用 DCU 监控时）：平均/峰值 DCU 利用率、显存使用率、功耗、温度

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

## 加速卡监控说明

PerfBench 通过独立的加速卡监控层支持不同类型的加速器指标采集，当前已实现海光 DCU（`hy-smi`）。加速卡监控与调度平台（SLURM / LSF / 天河）完全解耦，可自由组合。

### 启用方式

两种方式任选其一：

1. **配置文件**：在 `perfbench/platform_config.json` 中设置 `"accelerator_type": "dcu"`
2. **CLI 参数**：提交时添加 `--accelerator dcu`

### 工作原理

- 在作业脚本副本中注入 DCU 采样块（原始脚本不修改）
- 通过 `srun --overlap` 在所有计算节点上启动后台 `hy-smi` 采样循环
- 每个节点写入独立日志文件到 `{output_dir}/dcu_logs/dcu_hysmi_{hostname}.log`
- 作业结束后 SLURM cgroup 自动清理采样进程
- PerfBench 解析所有节点日志，汇总 DCU 利用率、显存、功耗、温度等指标

### 采集指标

| 指标 | 来源 | 说明 |
|------|------|------|
| DCU% | `hy-smi` 默认输出 | 计算引擎利用率 |
| VRAM% | `hy-smi` 默认输出 | 显存使用率 |
| AvgPwr | `hy-smi` 默认输出 | 平均功耗 (W) |
| Temp | `hy-smi` 默认输出 | 温度 (°C) |
| SCLK/MCLK | `hy-smi` 默认输出 | 系统/显存时钟频率 |

### 配置项

`platform_config.json` 中的加速卡相关字段：

```json
{
    "accelerator_type": "dcu",
    "accelerator_sampling_interval": null
}
```

- `accelerator_type`：加速卡类型，可选 `"dcu"` / `"matrix"` / `"none"`（不启用）
- `accelerator_sampling_interval`：加速卡采样间隔（秒），为 `null` 时使用全局 `-t` 参数值

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
│   ├── platform_config.json  # 平台配置文件（运行时唯一配置源）
│   ├── core/                 # 核心功能模块
│   │   ├── initializer.py    # 环境初始化
│   │   ├── script_processor.py # 评测执行器（run_evaluation）
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
│   ├── test_config_template.json # 多规模测试配置模板（JSON）
│   ├── orchestrator/          # 编排引擎（多规模/支撑软件评测）
│   │   ├── config_loader.py   # 测试配置加载器（YAML/JSON 双格式）
│   │   ├── multi_scale.py     # 多规模自动提交编排器
│   │   └── before_after.py    # 支撑软件前后对比编排器
│   ├── analysis/             # 领域分析层
│   │   ├── metrics.py        # 指标计算器（并行度查表/效率，对标规范公式）
│   │   ├── scalability.py    # 可扩展性计算（强/弱可扩展并行效率）
│   │   ├── accuracy.py       # 数值模拟精度（绝对误差/相对误差/RMSE）
│   │   ├── improvement.py    # 支撑软件性能提升率（6个公式）
│   │   └── config_reader.py  # 平台配置读取器
│   └── utils/                # 工具函数
│       ├── logger.py         # 日志管理
│       ├── script_parser.py   # 脚本解析器（SLURM #SBATCH / LSF bsub 命令行）
│       └── system_checker.py # 系统环境检查
```

## 许可证

MIT License - 详见项目根目录的 LICENSE 文件

## 联系方式

遇到问题或有建议？请提交Issue或Pull Request。
