# PerfBench - 性能基准测试工具

PerfBench 是一个专为高性能计算（HPC）集群设计的性能基准测试工具，支持 SLURM、LSF（Sunway）等多种调度器。它可以自动化地修改和提交作业脚本，收集运行时性能数据，生成分析报告，并通过暗水印技术验证证书真伪。

## 核心特性

### 基础功能
- 自动解析和修改 SLURM/LSF 作业脚本
- 自动收集 CPU、内存、GPU 等资源使用情况
- 支持 x86_64 和 aarch64 架构
- 无需外部网络依赖
- 自动化的环境适配性检测

### 高级功能
- **多平台支持**：SLURM（x86 集群）、LSF/cnload（Sunway 超算）
- **智能监控**：登录节点后台监控，支持日志轮转和自恢复机制
- **证书生成**：生成性能测试证书海报（PDF）
- **水印验证**：采用 HMAC-SHA256 算法的暗水印，确保证书真伪可验证

## 安装

### 前置要求
- Python 3.6+
- 在 SLURM/LSF 集群登录节点运行
- 必要的 Python 依赖包

### 安装步骤

1. **克隆仓库**：
```bash
git clone https://github.com/your-org/PerfBench.git
cd PerfBench
```

2. **安装依赖**：
```bash
pip install -r requirements.txt
```

3. **初始化环境**：
```bash
./perfbench.py -init
```

## 使用方法

### 基本命令

#### 1. 初始化工具
```bash
./perfbench.py -init
```
初始化 PerfBench 运行环境，检查 SLURM/LSF 命令可用性，配置必要的环境变量。

#### 2. 环境验证
```bash
./perfbench.py -v
```
运行环境适配性测试，确保工具能正常运行。

#### 3. 提交监控作业（SLURM）
```bash
./perfbench.py -s /path/to/slurm/script.slurm -t 60 -o /path/to/output
```

参数说明：
- `-s, --script`: 指定 SLURM 脚本路径
- `-t, --interval`: 设置性能数据采集间隔（秒）
- `-o, --output`: 指定输出目录路径

#### 4. 提交监控作业（Sunway/LSF）
```bash
./perfbench.py -sw -s /path/to/sunway/script.sh -t 60 -o /path/to/output
```

参数说明：
- `-sw`: 指定为 Sunway/LSF 平台
- `-s, --script`: 指定作业脚本路径
- `-t, --interval`: 采集间隔（秒）
- `-o, --output`: 输出目录路径

## 输出说明

工具会在指定的输出目录下创建一个新的文件夹，格式为：`perfbench_YYYYMMDD_HHMMSS`，包含：

### 文件结构
```
perfbench_20250227_100000/
├── modified_script.slurm          # 修改后的脚本
├── job_node_info.txt              # 作业节点信息
├── sacct_20250227_100000.log      # 资源使用日志（SLURM）
├── seff_20250227_100000.log       # 效率报告（SLURM）
├── cnload_c_*.log                 # 主核负载日志（Sunway）
├── cnload_b_job_*.log             # 从核位图日志（Sunway）
├── certificate_final.pdf          # 生成的证书海报
├── certificate_watermark.json     # 水印验证信息
└── monitor_sunway.pid             # 监控进程 PID（Sunway）
```

## 水印验证机制

### 暗水印特性
PerfBench 生成的证书海报包含不可见的暗水印，用于验证证书真伪：

- **水印算法**：HMAC-SHA256
- **水印数据**：平台名称、节点数、应用名称、生成时间戳
- **验证码**：16 位十六进制字符串，易于记录和分享

### 验证证书

使用提供的验证工具检查证书真伪：

```bash
# 验证单个证书
python perfbench/report/verify_certificate.py /path/to/certificate_watermark.json

# 列出目录中所有证书
python perfbench/report/verify_certificate.py --list /path/to/output
```

### 验证输出示例
```
✓ 证书验证成功！
  平台: HYGON
  节点数: 100
  应用: LAMMPS
  验证码: 7F3C8A9B2E1D4F6C
  生成时间: 2025-02-27T10:00:00.123456
```

## 配置说明

### 平台配置文件

编辑 `perfbench/platform_config.yaml` 配置性能基准参数：

```yaml
platform_name: "DCU Z100"        # 平台名称
compared_cores: 5                # 对比核心数（万核）
compared_run_time: 60            # 对比时间（秒）
```

