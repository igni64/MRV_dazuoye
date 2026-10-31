# -*- coding: utf-8 -*-  # 指定脚本编码为 UTF-8
"""
01_clean.py：清洗 2023 年 THETIS-MRV 集装箱船、散货船、油船数据。

输入：
    data/raw/thrtis_mrv_2023.xlsx 的 "2023" 工作表
输出：
    data/clean/ships_clean.csv

运行方式：
    conda activate shipping
    python analysis/01_clean.py
"""

import re  # 导入正则模块，用于列名模糊匹配和 EEXI 数值提取
import sys  # 导入系统模块，用于设置标准输出编码
from pathlib import Path  # 导入路径模块，用于拼接项目相对路径
import pandas as pd  # 导入 pandas，用于读取 Excel 和清洗数据

# ==================== 参数区（集中配置） ====================  # 参数区标题
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 由脚本位置推导项目根目录
INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "thrtis_mrv_2023.xlsx"  # 原始 Excel 路径
SHEET_NAME = "2023"  # 原始工作表名称
HEADER_ROW = 2  # 表头行号（0 基，对应 Excel 第 3 行）
OUTPUT_FILE = PROJECT_ROOT / "data" / "clean" / "ships_clean.csv"  # 输出 CSV 路径
TARGET_SHIP_TYPES = ["Container ship", "Bulk carrier", "Oil tanker"]  # 三种目标船型
TARGET_EFFICIENCY = "EEXI"  # 目标能效标识（排除 EEDI/EIV/Not Applicable）
TARGET_YEAR = 2023  # 目标报告年度
EEXI_REGEX = r"EEXI\s*\(([\d.]+)"  # EEXI 数值提取正则，取括号内数字
WINSOR_LOWER_Q = 0.01  # 缩尾下分位点（1%）
WINSOR_UPPER_Q = 0.99  # 缩尾上分位点（99%）
MIN_EEXI_VALUE = 0.0  # EEXI 有效值下限（<=0 视为录入错误）
GROUP_LABELS = ["Small", "Medium", "Large"]  # 三分位分组标签
SIZE_GROUP_COL = "size_group"  # 全样本三分位列名
SIZE_GROUP_WITHIN_COL = "size_group_within_type"  # 船型内三分位列名
VALUE_COLUMNS = ["co2_intensity_winsor", "total_co2", "eexi_value"]  # 重点统计变量
OUTPUT_COLUMNS = [  # 最终输出列（顺序即 CSV 列顺序）
    "imo",  # IMO 编号
    "ship_name",  # 船名
    "ship_type",  # 原始英文船型
    "ship_type_group",  # 船型分组（保留英文原名）
    "report_year",  # 报告年度
    "co2_intensity",  # 原始碳强度（质量口径）
    "co2_intensity_winsor",  # 船型内缩尾后的碳强度
    "total_co2",  # 总 CO2 排放（船大小代理变量）
    "eexi_value",  # EEXI 设计能效数值
    "size_group",  # 全样本三分位分组
    "size_group_within_type",  # 船型内三分位分组
]
OUTPUT_ENCODING = "utf-8-sig"  # 输出编码，兼容 Windows Excel
PREVIEW_ROWS = 5  # 终端预览行数
COLUMN_RULES = {  # 关键列模糊匹配规则
    "imo": {"mode": "startswith", "keywords": ["imo number"], "exclude": []},  # IMO 编号列
    "ship_name": {"mode": "exact", "keywords": ["name"], "exclude": []},  # 船名列
    "ship_type": {"mode": "startswith", "keywords": ["ship type"], "exclude": []},  # 船型列
    "report_year": {"mode": "startswith", "keywords": ["reporting period"], "exclude": []},  # 年度列
    "tech_eff": {"mode": "startswith", "keywords": ["technical efficiency"], "exclude": []},  # 能效列
    "co2_intensity": {  # 碳强度列（质量口径）
        "mode": "startswith",  # 使用前缀匹配
        "keywords": ["annual average co2 emissions per transport work (mass)"],  # 关键词
        "exclude": ["on laden"],  # 排除载货航次专用列
    },  # 结束碳强度规则
    "total_co2": {"mode": "startswith", "keywords": ["total co2 emissions"], "exclude": []},  # 总 CO2 列
}  # 结束列匹配规则


