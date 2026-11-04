# -*- coding: utf-8 -*-  # 指定脚本编码为 UTF-8
"""图4：三种船型在不同规模组中 EEXI 对碳强度的解释力（R²）。

输入：
    tables/model_results.csv（由 03_model.py 生成）
输出：
    figures/fig04_r2_by_type_size.png / .pdf
    figures/fig04_statistics.csv

运行方式：
    conda activate shipping
    python analysis/plot_r2_groups.py
"""

import sys  # 导入系统模块，用于打印解释器路径
from pathlib import Path  # 导入路径模块，用于拼接项目相对路径
import numpy as np  # 导入 numpy，用于数值与坐标计算
import pandas as pd  # 导入 pandas，用于读取模型结果表
import matplotlib  # 导入 matplotlib 主模块
matplotlib.use("Agg")  # 使用无界面后端，命令行环境也能正常出图
import matplotlib.pyplot as plt  # 导入绘图接口
from matplotlib import font_manager  # 导入字体管理，用于挑选中文字体
from matplotlib.patches import Patch  # 导入色块，用于自定义图例
from matplotlib.lines import Line2D  # 导入线条，用于绘制参照线图例

# ==================== 参数区（集中配置） ====================  # 参数区标题
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 由脚本位置推导项目根目录
INPUT_FILE = PROJECT_ROOT / "tables" / "model_results.csv"  # 模型结果汇总表
OUTPUT_DIR = PROJECT_ROOT / "figures"  # 图表输出目录
PNG_FILE = OUTPUT_DIR / "fig04_r2_by_type_size.png"  # 输出 PNG 路径
PDF_FILE = OUTPUT_DIR / "fig04_r2_by_type_size.pdf"  # 输出 PDF 路径
STATS_FILE = OUTPUT_DIR / "fig04_statistics.csv"  # 图4 专用数据表
SHIP_TYPES = ["Container ship", "Bulk carrier", "Oil tanker"]  # 三种船型的英文原值
SHIP_LABELS = ["集装箱船", "散货船", "油船"]  # 三种船型的中文标签
SIZE_GROUPS = ["Small", "Medium", "Large"]  # 三个规模组的英文原值
SIZE_LABELS = ["小船组", "中船组", "大船组"]  # 三个规模组的中文标签
COLORS = ["#4477AA", "#228833", "#EE9944"]  # 与图1、图3 保持一致的配色
REFERENCE_R2 = 0.4595  # 全样本 M3 的 R²，作为对照虚线
ALPHA = 0.05  # 显著性水平
LEVERAGE_THRESHOLD = 0.2  # 最大杠杆值阈值，超过视为估计不稳健
BAR_WIDTH = 0.26  # 单根柱子的宽度
DECIMALS = 3  # 柱顶 R² 标注保留的小数位
FONT_SIZE = 11  # 全局基础字号

# 中文字体候选：覆盖 Windows、macOS 与常见 Linux 发行版
CJK_FONTS = ["Microsoft YaHei", "SimHei", "PingFang SC", "Hiragino Sans GB",
             "Heiti SC", "Arial Unicode MS", "Noto Sans CJK SC",
             "Source Han Sans SC", "WenQuanYi Zen Hei"]  # 字体候选列表
installed = {font.name for font in font_manager.fontManager.ttflist}  # 收集本机已安装字体
font = next((name for name in CJK_FONTS if name in installed), None)  # 取第一个可用中文字体
if font is None:  # 如果本机没有任何候选中文字体
    print("[警告] 未找到中文字体，中文可能显示为方块；建议安装 Noto Sans CJK SC。")  # 打印提示
    font = "DejaVu Sans"  # 回退到默认字体，保证脚本不中断
plt.rcParams.update({  # 统一设置绘图参数
    "font.sans-serif": [font, "DejaVu Sans"],  # 优先中文字体，其次默认字体
    "axes.unicode_minus": False,  # 正常显示负号
    "font.size": FONT_SIZE,  # 设置基础字号
    "pdf.fonttype": 42,  # 让 PDF 嵌入 TrueType 字体，避免乱码
})