## 高级功能

### Sunway 平台支持

#### 特殊特性
1. **LSF 作业管理**：自动检测并使用 `bjobs`、`bsub` 等 LSF 命令
2. **cnload 监控**：实时采集主核（Master）和从核（SPE）的运行状态
3. **位图解析**：自动解析 cnload 输出中的十六进制位图，计算核心利用率
4. **自动恢复**：监控脚本支持进程存活检测和自动重启

#### cnload 位图示例
```
原始输出：
SPE0: 0x00FF00FF
SPE1: 0xFFFF0000

解析结果：
SPE0 活跃核心数：16
SPE1 活跃核心数：16
总体利用率：50%
```

### 日志轮转策略

为防止长时间监控导致磁盘满溢，监控脚本内置日志轮转机制：

- **轮转阈值**：10MB
- **轮转命名**：`logname.1`, `logname.2`, ...
- **自动清理**：保留最近 10 个日志文件

### 错误恢复

监控脚本包含以下容错机制：

1. **命令重试**：单个命令失败时最多重试 3 次
2. **进程监控**：后台守护线程检测监控脚本，故障自动重启
3. **优雅退出**：支持 SIGTERM 信号，确保完整的日志记录

## 支持的平台

| 平台 | 架构 | 核心数公式 | 调度器 |
|------|------|----------|--------|
| SW26010 | MIPS | 节点 × 260 | LSF |
| SW39000 | MIPS | 节点 × 390 | LSF |
| Sunway TaihuLight | MIPS | 节点 × 3.45w | LSF |
| 飞腾-64 | ARMv8 | 节点 × 64 | SLURM |
| Matrix2000 | MIPS | 节点 × 256 | SLURM |
| Matrix3000 | MIPS | 节点 × 1648 | SLURM |
| DCU Z100/Z100L | x86 + DCU | 节点 × 288 | SLURM |
| BW1000(80CU) | x86 + DCU | 节点 × 352 | SLURM |
| BW1000(88CU) | x86 + DCU | 节点 × 384 | SLURM |
| Tesla P100/V100 | x86 + GPU | 节点 × (112\|160) | SLURM |

## 工作流程

```
┌─────────────────────────────────────┐
│  用户提交作业脚本                    │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  脚本解析 (Script Parser)           │
│  - 提取 SBATCH/LSF 指令            │
│  - 识别节点数、任务数等参数         │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  作业提交 (Job Submission)          │
│  - SLURM: sbatch 提交               │
│  - LSF: bsub 提交                   │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  后台监控 (Background Monitor)      │
│  - 登录节点轮询监控                 │
│  - 日志轮转与自恢复                 │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  数据分析 (Result Analysis)         │
│  - 并行度计算                       │
│  - 效率评估                         │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  证书生成 (Certificate Generation)  │
│  - 生成 PDF 海报                    │
│  - 嵌入暗水印 (HMAC-SHA256)        │
│  - 生成验证信息                     │
└─────────────────────────────────────┘
```

## 单元测试

项目包含完整的测试套件，覆盖核心功能：

```bash
# 安装测试依赖
pip install pytest pyyaml

# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_result_handler.py -v
pytest tests/test_script_parser.py -v
pytest tests/test_certificate_generator.py -v
```

## 注意事项

1. **环境要求**：工具必须在 SLURM/LSF 集群的登录节点上运行
2. **磁盘空间**：确保有足够的磁盘空间存储监控数据（长时间监控可能占用 GB 级空间）
3. **权限**：需要能够读写输出目录和提交作业的权限
4. **定期清理**：建议定期清理旧的监控数据，防止磁盘满溢
5. **水印验证**：证书水印密钥内置在工具中，仅作真伪验证用途

## 故障排除

### 常见问题

**Q: 提示"SLURM 命令不可用"**
- A: 确保在 SLURM 登录节点运行，或使用 `--force` 标志跳过检查（仅用于调试）

**Q: 监控脚本启动失败**
- A: 检查输出目录的写权限，以及是否有足够的磁盘空间

**Q: 证书验证失败**
- A: 确保 `certificate_watermark.json` 文件完整，未被修改或损坏

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

- 项目主页：https://github.com/your-org/PerfBench
- 问题反馈：https://github.com/your-org/PerfBench/issues