# ==================== 工具函数 ====================  # 工具函数区
def print_section(title: str) -> None:  # 定义分节标题打印函数
    """打印统一格式的分节标题。"""  # 函数说明
    print("\n" + "=" * 80)  # 打印上分隔线
    print(title)  # 打印标题
    print("=" * 80)  # 打印下分隔线


def normalize_column_name(name: object) -> str:  # 定义列名归一化函数
    """统一 CO2 下标、空白和大小写，便于模糊匹配。"""  # 函数说明
    text = str(name)  # 把列名转成字符串
    text = text.replace("₂", "2")  # 把 Unicode 下标 2 转成普通 2
    text = text.replace("CO₂", "CO2")  # 把大写 CO₂ 转成 CO2
    text = text.replace("co₂", "co2")  # 把小写 co₂ 转成 co2
    text = text.replace("\u00a0", " ")  # 把不换行空格转成普通空格
    text = re.sub(r"\s+", " ", text).strip()  # 合并连续空白并去掉首尾空格
    return text.casefold()  # 转成小写并返回


def match_column(column: str, rule: dict) -> bool:  # 定义单列规则匹配函数
    """按 exact/startswith/contains 规则判断列名是否命中。"""  # 函数说明
    norm = normalize_column_name(column)  # 归一化当前列名
    for keyword in rule["keywords"]:  # 遍历规则关键词
        if rule["mode"] == "exact":  # 如果是精确匹配
            hit = norm == keyword  # 判断完全相等
        elif rule["mode"] == "startswith":  # 如果是前缀匹配
            hit = norm.startswith(keyword)  # 判断是否以关键词开头
        else:  # 其他情况按包含匹配
            hit = keyword in norm  # 判断是否包含关键词
        if hit:  # 如果当前关键词命中
            excluded = any(ex in norm for ex in rule["exclude"])  # 检查是否命中排除词
            return not excluded  # 未命中排除词则返回真
    return False  # 所有关键词都没命中则返回假


def resolve_columns(columns: list) -> dict:  # 定义关键列解析函数
    """模糊匹配关键列，匹配失败时打印全部列名并终止。"""  # 函数说明
    resolved = {}  # 保存 key 到原始列名的映射
    print("关键列匹配结果：")  # 打印提示
    for key, rule in COLUMN_RULES.items():  # 遍历每个关键列规则
        matches = [col for col in columns if match_column(col, rule)]  # 找出全部命中列
        print(f"  {key}: {matches!r}")  # 打印候选列
        if not matches:  # 如果一个都没命中
            print(f"[错误] 找不到关键列：{key}，匹配规则：{rule}")  # 打印错误信息
            print("全部列名如下：")  # 打印提示
            for index, column in enumerate(columns):  # 遍历全部列
                print(f"    {index}: {column!r}")  # 打印列位置和列名
            raise SystemExit(f"关键列匹配失败：{key}")  # 终止脚本，避免瞎猜
        matches.sort(key=lambda col: len(normalize_column_name(col)))  # 按归一化长度排序
        resolved[key] = matches[0]  # 选择最短候选列
        if len(matches) > 1:  # 如果候选列不止一个
            print(f"  [提示] {key} 命中多列，已选择：{matches[0]!r}")  # 打印选择结果
    return resolved  # 返回映射


def to_numeric_clean(series: pd.Series) -> pd.Series:  # 定义数值清洗函数
    """去掉空白、BOM、千分位逗号后转数值，无法转换的变 NaN。"""  # 函数说明
    text = series.astype("string").str.strip()  # 转字符串并去掉首尾空格
    text = text.str.replace("\ufeff", "", regex=False)  # 去掉 BOM
    text = text.str.replace("\u00a0", "", regex=False)  # 去掉不换行空格
    text = text.str.replace(",", "", regex=False)  # 去掉千分位逗号
    return pd.to_numeric(text, errors="coerce")  # 转数值，失败变 NaN