def load_group_results() -> pd.DataFrame:  # 定义读取并整理 9 组结果的函数
    """读取模型结果表，筛出 9 个异质性模型并补充标记列。"""  # 函数说明
    if not INPUT_FILE.exists():  # 如果模型结果表不存在
        raise FileNotFoundError(
            f"未找到 {INPUT_FILE}，请先运行 python analysis/03_model.py"
        )  # 提示先跑 03
    data = pd.read_csv(INPUT_FILE)  # 读取模型结果汇总表
    required = {"section", "model_id", "n", "r2", "coef_eexi", "p_hc3", "note"}  # 需要的字段
    missing = required - set(data.columns)  # 计算缺失字段
    if missing:  # 如果有字段缺失
        raise ValueError(f"model_results.csv 缺少字段：{sorted(missing)}")  # 报错并列出缺失字段
    rows = data.loc[  # 筛选 9 组异质性回归
        (data["section"] == "heterogeneity")  # 只看异质性分区
        & (data["model_id"].str.contains(" / ", regex=False))  # 模型编号里含“ / ”的 9 组
    ].copy()  # 复制一份，避免修改原表
    if len(rows) != 9:  # 如果筛出来不是 9 行
        raise ValueError(f"应找到 9 个分组模型，实际找到 {len(rows)} 个，请检查 03_model.py 的结果")  # 报错
    rows["ship_type"] = rows["model_id"].str.split(" / ").str[0]  # 拆出船型
    rows["size_group"] = rows["model_id"].str.split(" / ").str[1]  # 拆出规模组
    expected = {(ship, size) for ship in SHIP_TYPES for size in SIZE_GROUPS}  # 期望的 9 个组合
    found = set(zip(rows["ship_type"], rows["size_group"]))  # 实际找到的组合
    if found != expected:  # 如果组合不完整或不匹配
        raise ValueError(f"分组组合不完整，缺少：{sorted(expected - found)}")  # 报错并列出缺失组合
    rows["max_h"] = (  # 从备注中提取最大杠杆值
        rows["note"].astype(str).str.extract(r"max_h=([0-9.]+)", expand=False).astype(float)  # 正则提取数字
    )  # 结束提取
    rows["not_significant"] = rows["p_hc3"] >= ALPHA  # 标记 HC3 下不显著的组
    rows["high_leverage"] = rows["max_h"].fillna(0.0) > LEVERAGE_THRESHOLD  # 标记高杠杆组
    rows["flag"] = rows.apply(_make_flag, axis=1)  # 生成图上的符号标记
    ship_order = {name: index for index, name in enumerate(SHIP_TYPES)}  # 船型排序映射
    size_order = {name: index for index, name in enumerate(SIZE_GROUPS)}  # 规模组排序映射
    rows["ship_order"] = rows["ship_type"].map(ship_order)  # 加入船型顺序
    rows["size_order"] = rows["size_group"].map(size_order)  # 加入规模组顺序
    rows = rows.sort_values(["size_order", "ship_order"]).reset_index(drop=True)  # 按规模组、船型排序
    return rows  # 返回整理后的 9 行


def _make_flag(row: pd.Series) -> str:  # 定义符号标记函数
    """根据显著性与杠杆值生成 † / △ 标记。"""  # 函数说明
    flag = ""  # 初始化空标记
    if bool(row["not_significant"]):  # 如果 HC3 下不显著
        flag += "†"  # 追加不显著符号
    if bool(row["high_leverage"]):  # 如果组内存在高杠杆点
        flag += "△"  # 追加高杠杆符号
    return flag  # 返回标记字符串


