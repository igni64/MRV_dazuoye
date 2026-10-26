# -*- coding: utf-8 -*-  # 指定脚本编码为 UTF-8
"""  # 开始模块说明
01_clean.py：清洗 2023 年 THETIS-MRV 集装箱船数据。  # 脚本用途
  # 空注释行
输入：  # 输入说明
    data/raw/thrtis_mrv_2023.xlsx 的 2023 工作表  # 2023 年原始数据
  # 空注释行
输出：  # 输出说明
    data/clean/container_clean.csv  # 清洗后的分析数据
  # 空注释行
运行方式：  # 运行说明
    python analysis/01_clean.py  # 在项目根目录运行
"""  # 结束模块说明

import re  # 导入正则表达式模块，用于列名匹配和 EEXI 提取
import sys  # 导入系统模块，用于设置标准输出编码
from pathlib import Path  # 导入路径模块，用于处理项目相对路径
import pandas as pd  # 导入 pandas，用于读取 Excel 和清洗数据

# ============================== 参数区 ==============================  # 参数集中区
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 根据脚本位置推导项目根目录
INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "thrtis_mrv_2023.xlsx"  # 输入 Excel 文件
SHEET_NAME = "2023"  # 输入工作表名称
HEADER_ROW = 2  # 表头行号，0 基，对应 Excel 第 3 行
OUTPUT_FILE = PROJECT_ROOT / "data" / "clean" / "container_clean.csv"  # 输出 CSV 路径
TARGET_SHIP_TYPE = "Container ship"  # 目标船舶类型
TARGET_YEAR = 2023  # 目标报告年度
TARGET_EFFICIENCY = "EEXI"  # 目标能效指标
EEXI_REGEX = r"EEXI\s*\(([\d.]+)"  # EEXI 数值提取正则
WINSOR_LOWER_Q = 0.01  # 缩尾下分位点
WINSOR_UPPER_Q = 0.99  # 缩尾上分位点
GROUP_LABELS = ["小船组", "中船组", "大船组"]  # 三分位分组标签
OUTPUT_COLUMNS = [  # 最终输出列
    "imo",  # IMO 编号
    "ship_name",  # 船名
    "report_year",  # 报告年度
    "co2_intensity",  # 缩尾后的碳强度
    "total_co2",  # 总 CO2 排放
    "eexi_value",  # EEXI 数值
    "size_group",  # 分组标签
]  # 结束输出列
OUTPUT_ENCODING = "utf-8-sig"  # CSV 编码，兼容 Windows Excel
PREVIEW_ROWS = 10  # 诊断样例条数
COLUMN_RULES = {  # 关键列模糊匹配规则
    "imo": {"mode": "startswith", "keywords": ["imo number"], "exclude": []},  # IMO 列
    "ship_name": {"mode": "exact", "keywords": ["name"], "exclude": []},  # 船名列
    "ship_type": {"mode": "startswith", "keywords": ["ship type"], "exclude": []},  # 船型列
    "report_year": {"mode": "startswith", "keywords": ["reporting period"], "exclude": []},  # 年份列
    "tech_eff": {"mode": "startswith", "keywords": ["technical efficiency"], "exclude": []},  # 技术能效列
    "co2_intensity": {  # 碳强度列
        "mode": "startswith",  # 使用前缀匹配
        "keywords": ["annual average co2 emissions per transport work (mass)"],  # 英文关键词
        "exclude": ["on laden"],  # 排除载货航次专用列
    },  # 结束碳强度规则
    "total_co2": {"mode": "startswith", "keywords": ["total co2 emissions"], "exclude": []},  # 总 CO2 列
}  # 结束列匹配规则

# ============================== 工具函数 ==============================  # 工具函数区
def print_section(title: str) -> None:  # 定义打印分节标题的函数
    """打印统一格式的分节标题。"""  # 函数说明
    print("\n" + "=" * 80)  # 打印上分隔线
    print(title)  # 打印标题
    print("=" * 80)  # 打印下分隔线