def drop_and_report(data: pd.DataFrame, mask: pd.Series, label: str) -> pd.DataFrame:  # 定义删除并报告函数
    """删除 mask 为真的行，并打印行数变化。"""  # 函数说明
    before = len(data)  # 记录删除前行数
    data = data.loc[~mask].copy()  # 保留 mask 为假的行
    removed = before - len(data)  # 计算删除行数
    print(f"{label}：删除前 {before} 行，删除 {removed} 行，剩余 {len(data)} 行")  # 打印行数变化
    return data  # 返回删除后的数据


def describe_columns(data: pd.DataFrame, columns: list) -> pd.DataFrame:  # 定义描述统计函数
    """返回指定列的均值、标准差、最小值、最大值（变量为行）。"""  # 函数说明
    stats = data[columns].agg(["mean", "std", "min", "max"])  # 计算四项统计量
    return stats.T  # 转置后变量为行，便于打印


def make_tertiles(data: pd.DataFrame, value_col: str, group_col: str | None = None) -> pd.Series:  # 定义三分位分组函数
    """按排名做三分位分组，避免重复值导致 qcut 失败。"""  # 函数说明
    if group_col is None:  # 如果不需要组内分组
        rank = data[value_col].rank(method="first")  # 全样本按大小排名
        size = len(data)  # 全样本量
    else:  # 如果需要在每个组内部分组
        rank = data.groupby(group_col)[value_col].rank(method="first")  # 组内按大小排名
        size = data.groupby(group_col)[value_col].transform("size")  # 组内样本量
    fraction = rank / size  # 计算排名比例（0~1）
    return pd.cut(  # 按比例切三段
        fraction,  # 传入排名比例
        bins=[0.0, 1 / 3, 2 / 3, 1.0],  # 三段边界
        labels=GROUP_LABELS,  # 分组标签
        include_lowest=True,  # 包含最左边界
    )  # 结束 pd.cut


def winsorize_by_group(  # 定义分组缩尾函数
    data: pd.DataFrame,  # 输入数据
    value_col: str,  # 待缩尾列
    group_col: str,  # 分组列（船型）
    out_col: str,  # 缩尾结果列
    lower_q: float,  # 下分位点
    upper_q: float,  # 上分位点
) -> tuple[pd.DataFrame, pd.DataFrame]:  # 返回数据和阈值表
    """在每个组内独立做 1%/99% 缩尾，并返回各组阈值。"""  # 函数说明
    data = data.copy()  # 复制数据，避免修改原对象
    data[out_col] = data[value_col].astype(float)  # 先复制原始列作为缩尾列
    records = []  # 保存各组阈值记录
    for group_value, group in data.groupby(group_col, observed=True):  # 逐组处理
        lower = float(group[value_col].quantile(lower_q))  # 计算组内下分位点
        upper = float(group[value_col].quantile(upper_q))  # 计算组内上分位点
        mask = data[group_col] == group_value  # 定位当前组的行
        data.loc[mask, out_col] = group[value_col].clip(lower=lower, upper=upper)  # 组内缩尾
        clipped = int(((group[value_col] < lower) | (group[value_col] > upper)).sum())  # 统计被裁剪条数
        records.append(  # 记录当前组信息
            {  # 开始字典
                "ship_type": group_value,  # 船型
                "lower_1pct": round(lower, 4),  # 下分位点
                "upper_99pct": round(upper, 4),  # 上分位点
                "clipped_rows": clipped,  # 被裁剪条数
                "max_before": round(float(group[value_col].max()), 4),  # 缩尾前最大值
                "max_after": round(upper, 4),  # 缩尾后最大值
            }  # 结束字典
        )  # 结束记录
    thresholds = pd.DataFrame(records)  # 转成表
    return data, thresholds  # 返回缩尾后数据和阈值表