def plot_groups(rows: pd.DataFrame) -> None:  # 定义绘图函数
    """绘制 9 组 R² 的分组柱状图，并保存 PNG 与 PDF。"""  # 函数说明
    fig, ax = plt.subplots(figsize=(10.5, 6.2))  # 创建画布与坐标轴
    fig.subplots_adjust(left=0.085, right=0.985, top=0.90, bottom=0.24)  # 手动留出底部图注空间
    x = np.arange(len(SIZE_GROUPS), dtype=float)  # 三个规模组的中心横坐标
    for index, (ship_type, label, color) in enumerate(zip(SHIP_TYPES, SHIP_LABELS, COLORS)):  # 遍历三种船型
        offsets = x + (index - 1) * BAR_WIDTH  # 计算当前船型三根柱子的横坐标
        subset = rows[rows["ship_type"] == ship_type].set_index("size_group").reindex(SIZE_GROUPS)  # 取出当前船型的三组
        bars = ax.bar(  # 绘制当前船型的三根柱子
            offsets,  # 柱子横坐标
            subset["r2"].to_numpy(float),  # 柱子高度（R²）
            width=BAR_WIDTH,  # 柱子宽度
            color=color,  # 柱子颜色
            edgecolor="white",  # 柱子边框颜色
            linewidth=0.8,  # 边框线宽
            label=label,  # 图例标签
            zorder=3,  # 图层顺序，保证柱子压在网格上方
        )  # 结束绘图
        for bar, (size_group, row) in zip(bars, subset.iterrows()):  # 遍历每根柱子
            value = float(row["r2"])  # 当前组的 R²
            ax.text(  # 在柱顶标注 R² 与样本量
                bar.get_x() + bar.get_width() / 2,  # 柱顶中心横坐标
                value + 0.012,  # 柱顶上方一点
                f"{value:.{DECIMALS}f}{row['flag']}\nn={int(row['n'])}",  # 数值、标记与样本量
                ha="center",  # 水平居中
                va="bottom",  # 垂直对齐到底部
                fontsize=8.8,  # 标注字号
                linespacing=1.15,  # 两行文字的行距
            )  # 结束标注
    ax.axhline(  # 绘制全样本参照线
        REFERENCE_R2,  # 参照线高度
        color="#555555",  # 线条颜色
        linestyle="--",  # 虚线样式
        linewidth=1.2,  # 线宽
        label=f"全样本 M3 R² = {REFERENCE_R2:.4f}",  # 图例标签
        zorder=2,  # 图层顺序，位于柱子上方但低于标注
    )  # 结束参照线
    ax.set_xticks(x, SIZE_LABELS)  # 设置横轴刻度与中文标签
    ax.set_xlim(-0.55, len(SIZE_GROUPS) - 0.45)  # 设置横轴范围，避免柱子贴边
    ax.set_ylim(0, 0.85)  # 设置纵轴范围
    ax.set_ylabel("组内模型 R²")  # 设置纵轴标题
    ax.set_xlabel("船型内规模组（按 total_co2 三分位）")  # 设置横轴标题
    ax.set_title(  # 设置图标题
        "图4  三种船型在不同规模组中 EEXI 对运营碳强度的解释力",  # 标题文字
        loc="left",  # 左对齐
        fontsize=15,  # 标题字号
        fontweight="bold",  # 标题加粗
        pad=12,  # 标题与图的距离
    )  # 结束标题设置
    ax.yaxis.grid(True, color="#E3E7EB", linewidth=0.8)  # 只保留水平网格
    ax.set_axisbelow(True)  # 让网格位于柱子下方
    ax.spines[["top", "right"]].set_visible(False)  # 去掉上、右两条边框
    handles = [Patch(facecolor=color, edgecolor="white", label=label)  # 为三种船型生成图例色块
               for color, label in zip(COLORS, SHIP_LABELS)]  # 遍历配色与中文标签
    handles.append(Line2D([0], [0], color="#555555", linestyle="--", linewidth=1.2,  # 追加参照线图例
                          label=f"全样本 M3 R² = {REFERENCE_R2:.4f}"))  # 设置参照线图例文字
    ax.legend(handles=handles, loc="upper left", ncol=4, frameon=False, fontsize=9)  # 左上角单行放四个图例
    fig.text(  # 在画布底部写图内说明
        0.012,  # 左侧起点
        0.02,  # 底部起点
        "注：† 表示 HC3 稳健标准误下 p≥0.05；△ 表示组内最大杠杆值>0.2，估计对单一船舶敏感、不宜强解释。\n"  # 符号说明
        "柱高为组内模型 R²；n 为组内样本量；虚线为全样本 M3 的 R²=0.4595。",  # 其他说明
        ha="left",  # 左对齐
        va="bottom",  # 底部对齐
        fontsize=8.5,  # 说明文字字号
        color="#475569",  # 说明文字颜色
        linespacing=1.6,  # 行距
    )  # 结束图内说明
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # 确保输出目录存在
    fig.savefig(PNG_FILE, dpi=300, bbox_inches="tight", facecolor="white")  # 保存 PNG
    fig.savefig(PDF_FILE, dpi=300, bbox_inches="tight", facecolor="white")  # 保存 PDF
    plt.close(fig)  # 关闭画布，释放内存
    print(f"已保存：{PNG_FILE}")  # 打印 PNG 路径
    print(f"已保存：{PDF_FILE}")  # 打印 PDF 路径


