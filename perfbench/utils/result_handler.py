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
        if self.cmd_name == "sacct":
            # print("The elapsed time is:" + self.data[-1]["Elapsed"])
            from datetime import datetime
            dt = datetime.strptime(self.data[-1]["Elapsed"], "%H:%M:%S")
            elapsed_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
            print(f"Elapsed time in seconds: {elapsed_seconds}")
            return elapsed_seconds
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
    try:
        # 获取当前模块的路径，向上两级到达perfbench目录
        module_path = Path(__file__).resolve()
        config_path = module_path.parent.parent / 'platform_config.yaml'
        
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
    
  
if __name__ == "__main__":
    test_result = Result("sacct", "G:/PerfBench/logs", 10)
    print(test_result.data)