def build_group_stats(data: pd.DataFrame, group_cols: list, value_cols: list) -> pd.DataFrame:  # 定义分组统计函数
    """生成分组 × 变量的长表统计（count/mean/std/min/max）。"""  # 函数说明
    records = []  # 保存统计记录
    for keys, group in data.groupby(group_cols, observed=True, sort=False):  # 遍历每个分组
        if not isinstance(keys, tuple):  # 如果只有一个分组键
            keys = (keys,)  # 包装成元组
        group_name = " / ".join(str(key) for key in keys)  # 拼接分组名称
        for col in value_cols:  # 遍历每个变量
            series = group[col]  # 取出当前变量
            records.append(  # 记录统计结果
                {  # 开始字典
                    "group": group_name,  # 分组名称
                    "variable": col,  # 变量名
                    "count": int(series.count()),  # 有效样本量
                    "mean": float(series.mean()),  # 均值
                    "std": float(series.std()),  # 标准差
                    "min": float(series.min()),  # 最小值
                    "max": float(series.max()),  # 最大值
                }  # 结束字典
            )  # 结束记录
    stats = pd.DataFrame(records)  # 转成 DataFrame
    numeric_cols = ["count", "mean", "std", "min", "max"]  # 需要保留小数的列
    stats[numeric_cols] = stats[numeric_cols].round(4)  # 统一保留 4 位小数
    return stats  # 返回统计表


