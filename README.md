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
 - `--wait`: 等待提交的作业结束并生成后处理报告（用于 Sunway / LSF 的 cnload 后处理）
 
### Sunway / LSF 支持 (神威超算)

PerfBench 现在支持 Sunway/LSF 系统（例如神威超算）。当检测到 LSF 调度器时，工具会：
- 自动将脚本注入 LSF 环境（将 LSB_JOBID 写入 job_node_info）
- 使用 `bsub` 提交作业（脚本会被 `bsub < script` 提交）
- 启动 `monitor_sunway.sh` 轮询 `bjobs` 和 `cnload -b`，并将位图输出存为 `cnload_b_job_*` / `cnload_b_c_*` 文件
- 支持 `--wait` 来等待作业结束并自动导出 `cnload_detailed.csv`（每 node/group 的利用率）、或 `cnload_summary.csv`

示例（Sunway/LSF）：
```bash
python -m perfbench --script ./cg_monitor.sh --interval 3 --output /path/to/out --wait
```

注意：当使用 Sunway 模式时，请确保你的脚本中包含 `MASTER_CORES` 或能推断出 `master_cores`，PerfBench 将使用 `master_cores * 64 * node_num` 计算并行度；否则仍会回退到平台常数（例如 SW26010=260）来计算。

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

## 测试

本项目使用 pytest 编写单元测试，工作流配置已包含在 `.github/workflows/ci.yml` 中。要在本地运行测试：

```bash
pip install pytest
pytest -q
```
