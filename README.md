# PerfBench - 超算集群性能基准测试工具

PerfBench是一款轻量级的性能基准测试工具，专为SLURM和申威等超算集群设计。它能自动化地处理作业脚本、收集系统性能数据、计算并行度效率，并生成性能评估报告。

## 特性

- 🔄 **自动化脚本处理**：解析和修改SLURM/申威作业脚本，自动注入性能监控代码
- 📊 **全面的性能监控**：收集CPU、内存、GPU等资源使用数据
- 🏗️ **多架构支持**：支持x86_64和aarch64等多种处理器架构
- 🔍 **性能分析**：计算并行度、运行效率等关键性能指标
- 📝 **自动化报告**：生成结构化的性能评估报告
- 🛡️ **轻量依赖**：仅依赖少量 Python 库（见下方依赖说明），无需网络连接，完全本地化运行
- ✅ **环境自适配**：自动检测和适配运行环境

## 系统要求

- Python 3.6+
- SLURM 或申威集群管理系统
- 运行权限：需在集群登录节点上执行
- 磁盘空间：需预留足够空间存储监控数据

## 依赖说明

PerfBench 依赖以下 Python 库（通过 `pip install` 安装）：

| 库 | 版本要求 | 用途 |
|----|---------|------|
| `questionary` | >=1.10.0 | 交互式命令行问答界面 |
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

对于申威平台，添加 `-sw` 参数：
```bash
./perfbench.py -s /path/to/script.sh -t 60 -o /path/to/output -sw
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
| `-s, --script` | - | 指定SLURM/申威作业脚本路径 | `-s script.slurm/script.sh` |
| `-t, --interval` | - | 设置性能数据采集间隔（秒，必需） | `-t 60` |
| `-o, --output` | - | 指定输出目录路径（必需） | `-o /tmp/output` |
| `-sw` | - | 指定为申威平台（可选，默认自动检测） | `-sw` |
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

# 提交申威作业进行监控
./perfbench.py -s ./examples/test_programs/sample.sh -t 60 -o /tmp/perfbench_results -sw
```

## 输出说明

工具执行完成后，会在指定的输出目录下创建一个带时间戳的文件夹，格式为 `perfbench_YYYYMMDD_HHMMSS`，其中包含：

| 文件/目录 | 说明 |
|---------|------|
| `modified_script.slurm` | 修改后的SLURM脚本（注入了监控代码） |
| `monitor_data/` | 性能监控数据文件 |
| `perfbench.log` | 详细的执行日志 |
| `performance_report.json` | 结构化的性能数据分析报告 |
| `efficiency_report.pdf` | PDF格式的可视化报告（如生成） |

### 性能报告内容

生成的报告包含以下关键性能指标：

- **平台信息**：运行的超算平台名称
- **节点数量**：作业使用的计算节点数
- **应用名称**：作业名称
- **核心数量**：使用的CPU核心总数
- **并行效率**：计算得出的并行度效率（相对于基准配置）
- **运行时间**：作业总运行时间

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
│ (sbatch/申威提交)       │
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

## 故障排除

### 问题：未检测到SLURM环境
**解决方案**：
- 确认当前节点是SLURM集群的登录节点
- 检查SLURM命令是否在PATH中：`which sbatch`
- 尝试使用 `--force` 参数：`./perfbench.py -init --force`

### 问题：脚本解析失败
**解决方案**：
- 检查提供的脚本是否为标准SLURM脚本格式
- 确保脚本以 `#!/bin/bash` 开头
- 查看详细日志：`perfbench.log`

### 问题：监控数据不完整
**解决方案**：
- 增加采集间隔时间（-t 参数），减少数据压力
- 确保输出目录有足够的磁盘空间
- 检查作业是否正常完成

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
│   │   └── certificate_generator.py
│   ├── platform/             # 平台适配层（收拢所有平台差异）
│   │   ├── base.py           # 抽象基类 PlatformAdapter
│   │   ├── slurm.py          # SLURM 平台适配器
│   │   └── sunway.py         # 申威平台适配器
│   ├── analysis/             # 领域分析层
│   │   ├── log_parser.py     # 日志解析器（Result 类）
│   │   ├── metrics.py        # 指标计算器（并行度/效率）
│   │   └── config_reader.py  # 平台配置读取器
│   └── utils/                # 工具函数
│       ├── logger.py         # 日志管理
│       ├── monitoring.py     # 脚本准备器 + 监控执行器
│       └── system_checker.py # 系统环境检查
```

## 许可证

MIT License - 详见项目根目录的 LICENSE 文件

## 联系方式

遇到问题或有建议？请提交Issue或Pull Request。