# ==================== 主流程 ====================  # 主流程区
def main() -> None:  # 定义主函数
    """执行从读取 Excel 到保存 CSV 的完整清洗流程。"""  # 函数说明
    if hasattr(sys.stdout, "reconfigure"):  # 如果标准输出支持重配置
        sys.stdout.reconfigure(encoding="utf-8")  # 设置 UTF-8 输出，避免中文乱码
    print(f"Python 解释器：{sys.executable}")  # 打印解释器路径，确认使用 shipping 环境
    print(f"输入文件：{INPUT_FILE}")  # 打印输入文件路径
    print(f"输出文件：{OUTPUT_FILE}")  # 打印输出文件路径

    print_section("第1步：读取 Excel")  # 打印第 1 步标题
    if not INPUT_FILE.exists():  # 如果输入文件不存在
        raise FileNotFoundError(f"输入文件不存在：{INPUT_FILE}")  # 抛出明确异常
    raw = pd.read_excel(INPUT_FILE, sheet_name=SHEET_NAME, header=HEADER_ROW)  # 读取指定工作表
    print(f"原始总行数：{len(raw)} 行")  # 打印原始总行数
    print(f"原始总列数：{len(raw.columns)} 列")  # 打印原始总列数
    resolved = resolve_columns(list(raw.columns))  # 模糊匹配关键列
    df = pd.DataFrame({key: raw[original] for key, original in resolved.items()})  # 只保留关键列
    print(f"提取关键列后形状：{df.shape}")  # 打印形状

    print_section("第2步：筛选三种目标船型")  # 打印第 2 步标题
    df["ship_type"] = df["ship_type"].astype("string").str.replace("\u00a0", " ", regex=False).str.strip()  # 清洗船型文本
    print("原始数据 Ship type 分布：")  # 打印提示
    ship_type_counts = raw[resolved["ship_type"]].astype("string").str.strip().value_counts(dropna=False)  # 统计原始船型分布
    print(ship_type_counts.to_string())  # 打印全部船型分布
    before = len(df)  # 记录筛选前行数
    target_keys = [ship_type.casefold() for ship_type in TARGET_SHIP_TYPES]  # 生成目标船型小写集合
    df = df.loc[df["ship_type"].str.casefold().isin(target_keys)].copy()  # 只保留三种目标船型
    print(f"筛选三种目标船型：筛选前 {before} 行，删除 {before - len(df)} 行，剩余 {len(df)} 行")  # 打印行数变化
    print("各船型保留行数：")  # 打印提示
    for ship_type in TARGET_SHIP_TYPES:  # 遍历三种目标船型
        count = int((df["ship_type"].str.casefold() == ship_type.casefold()).sum())  # 统计当前船型行数
        print(f"  {ship_type}: {count} 行")  # 打印当前船型行数
        if count == 0:  # 如果当前船型为空
            raise SystemExit(f"船型 {ship_type} 筛选后为 0 行，请检查 Ship type 取值")  # 终止并提示

    print_section("第3步：筛选 Technical efficiency 含 EEXI")  # 打印第 3 步标题
    tech_text = df["tech_eff"].astype("string").fillna("").str.replace("\ufeff", "", regex=False).str.strip()  # 清洗能效文本
    label_counts = tech_text.str.extract(r"^\s*([A-Za-z]+)", expand=False).value_counts(dropna=False)  # 统计能效标识
    print("筛选前能效标识分布：")  # 打印提示
    print(label_counts.to_string())  # 打印能效标识分布
    before = len(df)  # 记录筛选前行数
    contain_eexi = tech_text.str.contains(TARGET_EFFICIENCY, case=False, na=False, regex=False)  # 构造含 EEXI 掩码
    df = df.loc[contain_eexi].copy()  # 只保留含 EEXI 的行
    print(f"筛选含 {TARGET_EFFICIENCY}：筛选前 {before} 行，删除 {before - len(df)} 行，剩余 {len(df)} 行")  # 打印行数变化
    print("各船型含 EEXI 行数：")  # 打印提示
    for ship_type in TARGET_SHIP_TYPES:  # 遍历三种目标船型
        count = int((df["ship_type"].str.casefold() == ship_type.casefold()).sum())  # 统计当前船型行数
        print(f"  {ship_type}: {count} 行")  # 打印当前船型行数
    print(f"含 EEXI 的总样本量：{len(df)} 艘")  # 打印有 EEXI 的总样本量

    print_section("第4步：提取碳强度与总 CO2 并删除空值/非正值")  # 打印第 4 步标题
    df["co2_intensity"] = to_numeric_clean(df["co2_intensity"])  # 碳强度转数值
    print(f"co2_intensity 非空 {int(df['co2_intensity'].notna().sum())} 条，空值 {int(df['co2_intensity'].isna().sum())} 条")  # 打印非空与空值
    print(f"co2_intensity <= 0 的条数：{int(df['co2_intensity'].le(0).sum())}")  # 打印非正条数
    invalid_intensity = df["co2_intensity"].isna() | df["co2_intensity"].le(0)  # 构造无效掩码
    df = drop_and_report(df, invalid_intensity, "删除 co2_intensity 为空或<=0")  # 删除无效行
    df["total_co2"] = to_numeric_clean(df["total_co2"])  # 总 CO2 转数值
    print(f"total_co2 非空 {int(df['total_co2'].notna().sum())} 条，空值 {int(df['total_co2'].isna().sum())} 条")  # 打印非空与空值
    print(f"total_co2 <= 0 的条数：{int(df['total_co2'].le(0).sum())}")  # 打印非正条数
    invalid_total = df["total_co2"].isna() | df["total_co2"].le(0)  # 构造无效掩码
    df = drop_and_report(df, invalid_total, "删除 total_co2 为空或<=0")  # 删除无效行
    if len(df) < 3:  # 如果样本量不足
        raise SystemExit("有效样本少于 3 条，无法做三分位分组")  # 终止并提示

    print_section("第5步：正则提取 EEXI 数值并删除空值/非正值")  # 打印第 5 步标题
    extracted = df["tech_eff"].astype("string").fillna("").str.extract(EEXI_REGEX, expand=False)  # 用正则提取括号内数字
    df["eexi_value"] = pd.to_numeric(extracted, errors="coerce")  # 转成数值，失败变 NaN
    valid = int(df["eexi_value"].notna().sum())  # 统计解析成功条数
    failed = int(df["eexi_value"].isna().sum())  # 统计解析失败条数
    print(f"eexi_value 解析成功 {valid} 条，失败 {failed} 条")  # 打印解析结果
    if failed > 0:  # 如果存在解析失败
        print("未能提取的样例：")  # 打印提示
        print(df.loc[df["eexi_value"].isna(), "tech_eff"].astype(str).head(PREVIEW_ROWS).tolist())  # 打印失败样例
    df = drop_and_report(df, df["eexi_value"].isna(), "删除 eexi_value 为空")  # 删除 EEXI 空值
    invalid_eexi = df["eexi_value"].le(MIN_EEXI_VALUE)  # 构造非正 EEXI 掩码
    print(f"eexi_value <= {MIN_EEXI_VALUE} 的条数：{int(invalid_eexi.sum())}")  # 打印非正 EEXI 条数
    if invalid_eexi.any():  # 如果存在非正 EEXI
        print("被删除的 EEXI 异常记录：")  # 打印提示
        bad_columns = ["imo", "ship_name", "ship_type", "tech_eff", "eexi_value"]  # 需要展示的列
        print(df.loc[invalid_eexi, bad_columns].to_string(index=False))  # 打印异常记录明细
    df = drop_and_report(df, invalid_eexi, "删除 eexi_value<=0 的异常记录")  # 删除异常行

    print_section("第6步：按船型做 1%/99% 缩尾")  # 打印第 6 步标题
    before_max = float(df["co2_intensity"].max())  # 记录缩尾前的整体最大值
    df, thresholds = winsorize_by_group(  # 调用分组缩尾函数
        df,  # 输入数据
        "co2_intensity",  # 待缩尾列
        "ship_type",  # 按船型分组
        "co2_intensity_winsor",  # 输出列
        WINSOR_LOWER_Q,  # 下分位点
        WINSOR_UPPER_Q,  # 上分位点
    )  # 结束调用
    print("各船型缩尾阈值：")  # 打印提示
    print(thresholds.to_string(index=False))  # 打印阈值表
    print(f"缩尾前 co2_intensity 最大值：{before_max:.4f}")  # 打印缩尾前整体最大值
    after_max = float(df["co2_intensity_winsor"].max())  # 取缩尾后的整体最大值
    print(f"缩尾后 co2_intensity_winsor 最大值：{after_max:.4f}")  # 打印缩尾后整体最大值
    print(f"缩尾后有效样本量：{len(df)} 艘")  # 打印样本量

    print_section("第7步：按 total_co2 全样本三分位生成 size_group")  # 打印第 7 步标题
    df[SIZE_GROUP_COL] = make_tertiles(df, "total_co2").astype("string")  # 生成全样本三分位分组
    print("size_group 三组数量：")  # 打印提示
    size_counts = df[SIZE_GROUP_COL].value_counts().reindex(GROUP_LABELS)  # 按固定顺序统计三组数量
    print(size_counts.to_string())  # 打印三组数量
    print("size_group 三组 total_co2 范围：")  # 打印提示
    size_range = df.groupby(SIZE_GROUP_COL, observed=True)["total_co2"].agg(["count", "min", "max"])  # 计算组内范围
    print(size_range.reindex(GROUP_LABELS).to_string())  # 打印组内范围

    print_section("第8步：按船型内 total_co2 三分位生成 size_group_within_type")  # 打印第 8 步标题
    within_group = make_tertiles(df, "total_co2", group_col="ship_type")  # 生成船型内三分位
    df[SIZE_GROUP_WITHIN_COL] = within_group.astype("string")  # 写入新列
    print("ship_type × size_group_within_type 交叉表：")  # 打印提示
    within_table = pd.crosstab(df["ship_type"], df[SIZE_GROUP_WITHIN_COL])  # 生成交叉表
    within_table = within_table.reindex(columns=GROUP_LABELS, fill_value=0)  # 固定列顺序
    print(within_table.to_string())  # 打印交叉表
    print("各组 total_co2 范围：")  # 打印提示
    within_range = df.groupby(["ship_type", SIZE_GROUP_WITHIN_COL], observed=True)["total_co2"].agg(["count", "min", "max"])  # 计算组内范围
    print(within_range.to_string())  # 打印组内范围

    print_section("第9步：生成 ship_type_group、校验年度并重置索引")  # 打印第 9 步标题
    df["ship_type_group"] = df["ship_type"]  # 保留英文原始船型名
    df["report_year"] = pd.to_numeric(df["report_year"], errors="coerce").astype("Int64")  # 年度转可空整数
    print("报告年度分布：")  # 打印提示
    print(df["report_year"].value_counts(dropna=False).sort_index().to_string())  # 打印年度分布
    year_values = set(df["report_year"].dropna().astype(int).tolist())  # 取出实际出现的年度
    if year_values != {TARGET_YEAR}:  # 如果存在非目标年度
        print(f"[警告] 存在非 {TARGET_YEAR} 年记录，请检查数据")  # 打印警告
    output = df[OUTPUT_COLUMNS].copy()  # 只保留最终输出列
    output["imo"] = pd.to_numeric(output["imo"], errors="coerce").astype("Int64")  # IMO 转可空整数
    output["ship_name"] = output["ship_name"].astype("string").str.strip()  # 船名转字符串并去空格
    output = output.reset_index(drop=True)  # 重置索引
    print(f"最终样本量：{len(output)} 艘")  # 打印最终样本量
    print("输出列缺失值统计：")  # 打印提示
    print(output.isna().sum().to_string())  # 打印每列缺失值
    print(f"重复 IMO 行数（仅诊断，不删除）：{int(output['imo'].duplicated().sum())}")  # 打印重复 IMO 行数
    print("输出前 5 行：")  # 打印提示
    print(output.head(PREVIEW_ROWS).to_string(index=False))  # 打印前几行

    print_section("第10步：保存 CSV 并打印最终统计")  # 打印第 10 步标题
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)  # 创建输出目录（不存在时）
    output.to_csv(OUTPUT_FILE, index=False, encoding=OUTPUT_ENCODING)  # 保存 CSV
    file_size_kb = OUTPUT_FILE.stat().st_size / 1024  # 计算文件大小（KB）
    print(f"已保存：{OUTPUT_FILE}")  # 打印保存路径
    print(f"文件行数：{len(output)}，文件大小：{file_size_kb:.2f} KB")  # 打印行数和文件大小
    print("三个变量的均值、标准差、最小值、最大值：")  # 打印提示
    overall_stats = describe_columns(output, VALUE_COLUMNS)  # 计算整体统计
    print(overall_stats.round(4).to_string())  # 打印整体统计
    print("分船型三个变量统计：")  # 打印提示
    type_stats = build_group_stats(output, ["ship_type"], VALUE_COLUMNS)  # 计算分船型统计
    type_order = {name: index for index, name in enumerate(TARGET_SHIP_TYPES)}  # 船型排序映射
    type_stats["type_order"] = type_stats["group"].map(type_order)  # 加入船型顺序列
    type_stats = type_stats.sort_values(["type_order", "variable"])  # 按船型和变量排序
    type_stats = type_stats.drop(columns="type_order")  # 删除辅助排序列
    print(type_stats.to_string(index=False))  # 打印分船型统计
    print("船型 × 船型内大小组的三个变量对比表：")  # 打印提示
    cell_stats = build_group_stats(output, ["ship_type", SIZE_GROUP_WITHIN_COL], VALUE_COLUMNS)  # 计算 9 组统计
    cell_stats["type_order"] = cell_stats["group"].str.split(" / ").str[0].map(type_order)  # 加入船型顺序
    size_order = {name: index for index, name in enumerate(GROUP_LABELS)}  # 大小组排序映射
    cell_stats["size_order"] = cell_stats["group"].str.split(" / ").str[1].map(size_order)  # 加入大小组顺序
    cell_stats = cell_stats.sort_values(["type_order", "size_order", "variable"])  # 按船型、大小组、变量排序
    cell_stats = cell_stats.drop(columns=["type_order", "size_order"])  # 删除辅助排序列
    print(cell_stats.to_string(index=False))  # 打印 9 组统计
    print("船型 × 全样本 size_group 交叉表：")  # 打印提示
    final_table = pd.crosstab(output["ship_type"], output[SIZE_GROUP_COL])  # 生成最终交叉表
    final_table = final_table.reindex(columns=GROUP_LABELS, fill_value=0)  # 固定列顺序
    print(final_table.to_string())  # 打印最终交叉表
    print("\n清洗完成。")  # 打印完成提示


if __name__ == "__main__":  # 判断是否作为主程序运行
    main()  # 调用主函数
