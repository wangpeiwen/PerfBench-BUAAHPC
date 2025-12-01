import os
import glob
import yaml
from pathlib import Path
from perfbench.utils.logger import get_logger

logger = get_logger() # 获取logger实例

supported_CMD = [
    "sacct",
    "seff",
    "sinfo",
    "sstat",
    "scontrol",
]

class Result:
    def __init__(self, cmd_name, out_dir, interval: int):
        """
        cmd_name: 该result对象对应的命令名称
        out_dir: 本次测试中输出的log文件存放的路径
        """
        self.cmd_name = cmd_name
        self.out_dir = out_dir
        self.data = [] # 用于存放数据字典的列表
        self.interval = interval
        self.parse_log_files()
        
    def parse_log_files(self):
        """
        对{outDir}路径下的所有由{cmdName}产生的log文件进行分析
        """
        try:
            if self.cmd_name == "sacct":
                self.parse_sacct()
            elif self.cmd_name in ("cnload", "cnload_b", "cnload_c"):
                self.parse_cnload_bitmap()
            else:
                pass
        except Exception as e:
            logger.error(f"日志文件解析失败: {str(e)}")
            return None
    
    def get_column_by_name(self, column_name: str):
        """
        返回带时间戳的指定列的结果列表
        """
        res_list = []
        for row in self.data:
            res_list.append(
                {
                    "time_stamp": row["time_stamp"],
                    column_name: row[column_name]
                }
            )
        return res_list
    
    def parse_sacct(self):
        pattern = os.path.join(self.out_dir, "sacct_*.log")
        sacct_files = glob.glob(pattern)
        if not sacct_files:
            raise Exception # 抛出异常
        for file_path in sacct_files:
            with open(file_path, 'r', encoding='utf-8') as file:
                # 处理文件逻辑
                lines = [line.strip() for line in file.readlines() if line.strip()]
                if len(lines) <= 1: # 排除空行
                    continue
                header_line = lines[0] # 获取表头
                headers = [h.strip() for h in header_line.split('|')]
                data = lines[1].split('|')
                filename = os.path.basename(file_path)
                time_stamp = filename[6:-4] # 获取时间戳
                row_dict = {
                    "JobID": None,
                    "JobName": None,
                    "State": None,
                    "Elapsed": None,
                    "MaxRSS": None,
                    "AllocCPUS": None,
                    "time_stamp": time_stamp, # 格式：{YYYYMMDD_hhmmss}
                }
                for i, header in enumerate(headers):
                    row_dict[header] = data[i]
            self.data.append(row_dict)
        return

    def parse_cnload_bitmap(self):
        """
        解析 cnload -b 输出（LSF 神威的从核位图），生成统计数据：每个时间点的激活子核数量、理论并行度、利用率。
        支持两种文件：cnload_b_job_*.log（按 job 输出）和 cnload_b_c_*.log（按节点 / c 参数输出）
        """
        pattern = os.path.join(self.out_dir, "cnload_b_job_*.log")
        bitmap_files = glob.glob(pattern)
        if not bitmap_files:
            pattern2 = os.path.join(self.out_dir, "cnload_b_c_*.log")
            bitmap_files = glob.glob(pattern2)
        if not bitmap_files:
            logger.warning("未发现 cnload 位图日志文件。")
            return

        import re
        for file_path in sorted(bitmap_files):
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_lines = [l.rstrip('\n') for l in f.readlines()]
                lines = [l.strip() for l in raw_lines if l.strip()]
            if not lines:
                continue
            # time stamp 规则：根据文件名抽取
            filename = os.path.basename(file_path)
            # 提取文件名内的时间戳，匹配 YYYYMMDD_HHMMSS
            mtime = re.search(r"(\d{8}_\d{6})", filename)
            if mtime:
                time_stamp = mtime.group(1)
            else:
                time_stamp = filename

            total_active = 0
            total_bits = 0
            groups = []
            # 查找节点信息（以 'vn' 或 'node' 开头）
            nodename = None
            for hline in lines:
                mnode = re.match(r"^(vn\d+|node\d+|[a-zA-Z0-9_\-\.]+)\s+", hline)
                if mnode:
                    nodename = mnode.group(1)
                    break
            # 解析 MiniOS / ValidBitmap / EmployBitmap 表格行
            # 匹配类似： |     SPE0    | 0xFFFFFFFFFFFFFFFF | 0xFFFFFFFFFFFFFFFF |
            node_groups = []
            total_active = 0
            total_bits = 0
            for line in lines:
                # 匹配 MPE 或 SPE 行
                m = re.search(r"\|\s*(MPE|SPE\d+)\s*\|\s*(0x[0-9A-Fa-f]+)\s*\|\s*(0x[0-9A-Fa-f]+)\s*\|", line)
                if m:
                    label = m.group(1)
                    valid_hex = m.group(2)
                    employ_hex = m.group(3)
                    try:
                        valid_int = int(valid_hex, 16)
                        employ_int = int(employ_hex, 16)
                    except Exception:
                        continue
                    # 字符位数
                    group_size = len(valid_hex[2:]) * 4
                    valid_bits = bin(valid_int)[2:].zfill(group_size)
                    employ_bits = bin(employ_int)[2:].zfill(group_size)
                    # 统计激活位
                    active = employ_bits.count('1')
                    total_active += active
                    total_bits += group_size
                    node_groups.append({'label': label, 'valid_hex': valid_hex, 'employ_hex': employ_hex, 'active': active, 'group_size': group_size})

            if not node_groups:
                continue

            if total_bits == 0:
                continue
            # 计算并行度与利用率：总激活 / 总位数
            utilization = round(100.0 * total_active / total_bits, 2) if total_bits else 0.0
            row = {
                'file': filename,
                'node': nodename,
                'time_stamp': time_stamp,
                'total_active': total_active,
                'total_bits': total_bits,
                'utilization_percent': utilization,
                'groups': node_groups
            }
            self.data.append(row)
        return

    def export_cnload_detailed_csv(self, csv_path: str = None):
        """
        导出每个 node / group 的详尽 CSV，包括时间、节点、group label、active、group_size、valid_hex、employ_hex
        """
        import csv
        if not self.data:
            logger.warning("没有 cnload 数据可导出")
            return None
        if not csv_path:
            csv_path = os.path.join(self.out_dir, 'cnload_detailed.csv')
        fieldnames = ['file', 'time_stamp', 'node', 'group_label', 'group_size', 'active', 'valid_hex', 'employ_hex']
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.data:
                for g in row.get('groups', []):
                    writer.writerow({
                        'file': row.get('file'),
                        'time_stamp': row.get('time_stamp'),
                        'node': row.get('node'),
                        'group_label': g.get('label'),
                        'group_size': g.get('group_size'),
                        'active': g.get('active'),
                        'valid_hex': g.get('valid_hex'),
                        'employ_hex': g.get('employ_hex')
                    })
        logger.info(f"cnload 详细数据已导出到: {csv_path}")
        return csv_path

    def export_cnload_csv(self, csv_path: str = None):
        """
        将解析得到的 cnload 位图统计数据导出为 CSV 以方便绘图/分析。
        """
        import csv
        if not self.data:
            logger.warning("没有 cnload 数据可导出")
            return None
        if not csv_path:
            csv_path = os.path.join(self.out_dir, 'cnload_summary.csv')
        fieldnames = ['time_stamp', 'total_active', 'total_bits', 'utilization_percent']
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.data:
                writer.writerow({k: row.get(k) for k in fieldnames})
        logger.info(f"cnload 数据已导出到: {csv_path}")
        return csv_path
    
    def get_elapsed_time(self):
        if self.cmd_name == "sacct":
            # print("The elapsed time is:" + self.data[-1]["Elapsed"])
            from datetime import datetime
            dt = datetime.strptime(self.data[-1]["Elapsed"], "%H:%M:%S")
            elapsed_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
            print(f"Elapsed time in seconds: {elapsed_seconds}")
            return elapsed_seconds
        elif self.cmd_name in ("cnload", "cnload_b", "cnload_c"):
            # 从 cnload 解析的时间戳字段中估算运行时
            if not self.data:
                logger.warning("cnload 数据为空，无法计算运行时")
                return None
            from datetime import datetime
            try:
                first_ts = self.data[0]['time_stamp']
                last_ts = self.data[-1]['time_stamp']
                dt_first = datetime.strptime(first_ts, "%Y%m%d_%H%M%S")
                dt_last = datetime.strptime(last_ts, "%Y%m%d_%H%M%S")
                elapsed_seconds = int((dt_last - dt_first).total_seconds())
                print(f"Elapsed time (cnload) in seconds: {elapsed_seconds}")
                return elapsed_seconds
            except Exception as e:
                logger.warning(f"解析 cnload 时间戳失败: {e}")
                return None
        logger.warning("正在尝试从错误的日志中提取作业完成时间信息")
        return None
             
    def parse_sstat(self):
        pass
    
    def parse_sinfo(self):
        pass
    
    def parse_seff(self):
        pass
    
    def parse_scontrol(self):
        pass

