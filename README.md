# PerfBench - SLURM集群性能基准测试工具

PerfBench是一个专为SLURM集群设计的性能基准测试工具，它可以自动化地修改和提交SLURM作业脚本，收集运行时性能数据，并生成分析报告。

## 特性

- 自动解析和修改SLURM作业脚本
- 自动收集CPU、内存、GPU等资源使用情况
- 支持x86_64和aarch64架构
- 无需外部网络依赖
- 自动化的环境适配性检测

## 安装

1. 克隆仓库：
```bash
git clone https://your-repo-url/perfbench.git
cd perfbench
```

2. 初始化环境：
```bash
./perfbench.py -init
```

## 使用方法

### 基本命令

1. 初始化工具：
```bash
./perfbench.py -init
```

2. 运行适配性测试：
```bash
./perfbench.py -v
```

3. 提交监控作业：
```bash
./perfbench.py -s /path/to/slurm/script.slurm -t 60 -o /path/to/output
```

### 参数说明

- `-init`: 初始化工具环境
- `-v`: 运行工具适配性测试
- `-s, --script`: 指定SLURM脚本路径
- `-t, --interval`: 设置性能数据采集间隔（秒）
- `-o, --output`: 指定输出目录路径
- `--version`: 显示版本信息

## 输出说明

工具会在指定的输出目录下创建一个新的文件夹，格式为：`perfbench_YYYYMMDD_HHMMSS`，包含：

- 修改后的SLURM脚本
- 性能监控数据
- 运行日志
- 分析报告

## 注意事项

1. 工具必须在SLURM集群的登录节点上运行
2. 确保有足够的磁盘空间存储监控数据
3. 建议定期清理旧的监控数据