def normalize_column_name(name: object) -> str:  # 定义列名归一化函数
    """统一 CO2 下标、空白和大小写，便于模糊匹配。"""  # 函数说明
    text = str(name)  # 把列名转成字符串
    text = text.replace("₂", "2")  # 把 Unicode 下标 2 转成普通 2
    text = text.replace("CO₂", "CO2")  # 把 CO₂ 转成 CO2
    text = text.replace("co₂", "co2")  # 把 co₂ 转成 co2
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
    """模糊匹配关键列，打印候选列并返回原始列名映射。"""  # 函数说明
    resolved = {}  # 保存 key 到原始列名的映射
    print("关键列匹配结果：")  # 打印提示
    for key, rule in COLUMN_RULES.items():  # 遍历每个关键列规则
        matches = [col for col in columns if match_column(col, rule)]  # 找出全部命中列
        print(f"  {key}: {matches!r}")  # 打印候选列
        if not matches:  # 如果一个都没命中
            print(f"[错误] 找不到关键列 {key!r}，规则：{rule}")  # 打印错误信息
            print("全部列名如下：")  # 打印提示
            for index, column in enumerate(columns):  # 遍历全部列
                print(f"    {index}: {column!r}")  # 打印列位置和列名
            raise ValueError(f"找不到关键列：{key}")  # 抛出异常停止执行
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
    """返回指定列的均值、标准差、最小值、最大值。"""  # 函数说明
    return data[columns].describe().loc[["mean", "std", "min", "max"]]  # 计算并返回四项统计


