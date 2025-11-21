import io
import os
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import white, black, lightgrey
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from perfbench.utils.logger import get_logger

logger = get_logger()

# 网格配置
GRID_STEP = 20          # 网格间隔（单位：pt，1 pt = 1/72 英寸）
LABEL_EVERY = 5         # 每隔多少条线标一次数字
LINE_WIDTH_THIN = 0.3
LINE_WIDTH_BOLD = 0.7
GRID_COLOR = lightgrey  # 网格线颜色
AXIS_COLOR = black      # 轴线和坐标文字颜色
FONT_SIZE = 6           # 坐标标注字号

# 默认字体路径（可以根据需要修改）
DEFAULT_FONT_PATH = "Arial.ttf"
DEFAULT_FONT_NAME = "CJKFont"

def create_overlay(page_width, page_height, overrides_for_page, font_path=DEFAULT_FONT_PATH, font_name=DEFAULT_FONT_NAME):
    """
    为单页创建一张只包含覆写内容的 PDF 页面（作为 overlay）。
    """
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # 注册中文字体
    pdfmetrics.registerFont(TTFont(font_name, font_path))
    c.setFont(font_name, 18)

    for x, y, text, w, h in overrides_for_page:
        # 1. 画白色矩形盖住原内容（可选）
        if w > 0 and h > 0:
            c.setFillColor(white)
            c.rect(x, y, w, h, fill=1, stroke=0)

        # 2. 写文本（黑色）
        c.setFillColor(black)
        # 注意：ReportLab 的原点也是左下
        c.drawString(x + 2, y + h / 2 - 4, text)

    c.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]

def create_grid_overlay(page_width, page_height):
    """
    为一页生成网格 overlay（同尺寸透明页，上面画网格+坐标）
    """
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # 画竖线
    x = 0
    while x <= page_width:
        # 粗线：坐标轴或 LABEL_EVERY 的倍数
        if x == 0:
            c.setStrokeColor(AXIS_COLOR)
            c.setLineWidth(LINE_WIDTH_BOLD)
        elif (x / GRID_STEP) % LABEL_EVERY == 0:
            c.setStrokeColor(GRID_COLOR)
            c.setLineWidth(LINE_WIDTH_BOLD)
        else:
            c.setStrokeColor(GRID_COLOR)
            c.setLineWidth(LINE_WIDTH_THIN)

        c.line(x, 0, x, page_height)

        # 写坐标标签（底部）
        if (x / GRID_STEP) % LABEL_EVERY == 0:
            c.setFillColor(AXIS_COLOR)
            c.setFont("Helvetica", FONT_SIZE)
            c.drawString(x + 1, 2, str(int(x)))

        x += GRID_STEP

    # 画横线
    y = 0
    while y <= page_height:
        if y == 0:
            c.setStrokeColor(AXIS_COLOR)
            c.setLineWidth(LINE_WIDTH_BOLD)
        elif (y / GRID_STEP) % LABEL_EVERY == 0:
            c.setStrokeColor(GRID_COLOR)
            c.setLineWidth(LINE_WIDTH_BOLD)
        else:
            c.setStrokeColor(GRID_COLOR)
            c.setLineWidth(LINE_WIDTH_THIN)

        c.line(0, y, page_width, y)

        # 写坐标标签（左侧）
        if (y / GRID_STEP) % LABEL_EVERY == 0:
            c.setFillColor(AXIS_COLOR)
            c.setFont("Helvetica", FONT_SIZE)
            c.drawString(2, y + 2, str(int(y)))

        y += GRID_STEP

    c.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]

def generate_certificate(report_info, out_dir, input_template="certificate.pdf", font_path=DEFAULT_FONT_PATH):
    """
    生成性能测试证书海报
    
    Args:
        report_info (dict): 包含报告信息的字典，需要包含以下键：
            - platform: 平台名称
            - node_num: 节点数量
            - app_name: 应用名称
            - core_num: 核心数量
            - eff: 效率信息
            - time: 时间信息
        out_dir (str): 输出目录路径
        input_template (str): 输入模板PDF文件名或路径
        font_path (str): 字体文件路径
    
    Returns:
        str: 生成的最终PDF文件路径
    """
    # 确保输出目录存在
    os.makedirs(out_dir, exist_ok=True)
    
    # 检查输入模板是否为完整路径，如果不是则使用相对路径
    if not os.path.isabs(input_template):
        # 假设模板在当前目录或与脚本相同的目录
        if os.path.exists(input_template):
            template_path = input_template
        else:
            # 尝试使用脚本所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            template_path = os.path.join(script_dir, input_template)
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"找不到模板文件: {input_template}")
    else:
        template_path = input_template
    
    # 生成OVERRIDES列表
    OVERRIDES = [
        (0, 200, 446, report_info.get("platform", ""), 0, 0),
        (0, 200, 388, report_info.get("node_num", ""), 0, 0),
        (0, 200, 332, report_info.get("app_name", ""), 0, 0),
        (0, 200, 275, report_info.get("core_num", ""), 0, 0),
        (0, 200, 216, report_info.get("eff", ""), 0, 0),
        (0, 300, 141, report_info.get("time", ""), 0, 0),
        (0, 100, 115, "", 0, 0),
    ]
    
    # 定义文件名
    final_pdf = os.path.join(out_dir, "certificate_final.pdf")
    
    try:
        # 添加文本内容到PDF
        reader = PdfReader(template_path)
        writer = PdfWriter()

        # 按页组织需要覆写的项目
        page_to_items = {}
        for page_idx, x, y, text, w, h in OVERRIDES:
            page_to_items.setdefault(page_idx, []).append((x, y, text, w, h))

        for i, page in enumerate(reader.pages):
            if i in page_to_items:
                # 获取原页面大小
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)

                overlay_page = create_overlay(page_width, page_height, page_to_items[i], font_path)

                # 合并 overlay 到当前页面
                page.merge_page(overlay_page)

            writer.add_page(page)

        # 保存最终结果
        with open(final_pdf, "wb") as f:
            writer.write(f)
        
        logger.info(f"已生成证书海报: {final_pdf}")
        
        return final_pdf
        
    except Exception as e:
        logger.error(f"生成证书时出错: {str(e)}")
        raise

if __name__ == "__main__":
    # test用法
    sample_report_info = {
        "platform": "HYGON",
        "node_num": "100",
        "app_name": "LAMMPS",
        "core_num": "102400",
        "eff": "18.30%(10 Nodes)",
        "time": "2025.11.3",
    }
    
    output_dir = "./output"
    generate_certificate(sample_report_info, output_dir)