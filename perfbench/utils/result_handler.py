import os
import glob
import json
from pathlib import Path
from perfbench.utils.logger import get_logger

logger = get_logger() # 获取logger实例

supported_CMD = [
    "sacct",
    "seff",
    "sinfo",
    "sstat",
    "scontrol",
    "bjobs",
    "cnload",
]

class Result:
    def __init__(self, cmd_name, out_dir, interval: int, platform: str = "SLURM"):
        """
        cmd_name: 该result对象对应的命令名称
        out_dir: 本次测试中输出的log文件存放的路径
        interval: 监控间隔
        platform: 平台类型，可选"SLURM"或"Sunway"
        """
        self.cmd_name = cmd_name
        self.out_dir = out_dir
        self.data = [] # 用于存放数据字典的列表
        self.interval = interval
        self.platform = platform
        self.parse_log_files()
        
    def parse_log_files(self):
        """
        对{outDir}路径下的所有由{cmdName}产生的log文件进行分析
        根据平台类型选择相应的解析方法
        """
        try:
            if self.platform == "Sunway":
                if self.cmd_name == "bjobs":
                    self.parse_bjobs()
                else:
                    pass
            else:  # SLURM
                if self.cmd_name == "sacct":
                    self.parse_sacct()
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
    
    def get_elapsed_time(self):
        if self.platform == "Sunway":
            if self.cmd_name == "bjobs":
                return self.get_elapsed_time_sunway()
        else:  # SLURM
            if self.cmd_name == "sacct":
                return self.get_elapsed_time_slurm()
        logger.warning("正在尝试从错误的日志中提取作业完成时间信息")
        return None
    
    def get_elapsed_time_slurm(self):
        """提取SLURM平台的作业运行时间（秒）"""
        if not self.data:
            logger.warning("sacct数据为空")
            return None
        from datetime import datetime
        dt = datetime.strptime(self.data[-1]["Elapsed"], "%H:%M:%S")
        elapsed_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        logger.info(f"SLURM运行时间（秒）: {elapsed_seconds}")
        return elapsed_seconds
    
    def get_elapsed_time_sunway(self):
        """提取申威平台的作业运行时间（秒）"""
        if not self.data:
            logger.warning("bjobs数据为空")
            return None
        # 申威bjobs输出包含Run time或Total time信息
        for row in reversed(self.data):
            if "run_time" in row and row["run_time"]:
                try:
                    elapsed_seconds = int(float(row["run_time"]))
                    logger.info(f"申威运行时间（秒）: {elapsed_seconds}")
                    return elapsed_seconds
                except (ValueError, TypeError):
                    pass
        logger.warning("无法从bjobs数据提取运行时间")
        return None
             
    def parse_sstat(self):
        pass
    
    def parse_sinfo(self):
        pass
    
    def parse_seff(self):
        pass
    
    def parse_scontrol(self):
        pass
    
    def parse_bjobs(self):
        """
        解析申威平台的bjobs日志文件
        bjobs -l输出格式示例：
        User <user> Job <jobid> Job Name <name>, ... Run time: <seconds>, ...
        """
        pattern = os.path.join(self.out_dir, "bjobs_*.log")
        bjobs_files = glob.glob(pattern)
        if not bjobs_files:
            raise Exception("未找到bjobs日志文件")
        
        for file_path in bjobs_files:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = [line.strip() for line in file.readlines() if line.strip()]
                if not lines:
                    continue
                
                filename = os.path.basename(file_path)
                time_stamp = filename[6:-4]  # 获取时间戳
                
                # 解析第一行主要信息
                main_line = lines[0]
                row_dict = {
                    "JobID": None,
                    "JobName": None,
                    "State": None,
                    "run_time": None,
                    "Memory": None,
                    "time_stamp": time_stamp,
                }
                
                # 从bjobs输出解析信息
                import re
                jobid_match = re.search(r'Job <(\d+)>', main_line)
                if jobid_match:
                    row_dict["JobID"] = jobid_match.group(1)
                
                jobname_match = re.search(r'Job Name <([^>]+)>', main_line)
                if jobname_match:
                    row_dict["JobName"] = jobname_match.group(1)
                
                # 查找状态（从多行中查找）
                full_text = '\n'.join(lines)
                state_match = re.search(r'Status <([^>]+)>', full_text)
                if state_match:
                    row_dict["State"] = state_match.group(1)
                
                # 查找运行时间
                time_match = re.search(r'Run time\s+[=:]?\s*(\d+)', full_text, re.IGNORECASE)
                if time_match:
                    row_dict["run_time"] = time_match.group(1)
                
                # 查找内存使用
                mem_match = re.search(r'(?:Memory|Mem)\s+[=:]?\s*(\d+)\s*(?:MB|GB)?', full_text, re.IGNORECASE)
                if mem_match:
                    row_dict["Memory"] = mem_match.group(1)
                
            self.data.append(row_dict)

def get_platform_config():
    """
    从platform_config.json中读取平台配置信息
    """
    try:
        module_path = Path(__file__).resolve()
        config_path = module_path.parent.parent / 'platform_config.json'
        
        with open(config_path, 'r', encoding='utf-8') as file:
            config = json.load(file)
            return config
    except FileNotFoundError:
        logger.error(f"平台配置文件不存在: {config_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"解析JSON配置文件失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"读取配置文件时发生未知错误: {str(e)}")
        return None

def calculate_parallelism(platform_name: str = None, node_num: int = None):
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
    if platform_name == "SW26010":
        res["core_num"] = node_num * 260
        res["method"] = "node_num \times 260"
    elif platform_name == "SW39000":
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

def calculate_efficiency(platform_config: dict, parallelism_info: dict, elapsed_time: int):
    """
    计算并行效率
    参数：
        platform_config: 平台配置字典（包含compared_cores, compared_run_time）
        parallelism_info: 并行度信息字典（包含core_num）
        elapsed_time: 实际运行时间（秒）
    返回：
        效率百分比（float）
    """
    if not parallelism_info or parallelism_info["core_num"] is None:
        logger.warning("并行度信息不完整，无法计算效率")
        return None
    
    if elapsed_time is None or elapsed_time <= 0:
        logger.warning("运行时间不合法，无法计算效率")
        return None
    
    try:
        compared_cores = platform_config.get("compared_cores", 5)
        compared_run_time = platform_config.get("compared_run_time", 60)
        core_num = parallelism_info["core_num"]
        
        # 效率 = (基准配置性能) / (当前配置性能)
        efficiency = (compared_cores * compared_run_time * 10000) / (core_num * elapsed_time) * 100
        return efficiency
    except (KeyError, TypeError, ZeroDivisionError) as e:
        logger.error(f"效率计算失败: {str(e)}")
        return None