def get_platform_config():
    """
    从platform_config.yaml中读取平台配置信息
    """
    # 获取当前模块的路径，向上两级到达perfbench目录
    module_path = Path(__file__).resolve()
    config_path = module_path.parent.parent / 'platform_config.yaml'
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            return config
    except FileNotFoundError:
        logger.error(f"平台配置文件不存在: {config_path}")
        return None
    except yaml.YAMLError as e:
        logger.error(f"解析YAML配置文件失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"读取配置文件时发生未知错误: {str(e)}")
        return None


def postprocess_cnload_job(out_dir: str, interval: int = 3):
    """
    对指定的输出目录进行基于 cnload 的后处理（位图解析 -> CSV 导出），返回 CSV 路径。
    """
    try:
        cnloader = Result(cmd_name='cnload', out_dir=out_dir, interval=interval)
        cnloader.parse_cnload_bitmap()
        csv_path = cnloader.export_cnload_detailed_csv()
        return csv_path
    except Exception as e:
        logger.error(f"cnload 后处理失败: {str(e)}")
        return None

from typing import Optional


def calculate_parallelism(platform_name: Optional[str] = None, node_num: Optional[int] = None, master_cores: Optional[int] = None):
    """
    根据平台类型和节点数计算并行度
    如果未提供platform_name，从配置文件中读取
    返回值结构：
    {
        "core_num": None,
        "method": None
    }
    """
    # 如果未提供平台名称，从配置文件中读取
    res = {
        "core_num": None,
        "method": None
    }
    # guard for None node_num
    if node_num is None:
        node_num = 1
    if platform_name == "SW26010":
        # Sunway SW26010: prefer master_cores * 64 per node if provided
        if master_cores:
            res["core_num"] = node_num * master_cores * 64
            res["method"] = f"node_num * master_cores({master_cores}) * 64"
        else:
            res["core_num"] = node_num * 260
            res["method"] = "node_num \times 260"
    elif platform_name == "SW39000":
        if master_cores:
            res["core_num"] = node_num * master_cores * 64
            res["method"] = f"node_num * master_cores({master_cores}) * 64"
        else:
            res["core_num"] = node_num * 390
            res["method"] = "node_num \times 390"
    elif platform_name == "飞腾-64":
        res["core_num"] = node_num * 64
        res["method"] = "node_num \times 64"
    elif platform_name == "Matrix2000":
        res["core_num"] = node_num * 256
        res["method"] = "node_num \times 256"
    elif platform_name == "Matrix3000":
        res["core_num"] = node_num * 1648
        res["method"] = "node_num \times 1648"
    elif platform_name in ["DCU Z100", "DCU Z100L"]:
        res["core_num"] = node_num * (256 + 32)
        res["method"] = "node_num \times (4\times DCU_nums + CPU_nums)"
    elif platform_name == "BW1000(80CU)":
        res["core_num"] = node_num * (320 + 32)
        res["method"] = "node_num \times (4\times DCU_nums + CPU_nums)"
    elif platform_name == "BW1000(88CU)":
        res["core_num"] = node_num * (352 + 32)
        res["method"] = "node_num \times (4\times DCU_nums + CPU_nums)"
    elif platform_name == "Tesla P100":
        res["core_num"] = node_num * 112
        res["method"] = "node_num \times 112"
    elif platform_name == "Tesla V100":
        res["core_num"] = node_num * 160
        res["method"] = "node_num \times 160"
    elif platform_name == "Tesla As100":
        res["core_num"] = node_num * 216
        res["method"] = "node_num \times 216"
    else:
        logger.error(f"无法计算并行度：不支持的平台类型。platform_name: {platform_name}, node_num: {node_num}")
        return None
    return res
    
  
if __name__ == "__main__":
    test_result = Result("sacct", "G:/PerfBench/logs", 10)
    print(test_result.data)