def save_statistics(rows: pd.DataFrame) -> None:  # 定义保存图4 数据表的函数
    """把 9 组结果整理成图4 专用 CSV，并打印到终端。"""  # 函数说明
    stats = rows[["ship_type", "size_group", "n", "r2", "coef_eexi", "p_hc3", "max_h", "flag"]].copy()  # 选出需要的列
    stats["ship_label"] = stats["ship_type"].map(dict(zip(SHIP_TYPES, SHIP_LABELS)))  # 补充中文船型标签
    stats["size_label"] = stats["size_group"].map(dict(zip(SIZE_GROUPS, SIZE_LABELS)))  # 补充中文规模组标签
    stats = stats[[  # 重新排列列顺序
        "ship_type", "ship_label", "size_group", "size_label",  # 船型与规模组
        "n", "r2", "coef_eexi", "p_hc3", "max_h", "flag",  # 统计量与标记
    ]]  # 结束重排
    stats["r2"] = stats["r2"].round(4)  # R² 保留 4 位小数
    stats["coef_eexi"] = stats["coef_eexi"].round(4)  # EEXI 系数保留 4 位小数
    stats["max_h"] = stats["max_h"].round(3)  # 最大杠杆值保留 3 位小数
    stats.to_csv(STATS_FILE, index=False, encoding="utf-8-sig")  # 保存为 CSV
    print(f"已保存：{STATS_FILE}")  # 打印保存路径
    print("\n图4 数据表：")  # 打印提示
    print(stats.to_string(index=False))  # 打印 9 行数据


def print_caption() -> None:  # 定义图注打印函数
    """打印图4 的四要素图注，便于直接复制进报告。"""  # 函数说明
    print("\n图注（四要素）：")  # 打印提示
    print("① 编号与题名：图4  三种船型在不同规模组中 EEXI 对运营碳强度的解释力（R²）")  # 题名
    print("② 数据来源：2023 年欧盟 MRV 数据库（EMSA THETIS-MRV），分析样本 4,105 艘；"  # 来源
          "分组回归结果取自 tables/model_results.csv。")  # 来源续
    print("③ 关键参数：每根柱对应一个组内 OLS（Y ~ total_co2 + eexi_value），共 9 个模型；"  # 参数
          "标准误为 HC3；规模组按各船型内 total_co2 三分位划分；n 为组内样本量；"  # 参数续
          f"虚线为全样本 M3 的 R²={REFERENCE_R2:.4f}。")  # 参数续
    print("④ 口径说明：Y 为船型内 1%/99% 缩尾后的运营碳强度 [gCO₂/(t·nm)]；"  # 口径
          "EEXI 为设计能效 [gCO₂/(t·nm)]；total_co2 是排放规模代理，不是 DWT/GT。"  # 口径续
          "† 表示 HC3 下 p≥0.05；△ 表示组内最大杠杆值>0.2，该组估计对单一船舶敏感，不宜强解释。")  # 口径续


def main() -> None:  # 定义主函数
    """执行图4 的读取、绘图与保存流程。"""  # 函数说明
    if hasattr(sys.stdout, "reconfigure"):  # 如果标准输出支持重配置
        sys.stdout.reconfigure(encoding="utf-8")  # 设置 UTF-8 输出，避免特殊符号无法编码
    print(f"Python 解释器：{sys.executable}")  # 打印解释器路径，确认运行环境
    print(f"输入文件：{INPUT_FILE}")  # 打印输入路径
    print(f"输出目录：{OUTPUT_DIR}")  # 打印输出目录
    rows = load_group_results()  # 读取并整理 9 组结果
    plot_groups(rows)  # 绘制并保存图4
    save_statistics(rows)  # 保存图4 专用数据表
    print_caption()  # 打印四要素图注
    print("\n图4 生成完成。")  # 打印完成提示


if __name__ == "__main__":  # 判断是否作为主程序运行
    main()  # 调用主函数