def main() -> None:  # 定义主函数
    """执行从读取 Excel 到保存 CSV 的完整清洗流程。"""  # 函数说明
    if hasattr(sys.stdout, "reconfigure"):  # 如果标准输出支持重配置
        sys.stdout.reconfigure(encoding="utf-8")  # 设置 UTF-8 输出，减少中文乱码
    print(f"Python 解释器：{sys.executable}")  # 打印解释器路径
    print(f"输入文件：{INPUT_FILE}")  # 打印输入路径
    print(f"输出文件：{OUTPUT_FILE}")  # 打印输出路径

    print_section("第1步：读取 Excel")  # 打印第 1 步标题
    if not INPUT_FILE.exists():  # 如果输入文件不存在
        raise FileNotFoundError(f"输入文件不存在：{INPUT_FILE}")  # 抛出明确异常
    raw = pd.read_excel(INPUT_FILE, sheet_name=SHEET_NAME, header=HEADER_ROW)  # 读取指定工作表
    print(f"原始数据形状：{raw.shape}")  # 打印原始行列数
    print(f"HEADER_ROW={HEADER_ROW}，对应 Excel 第 {HEADER_ROW + 1} 行")  # 打印表头行说明
    columns = list(raw.columns)  # 取出全部原始列名
    resolved = resolve_columns(columns)  # 模糊匹配关键列
    df = pd.DataFrame({key: raw[original] for key, original in resolved.items()})  # 只保留关键列并改成内部列名
    print(f"关键列映射：{resolved}")  # 打印映射结果
    print(f"工作数据形状：{df.shape}")  # 打印工作数据形状

    print_section("第2步：筛选集装箱船")  # 打印第 2 步标题
    ship_type = df["ship_type"].astype("string").str.replace("\u00a0", " ", regex=False).str.strip().str.casefold()  # 清洗船型文本
    before = len(df)  # 记录筛选前行数
    df = df.loc[ship_type == TARGET_SHIP_TYPE.casefold()].copy()  # 只保留集装箱船
    print(f"筛选 {TARGET_SHIP_TYPE!r}：筛选前 {before} 行，筛选后 {len(df)} 行，删除 {before - len(df)} 行")  # 打印行数变化
    if len(df) == 0:  # 如果筛选后为空
        raise ValueError(f"筛选 {TARGET_SHIP_TYPE!r} 后为 0 行，请检查 Ship type 取值")  # 抛出异常
    print("Ship type 取值分布（前 10）：")  # 打印提示
    print(raw[resolved["ship_type"]].astype("string").str.strip().value_counts().head(PREVIEW_ROWS).to_string())  # 打印船型分布

    print_section("第3步：筛选 EEXI")  # 打印第 3 步标题
    tech_text = df["tech_eff"].astype("string").fillna("").str.replace("\ufeff", "", regex=False).str.strip()  # 清洗技术能效文本
    type_counts = tech_text.str.extract(r"^\s*([A-Za-z]+)", expand=False).value_counts(dropna=False)  # 统计能效类型前缀
    print("筛选前 Technical efficiency 类型分布：")  # 打印提示
    print(type_counts.to_string())  # 打印类型分布
    before = len(df)  # 记录筛选前行数
    df = df.loc[tech_text.str.contains(TARGET_EFFICIENCY, case=False, na=False, regex=False)].copy()  # 只保留包含 EEXI 的行
    print(f"筛选包含 {TARGET_EFFICIENCY!r}：筛选前 {before} 行，筛选后 {len(df)} 行，删除 {before - len(df)} 行")  # 打印行数变化
    if len(df) == 0:  # 如果筛选后为空
        raise ValueError(f"筛选 {TARGET_EFFICIENCY!r} 后为 0 行，请检查 Technical efficiency 取值")  # 抛出异常

    print_section("第4步：提取碳强度并筛选非空")  # 打印第 4 步标题
    df["co2_intensity"] = to_numeric_clean(df["co2_intensity"])  # 把碳强度转成数值
    valid = int(df["co2_intensity"].notna().sum())  # 统计非空条数
    null = int(df["co2_intensity"].isna().sum())  # 统计空值条数
    print(f"co2_intensity 非空 {valid} 条，空值 {null} 条")  # 打印非空和空值数量
    print(f"co2_intensity <= 0 的条数：{int((df['co2_intensity'] <= 0).sum())}")  # 打印非正条数
    df = drop_and_report(df, df["co2_intensity"].isna(), "删除 co2_intensity 为空")  # 删除碳强度空值

    print_section("第5步：提取总 CO2 并筛选非空")  # 打印第 5 步标题
    df["total_co2"] = to_numeric_clean(df["total_co2"])  # 把总 CO2 转成数值
    valid = int(df["total_co2"].notna().sum())  # 统计非空条数
    null = int(df["total_co2"].isna().sum())  # 统计空值条数
    print(f"total_co2 非空 {valid} 条，空值 {null} 条")  # 打印非空和空值数量
    print(f"total_co2 <= 0 的条数：{int((df['total_co2'] <= 0).sum())}")  # 打印非正条数
    df = drop_and_report(df, df["total_co2"].isna(), "删除 total_co2 为空")  # 删除总 CO2 空值

    print_section("第6步：提取 EEXI 数值并剔除非正行")  # 打印第 6 步标题
    extracted = df["tech_eff"].astype("string").fillna("").str.replace("\ufeff", "", regex=False).str.strip().str.extract(EEXI_REGEX, expand=False)  # 用正则提取 EEXI 数值
    df["eexi_value"] = pd.to_numeric(extracted, errors="coerce")  # 转成数值，失败变 NaN
    valid = int(df["eexi_value"].notna().sum())  # 统计有效条数
    fail = int(df["eexi_value"].isna().sum())  # 统计失败条数
    print(f"eexi_value 有效 {valid} 条，失败 {fail} 条")  # 打印提取结果
    if fail > 0:  # 如果存在失败
        print("未能提取的样例：")  # 打印提示
        print(df.loc[df["eexi_value"].isna(), "tech_eff"].astype(str).head(PREVIEW_ROWS).tolist())  # 打印失败样例
    df = drop_and_report(df, df["eexi_value"].isna(), "删除 eexi_value 为空")  # 删除 EEXI 空值
    print(f"co2_intensity <= 0 的条数：{int((df['co2_intensity'] <= 0).sum())}")  # 再次打印非正碳强度
    print(f"total_co2 <= 0 的条数：{int((df['total_co2'] <= 0).sum())}")  # 再次打印非正总 CO2
    invalid_mask = (df["co2_intensity"] <= 0) | (df["total_co2"] <= 0)  # 构造非正行掩码
    df = drop_and_report(df, invalid_mask, "删除 co2_intensity<=0 或 total_co2<=0")  # 删除非正行
    if len(df) < 3:  # 如果样本量不足
        raise ValueError("有效样本少于 3 条，无法做三分位分组")  # 抛出异常

    print_section("第7步：1%/99% 缩尾并按 total_co2 三分位分组")  # 打印第 7 步标题
    raw_ci = df["co2_intensity"].copy()  # 保存缩尾前碳强度
    q_low = float(raw_ci.quantile(WINSOR_LOWER_Q))  # 计算 1% 分位点
    q_high = float(raw_ci.quantile(WINSOR_UPPER_Q))  # 计算 99% 分位点
    print(f"缩尾分位点：{WINSOR_LOWER_Q:.0%}={q_low:.4f}，{WINSOR_UPPER_Q:.0%}={q_high:.4f}")  # 打印分位点
    raw_desc = raw_ci.describe().loc[["count", "mean", "std", "min", "max"]]  # 计算缩尾前统计
    print("缩尾前 co2_intensity 统计：")  # 打印提示
    print(raw_desc.to_string())  # 打印缩尾前统计
    df["co2_intensity"] = raw_ci.clip(lower=q_low, upper=q_high)  # 按分位点缩尾
    win_desc = df["co2_intensity"].describe().loc[["count", "mean", "std", "min", "max"]]  # 计算缩尾后统计
    print("缩尾后 co2_intensity 统计：")  # 打印提示
    print(win_desc.to_string())  # 打印缩尾后统计
    try:  # 尝试直接按总 CO2 做三分位
        df["size_group"] = pd.qcut(df["total_co2"], q=3, labels=GROUP_LABELS)  # 生成三分位分组
    except ValueError as exc:  # 如果分位点重复导致失败
        print(f"[提示] 直接三分位失败：{exc}，改用排名后三分位")  # 打印回退提示
        ranked = df["total_co2"].rank(method="first")  # 先按大小排名，消除重复分位点
        df["size_group"] = pd.qcut(ranked, q=3, labels=GROUP_LABELS)  # 按排名做三分位
    df["size_group"] = df["size_group"].astype("string")  # 转成字符串，便于输出
    print("各分组数量：")  # 打印提示
    print(df["size_group"].value_counts().reindex(GROUP_LABELS).to_string())  # 打印三组数量
    print("各分组 total_co2 范围：")  # 打印提示
    group_range = df.groupby("size_group", observed=True)["total_co2"].agg(["count", "min", "max"]).reindex(GROUP_LABELS)  # 计算组内范围
    print(group_range.to_string())  # 打印组内范围

    print_section("第8步：重置索引并整理输出列")  # 打印第 8 步标题
    output = df[OUTPUT_COLUMNS].copy()  # 只保留最终输出列
    output["imo"] = pd.to_numeric(output["imo"], errors="coerce").astype("Int64")  # IMO 转可空整数
    output["report_year"] = pd.to_numeric(output["report_year"], errors="coerce").astype("Int64")  # 年份转可空整数
    output["ship_name"] = output["ship_name"].astype("string").str.strip()  # 船名转字符串并去空格
    output["size_group"] = output["size_group"].astype("string")  # 分组列转字符串
    output = output.reset_index(drop=True)  # 重置索引
    print(f"输出数据形状：{output.shape}")  # 打印输出形状
    print("输出列缺失值统计：")  # 打印提示
    print(output.isna().sum().to_string())  # 打印每列缺失值
    print("报告年度分布：")  # 打印提示
    print(output["report_year"].value_counts(dropna=False).sort_index().to_string())  # 打印年度分布
    print(f"重复 IMO 行数（仅诊断，不删除）：{int(output['imo'].duplicated().sum())}")  # 打印重复 IMO 数量
    if not (output["report_year"] == TARGET_YEAR).all():  # 如果存在非目标年份
        print(f"[警告] 存在非 {TARGET_YEAR} 年记录，请检查数据")  # 打印警告
    print("输出前 5 行：")  # 打印提示
    print(output.head(5).to_string(index=False))  # 打印前 5 行

    print_section("第9步：保存 CSV 并打印最终统计")  # 打印第 9 步标题
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)  # 创建输出目录
    output.to_csv(OUTPUT_FILE, index=False, encoding=OUTPUT_ENCODING)  # 保存 CSV
    file_size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024  # 计算文件大小
    print(f"已保存：{OUTPUT_FILE}")  # 打印保存路径
    print(f"文件行数：{len(output)}，文件大小：{file_size_mb:.2f} MB")  # 打印行数和大小
    print(f"最终样本量：{len(output)}")  # 打印最终样本量
    print("各分组数量：")  # 打印提示
    print(output["size_group"].value_counts().reindex(GROUP_LABELS).to_string())  # 打印分组数量
    print("三个变量的均值、标准差、最小值、最大值：")  # 打印提示
    final_desc = describe_columns(output, ["co2_intensity", "total_co2", "eexi_value"])  # 计算最终统计
    print(final_desc.to_string())  # 打印最终统计
    print("各分组三个变量均值：")  # 打印提示
    group_means = output.groupby("size_group", observed=True)[["co2_intensity", "total_co2", "eexi_value"]].mean().reindex(GROUP_LABELS)  # 计算组均值
    print(group_means.to_string())  # 打印组均值
    print("\n清洗完成。")  # 打印完成提示


if __name__ == "__main__":  # 判断是否作为主程序运行
    main()  # 调用主函数
