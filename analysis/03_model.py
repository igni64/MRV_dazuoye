# -*- coding: utf-8 -*-  # 指定脚本编码为 UTF-8
"""
03_model.py：EEXI 对碳强度解释力的回归分析（M0-M4 + 异质性 + 稳健性）。

输入：
    data/clean/ships_clean.csv
输出：
    tables/model_results.csv
    tables/shapley_decomposition.csv

运行方式：
    conda activate shipping
    python analysis/03_model.py
"""

import sys  # 导入系统模块，用于设置标准输出编码
import warnings  # 导入警告模块，用于屏蔽已知的数值警告
from pathlib import Path  # 导入路径模块，用于拼接项目相对路径
import numpy as np  # 导入 numpy，用于数值计算
import pandas as pd  # 导入 pandas，用于数据处理

try:  # 尝试导入 statsmodels 公式接口
    import statsmodels.formula.api as smf  # 导入 OLS 公式接口
    HAS_STATSMODELS = True  # 标记 statsmodels 可用
except ImportError:  # 如果未安装 statsmodels
    HAS_STATSMODELS = False  # 标记 statsmodels 不可用

# ==================== 参数区（集中配置） ====================  # 参数区标题
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 由脚本位置推导项目根目录
INPUT_FILE = PROJECT_ROOT / "data" / "clean" / "ships_clean.csv"  # 输入清洗后数据
OUTPUT_FILE = PROJECT_ROOT / "tables" / "model_results.csv"  # 模型结果汇总表
SHAPLEY_FILE = PROJECT_ROOT / "tables" / "shapley_decomposition.csv"  # Shapley 分解表
DEPENDENT = "co2_intensity_winsor"  # 因变量：缩尾后碳强度
RAW_DEPENDENT = "co2_intensity"  # 原始碳强度（稳健性检验用）
CORE_X = "eexi_value"  # 核心自变量：EEXI
SIZE_CONTROL = "total_co2"  # 规模控制变量：总 CO2 排放
TYPE_COL = "ship_type"  # 船型分类变量
SIZE_GROUP = "size_group"  # 全样本三分位分组
WITHIN_GROUP = "size_group_within_type"  # 船型内三分位分组
REFERENCE_TYPE = "Container ship"  # 船型虚拟变量的参照组
ALL_TYPES = ["Container ship", "Bulk carrier", "Oil tanker"]  # 三种目标船型
GROUP_LABELS = ["Small", "Medium", "Large"]  # 三分位标签
COOK_MULT = 4  # Cook's D 阈值倍数（4/N）
COOK_STRICT = 1.0  # Cook's D 严格阈值（>1 视为强影响点）
ALPHA = 0.05  # 显著性水平
DECIMALS = 4  # 输出保留小数位
RANDOM_SEED = 2023  # 随机种子（OLS 无随机性，为将来 bootstrap 预留）
OUTPUT_ENCODING = "utf-8-sig"  # 输出编码，兼容 Windows Excel


# ==================== 工具函数 ====================  # 工具函数区
def print_section(title: str) -> None:  # 定义分节标题打印函数
    """打印统一格式的分节标题。"""  # 函数说明
    print("\n" + "=" * 80)  # 打印上分隔线
    print(title)  # 打印标题
    print("=" * 80)  # 打印下分隔线


def require_statsmodels() -> None:  # 定义依赖检查函数
    """检查 statsmodels 是否可用，不可用时给出安装命令并退出。"""  # 函数说明
    if not HAS_STATSMODELS:  # 如果 statsmodels 不可用
        print("[错误] 未安装 statsmodels，请在 shipping 环境执行：")  # 打印提示
        print("    conda activate shipping")  # 打印激活命令
        print("    python -m pip install statsmodels")  # 打印安装命令
        raise SystemExit(1)  # 终止脚本


def subset_frame(data: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:  # 定义子样本函数
    """按掩码取子样本，并移除未使用的船型类别，避免虚拟变量全零。"""  # 函数说明
    subset = data.loc[mask].copy()  # 取出子样本并复制
    if isinstance(subset[TYPE_COL].dtype, pd.CategoricalDtype):  # 如果船型是分类类型
        subset[TYPE_COL] = subset[TYPE_COL].cat.remove_unused_categories()  # 删除未使用类别
    return subset  # 返回子样本


def fit_classic(formula: str, data: pd.DataFrame):  # 定义普通 OLS 拟合函数
    """用普通标准误拟合 OLS，用于计算 R²、F 和经典 p 值。"""  # 函数说明
    return smf.ols(formula, data=data).fit()  # 拟合并返回结果


def fit_robust(formula: str, data: pd.DataFrame, cov_type: str = "HC3", groups=None):  # 定义稳健 OLS 拟合函数
    """用 HC3（或聚类）稳健标准误拟合 OLS。"""  # 函数说明
    if groups is None:  # 如果不需要聚类
        return smf.ols(formula, data=data).fit(cov_type=cov_type)  # 使用 HC3 稳健标准误
    return smf.ols(formula, data=data).fit(cov_type=cov_type, cov_kwds={"groups": groups})  # 使用聚类稳健标准误


def print_model_summary(title: str, result, note: str = "", classic=None) -> None:  # 定义模型摘要打印函数
    """打印单个模型的 N、R²、调整 R²、F 与系数表。"""  # 函数说明
    print("-" * 80)  # 打印分隔线
    print(title)  # 打印模型标题
    if note:  # 如果有备注
        print(f"  备注：{note}")  # 打印备注
    print(f"  N = {int(result.nobs)}")  # 打印样本量
    print(f"  R² = {clean_r2(result.rsquared):.4f}   调整 R² = {clean_r2(result.rsquared_adj):.4f}")  # 打印 R² 与调整 R²
    classic_f = classic.fvalue if classic is not None else np.nan  # 取经典 F 值
    if np.isfinite(classic_f):  # 如果经典 F 有效
        print(f"  F(经典) = {classic_f:.4f}   p = {classic.f_pvalue:.4g}")  # 打印经典 F 与 p
    if np.isfinite(result.fvalue):  # 如果稳健 F 有效
        print(f"  F(HC3 Wald) = {result.fvalue:.4f}   p = {result.f_pvalue:.4g}")  # 打印稳健 F 与 p
    if not np.isfinite(classic_f) and not np.isfinite(result.fvalue):  # 如果两种 F 都无效
        print("  F = 不适用（空模型）")  # 打印空模型提示
    try:  # 尝试打印 statsmodels 系数表
        print(result.summary().tables[1].as_text())  # 打印系数、标准误、t、p
    except Exception:  # 如果表格接口异常
        table = pd.DataFrame({"coef": result.params, "se": result.bse, "t": result.tvalues, "p": result.pvalues})  # 手动组装系数表
        print(table.round(DECIMALS).to_string())  # 打印系数表


def clean_number(value: float) -> float:  # 定义数值整理函数
    """把 nan 或 inf 统一转为 NaN，便于写 CSV。"""  # 函数说明
    if value is None:  # 如果为空
        return np.nan  # 返回 NaN
    value = float(value)  # 转成浮点数
    return value if np.isfinite(value) else np.nan  # 非有限值返回 NaN


def clean_r2(value: float) -> float:  # 定义 R² 清理函数
    """把浮点误差造成的 -0.0000 归零。"""  # 函数说明
    value = float(value)  # 转成浮点数
    return 0.0 if abs(value) < 1e-12 else value  # 极小值归零


def build_row(section: str, model_id: str, formula: str, robust_result, classic_result,  # 定义结果行构造函数
              delta_r2: float = np.nan, note: str = "", core_term: str = CORE_X,  # 继续定义参数
              include_robust_f: bool = True) -> dict:  # 是否记录稳健 F（聚类模型不用）
    """把一个模型的结果整理成汇总表的一行。"""  # 函数说明
    r2_value = clean_r2(robust_result.rsquared)  # 取 R² 并清理浮点误差
    r2_adj_value = clean_r2(robust_result.rsquared_adj)  # 取调整 R² 并清理
    f_robust_value = np.nan  # 稳健 F 默认缺失
    f_p_robust_value = np.nan  # 稳健 F 的 p 值默认缺失
    if include_robust_f:  # 如果需要记录稳健 F
        with warnings.catch_warnings():  # 捕获并屏蔽已知的秩不足警告
            warnings.simplefilter("ignore")  # 忽略警告，避免污染终端
            f_robust_value = clean_number(robust_result.fvalue)  # 记录稳健 F
            f_p_robust_value = clean_number(robust_result.f_pvalue)  # 记录稳健 F 的 p 值
    row = {  # 开始组装字典
        "section": section,  # 结果分区
        "model_id": model_id,  # 模型编号
        "formula": formula,  # 回归公式
        "n": int(robust_result.nobs),  # 样本量
        "r2": round(r2_value, DECIMALS),  # R²
        "r2_adj": round(r2_adj_value, DECIMALS),  # 调整 R²
        "delta_r2": clean_number(delta_r2),  # 增量 R²
        "f": clean_number(classic_result.fvalue),  # 经典 F 统计量
        "f_p": clean_number(classic_result.f_pvalue),  # 经典 F 检验 p 值
        "f_robust": f_robust_value,  # 稳健 Wald F 统计量
        "f_p_robust": f_p_robust_value,  # 稳健 Wald F 的 p 值
        "coef_eexi": np.nan,  # EEXI 系数（默认缺失）
        "se_hc3": np.nan,  # HC3 标准误（默认缺失）
        "t_hc3": np.nan,  # HC3 t 值（默认缺失）
        "p_hc3": np.nan,  # HC3 p 值（默认缺失）
        "se_classic": np.nan,  # 普通标准误（默认缺失）
        "p_classic": np.nan,  # 普通 p 值（默认缺失）
        "note": note,  # 备注
    }  # 结束字典
    if core_term in robust_result.params.index:  # 如果模型包含核心变量
        row["coef_eexi"] = round(float(robust_result.params[core_term]), DECIMALS)  # 记录核心系数
        row["se_hc3"] = round(float(robust_result.bse[core_term]), DECIMALS)  # 记录 HC3 标准误
        row["t_hc3"] = round(float(robust_result.tvalues[core_term]), DECIMALS)  # 记录 HC3 t 值
        row["p_hc3"] = clean_number(robust_result.pvalues[core_term])  # 记录 HC3 p 值
        row["se_classic"] = round(float(classic_result.bse[core_term]), DECIMALS)  # 记录普通标准误
        row["p_classic"] = clean_number(classic_result.pvalues[core_term])  # 记录普通 p 值
    return row  # 返回结果行


def to_markdown(data: pd.DataFrame) -> str:  # 定义 markdown 表格生成函数
    """不依赖 tabulate，把 DataFrame 转成 markdown 表格。"""  # 函数说明
    columns = list(data.columns)  # 取出列名
    lines = ["| " + " | ".join(columns) + " |"]  # 生成表头行
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")  # 生成分隔行
    for _, row in data.iterrows():  # 遍历每一行
        values = []  # 保存格式化后的单元格
        for column in columns:  # 遍历每一列
            value = row[column]  # 取出单元格
            if isinstance(value, (float, np.floating)):  # 如果是浮点数
                if pd.isna(value):  # 如果是缺失值
                    values.append("")  # 输出空字符串
                elif value != 0 and abs(value) < 1e-4:  # 如果是极小值
                    values.append(f"{value:.3g}")  # 用科学计数法显示
                else:  # 其他浮点数
                    values.append(f"{value:.{DECIMALS}f}")  # 保留固定小数位
            else:  # 如果是其他类型
                values.append(str(value))  # 直接转字符串
        lines.append("| " + " | ".join(values) + " |")  # 生成数据行
    return "\n".join(lines)  # 返回 markdown 文本


# ==================== 主流程 ====================  # 主流程区
def main() -> None:  # 定义主函数
    """执行完整建模流程并输出结果表。"""  # 函数说明
    if hasattr(sys.stdout, "reconfigure"):  # 如果标准输出支持重配置
        sys.stdout.reconfigure(encoding="utf-8")  # 设置 UTF-8 输出，避免中文乱码
    np.random.seed(RANDOM_SEED)  # 固定随机种子（OLS 本身无随机性）
    require_statsmodels()  # 检查 statsmodels 是否可用
    print(f"Python 解释器：{sys.executable}")  # 打印解释器路径，确认环境
    print(f"输入文件：{INPUT_FILE}")  # 打印输入路径
    print(f"输出文件：{OUTPUT_FILE}")  # 打印输出路径

    print_section("第1步：读取数据并检查")  # 打印第 1 步标题
    if not INPUT_FILE.exists():  # 如果输入文件不存在
        raise FileNotFoundError(f"输入文件不存在：{INPUT_FILE}")  # 抛出明确异常
    df = pd.read_csv(INPUT_FILE)  # 读取清洗后的数据
    print(f"样本量：{len(df)} 行，{len(df.columns)} 列")  # 打印行列数
    print(f"缺失值总数：{int(df.isna().sum().sum())}")  # 打印缺失值总数
    if df.isna().sum().sum() > 0:  # 如果存在缺失值
        print(df.isna().sum().to_string())  # 打印每列缺失数
        raise SystemExit("存在缺失值，请先检查 01_clean.py 的输出")  # 终止并提示
    print("各船型样本量：")  # 打印提示
    print(df[TYPE_COL].value_counts().to_string())  # 打印各船型样本量
    type_order = [REFERENCE_TYPE] + [name for name in ALL_TYPES if name != REFERENCE_TYPE]  # 构造船型类别顺序
    df[TYPE_COL] = pd.Categorical(df[TYPE_COL], categories=type_order)  # 设为分类变量，参照组为集装箱船
    print(f"船型虚拟变量参照组：{REFERENCE_TYPE}")  # 打印参照组
    df["ln_y"] = np.log(df[DEPENDENT])  # 构造对数因变量
    df["ln_eexi"] = np.log(df[CORE_X])  # 构造对数 EEXI
    df["ln_total_co2"] = np.log(df[SIZE_CONTROL])  # 构造对数总 CO2
    print("已构造对数变量：ln_y, ln_eexi, ln_total_co2")  # 打印提示

    print_section("第2步：主模型阶梯 M0-M4（含 M3' 对照）")  # 打印第 2 步标题
    main_models = [  # 定义主模型列表
        ("M0", f"{DEPENDENT} ~ 1", "空模型（R² 基准，F 不适用）"),  # 空模型
        ("M1", f"{DEPENDENT} ~ {SIZE_CONTROL}", "基线：仅规模控制"),  # 规模基线
        ("M2", f"{DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL})", "加船型固定效应"),  # 船型固定效应
        ("M3", f"{DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL}) + {CORE_X}", "完整模型：核心模型"),  # 核心模型
        ("M3p", f"{DEPENDENT} ~ C({TYPE_COL}) + {CORE_X}", "对照：不含规模控制"),  # 不含规模控制的对照
        ("M4", f"{DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL}) + {CORE_X} + {CORE_X}:C({TYPE_COL})", "加船型×EEXI 交互"),  # 交互模型
    ]  # 结束主模型列表
    main_results = {}  # 保存稳健标准误结果
    main_classic = {}  # 保存普通标准误结果
    for model_id, formula, note in main_models:  # 遍历主模型
        classic = fit_classic(formula, df)  # 普通 OLS 拟合
        robust = fit_robust(formula, df, "HC3")  # HC3 稳健 OLS 拟合
        main_results[model_id] = robust  # 保存稳健结果
        main_classic[model_id] = classic  # 保存普通结果
        print_model_summary(f"{model_id}：{formula}", robust, note, classic=classic)  # 打印模型摘要

    m4_params = list(main_classic["M4"].params.index)  # 取 M4 参数名列表
    interaction_positions = [index for index, name in enumerate(m4_params) if ":" in name]  # 定位交互项位置
    restriction = np.zeros((len(interaction_positions), len(m4_params)))  # 初始化约束矩阵
    for row_index, column_index in enumerate(interaction_positions):  # 遍历交互项
        restriction[row_index, column_index] = 1.0  # 对应位置设为 1
    classic_joint = main_classic["M4"].f_test(restriction)  # 经典联合 F 检验
    f_joint = float(classic_joint.fvalue)  # 取经典 F 值
    p_joint = float(classic_joint.pvalue)  # 取经典 p 值
    df_joint = len(interaction_positions)  # 约束个数
    robust_joint = main_results["M4"].wald_test(restriction, scalar=True)  # HC3 稳健联合 Wald 检验
    f_joint_robust = float(robust_joint.statistic)  # 取稳健 F 值
    p_joint_robust = float(robust_joint.pvalue)  # 取稳健 p 值
    print("-" * 80)  # 打印分隔线
    print(f"M4 交互项联合检验：经典 F = {f_joint:.4f}（p = {p_joint:.4g}）；"  # 打印经典检验结果
          f"HC3 Wald F = {f_joint_robust:.4f}（p = {p_joint_robust:.4g}）；自由度 = {df_joint}")  # 打印稳健检验结果
    if p_joint_robust < ALPHA:  # 以稳健 p 值为判据
        print("  → 船型间 EEXI 斜率存在显著差异（以 HC3 稳健检验为准）")  # 打印显著结论
    else:  # 如果联合检验不显著
        print("  → 未发现船型间 EEXI 斜率显著差异（以 HC3 稳健检验为准）")  # 打印不显著结论

    r2_m0 = clean_r2(main_results["M0"].rsquared)  # 取 M0 的 R² 并清理浮点误差
    r2_m1 = clean_r2(main_results["M1"].rsquared)  # 取 M1 的 R²
    r2_m2 = clean_r2(main_results["M2"].rsquared)  # 取 M2 的 R²
    r2_m3 = clean_r2(main_results["M3"].rsquared)  # 取 M3 的 R²
    r2_m4 = clean_r2(main_results["M4"].rsquared)  # 取 M4 的 R²
    delta_m2 = r2_m2 - r2_m1  # 船型的增量 R²
    delta_m3 = r2_m3 - r2_m2  # EEXI 的增量 R²
    delta_m4 = r2_m4 - r2_m3  # 交互项的增量 R²
    print("-" * 80)  # 打印分隔线
    print("R² 阶梯：")  # 打印提示
    print(f"  M0 空模型        R² = {r2_m0:.4f}")  # 打印 M0
    print(f"  M1 仅规模        R² = {r2_m1:.4f}")  # 打印 M1
    print(f"  M2 +船型         R² = {r2_m2:.4f}   ΔR² = {delta_m2:.4f}")  # 打印 M2
    print(f"  M3 +EEXI         R² = {r2_m3:.4f}   ΔR² = {delta_m3:.4f}")  # 打印 M3
    print(f"  M4 +交互         R² = {r2_m4:.4f}   ΔR² = {delta_m4:.4f}")  # 打印 M4

    rows = []  # 保存所有模型结果行
    delta_map = {"M2": delta_m2, "M3": delta_m3, "M4": delta_m4}  # 增量 R² 映射
    for model_id, formula, note in main_models:  # 遍历主模型
        current_note = note  # 复制备注
        if model_id == "M4":  # 如果是交互模型
            current_note = (f"{note}；经典联合 F={f_joint:.3f}(p={p_joint:.3g})；"  # 追加经典联合检验
                            f"HC3 联合 F={f_joint_robust:.3f}(p={p_joint_robust:.3g})")  # 追加稳健联合检验
        rows.append(build_row("main", model_id, formula, main_results[model_id],  # 构造结果行
                              main_classic[model_id], delta_map.get(model_id, np.nan), current_note))  # 追加到结果列表

    print_section("第3步：异质性分析")  # 打印第 3 步标题
    print("3.1 分船型回归：Y ~ total_co2 + eexi_value")  # 打印小节标题
    type_table = []  # 保存分船型展示表
    for type_name in ALL_TYPES:  # 遍历三种船型
        mask = df[TYPE_COL] == type_name  # 构造当前船型掩码
        sub = subset_frame(df, mask)  # 取出子样本
        base_formula = f"{DEPENDENT} ~ {SIZE_CONTROL}"  # 仅规模的基线公式
        full_formula = f"{DEPENDENT} ~ {SIZE_CONTROL} + {CORE_X}"  # 加入 EEXI 的公式
        base = fit_classic(base_formula, sub)  # 拟合仅规模模型
        classic = fit_classic(full_formula, sub)  # 拟合完整模型（普通标准误）
        robust = fit_robust(full_formula, sub, "HC3")  # 拟合完整模型（HC3）
        delta = classic.rsquared - base.rsquared  # 计算 EEXI 的增量 R²
        coef = float(robust.params[CORE_X])  # 取 EEXI 系数
        p_value = float(robust.pvalues[CORE_X])  # 取 HC3 p 值
        print(f"  {type_name:<15} N={int(robust.nobs):4d}  R²(仅规模)={base.rsquared:.4f}  "  # 打印模型摘要
              f"R²(规模+EEXI)={classic.rsquared:.4f}  ΔR²={delta:.4f}  b={coef:.4f}  p={p_value:.3g}")  # 继续打印
        type_table.append({"ship_type": type_name, "n": int(robust.nobs), "r2_size": round(base.rsquared, DECIMALS),  # 记录展示行
                           "r2_full": round(classic.rsquared, DECIMALS), "delta_r2": round(delta, DECIMALS),  # 记录 R²
                           "coef_eexi": round(coef, DECIMALS), "p_hc3": p_value})  # 记录系数与 p
        rows.append(build_row("heterogeneity", f"type:{type_name}", full_formula, robust, classic,  # 构造结果行
                              delta, "分船型回归；ΔR² 相对 Y ~ total_co2"))  # 追加到结果列表
    print("\n分船型结果表：")  # 打印提示
    print(to_markdown(pd.DataFrame(type_table)))  # 打印 markdown 表

    print("\n3.2 船型 × 船型内大小组回归：Y ~ total_co2 + eexi_value")  # 打印小节标题
    group_table = []  # 保存 9 组展示表
    for type_name in ALL_TYPES:  # 遍历三种船型
        for label in GROUP_LABELS:  # 遍历三个大小组
            mask = (df[TYPE_COL] == type_name) & (df[WITHIN_GROUP] == label)  # 构造组掩码
            sub = subset_frame(df, mask)  # 取出子样本
            if len(sub) < 10:  # 如果样本过少
                print(f"  [跳过] {type_name} / {label} 样本量不足：{len(sub)}")  # 打印跳过提示
                continue  # 跳过当前组
            formula = f"{DEPENDENT} ~ {SIZE_CONTROL} + {CORE_X}"  # 组内回归公式
            classic = fit_classic(formula, sub)  # 普通 OLS
            robust = fit_robust(formula, sub, "HC3")  # HC3 稳健 OLS
            coef = float(robust.params[CORE_X])  # 取 EEXI 系数
            p_value = float(robust.pvalues[CORE_X])  # 取 HC3 p 值
            p_classic = float(classic.pvalues[CORE_X])  # 取经典 p 值
            max_h = float(np.max(classic.get_influence().hat_matrix_diag))  # 计算组内最大杠杆值
            print(f"  {type_name:<15} {label:<7} N={len(sub):4d}  R²={classic.rsquared:.4f}  "  # 打印组摘要
                  f"b={coef:.4f}  p_hc3={p_value:.3g}  p_classic={p_classic:.3g}  max_h={max_h:.3f}")  # 继续打印
            if max_h > 0.2:  # 如果组内存在高杠杆点
                print(f"    [警告] 组内最大杠杆值 {max_h:.3f} 偏高，HC3 标准误可能被放大")  # 打印杠杆警告
            group_table.append({"ship_type": type_name, "size_group": label, "n": len(sub),  # 记录展示行
                                "r2": round(classic.rsquared, DECIMALS), "coef_eexi": round(coef, DECIMALS),  # 记录 R² 与系数
                                "p_hc3": p_value, "p_classic": p_classic, "max_h": round(max_h, DECIMALS)})  # 记录 p 与杠杆值
            group_note = "9 组异质性回归"  # 默认备注
            if max_h > 0.2:  # 如果组内存在高杠杆点
                group_note += f"；max_h={max_h:.3f}，HC3 标准误可能被放大"  # 追加杠杆提示
            rows.append(build_row("heterogeneity", f"{type_name} / {label}", formula, robust, classic,  # 构造结果行
                                  np.nan, group_note))  # 追加到结果列表
    print("\n9 组结果表：")  # 打印提示
    print(to_markdown(pd.DataFrame(group_table)))  # 打印 markdown 表

    print("\n3.3 全样本大小组回归：Y ~ C(ship_type) + eexi_value（已去掉 total_co2）")  # 打印小节标题
    size_table = []  # 保存 3 组展示表
    for label in GROUP_LABELS:  # 遍历三个全样本大小组
        mask = df[SIZE_GROUP] == label  # 构造组掩码
        sub = subset_frame(df, mask)  # 取出子样本
        formula = f"{DEPENDENT} ~ C({TYPE_COL}) + {CORE_X}"  # 组内公式（不含规模控制）
        classic = fit_classic(formula, sub)  # 普通 OLS
        robust = fit_robust(formula, sub, "HC3")  # HC3 稳健 OLS
        coef = float(robust.params[CORE_X])  # 取 EEXI 系数
        p_value = float(robust.pvalues[CORE_X])  # 取 HC3 p 值
        p_classic = float(classic.pvalues[CORE_X])  # 取经典 p 值
        max_h = float(np.max(classic.get_influence().hat_matrix_diag))  # 计算组内最大杠杆值
        print(f"  {label:<7} N={len(sub):4d}  R²={classic.rsquared:.4f}  b={coef:.4f}  "  # 打印组摘要
              f"p_hc3={p_value:.3g}  p_classic={p_classic:.3g}  max_h={max_h:.3f}")  # 继续打印
        if max_h > 0.2:  # 如果组内存在高杠杆点
            print(f"    [警告] 组内最大杠杆值 {max_h:.3f} 偏高，HC3 标准误可能被放大")  # 打印杠杆警告
        size_table.append({"size_group": label, "n": len(sub), "r2": round(classic.rsquared, DECIMALS),  # 记录展示行
                           "coef_eexi": round(coef, DECIMALS), "p_hc3": p_value,  # 记录系数与 HC3 p 值
                           "p_classic": p_classic, "max_h": round(max_h, DECIMALS)})  # 记录经典 p 与杠杆值
        rows.append(build_row("heterogeneity", f"size:{label}", formula, robust, classic,  # 构造结果行
                              np.nan, "全样本大小组；已去掉 total_co2"))  # 追加到结果列表
    print("\n全样本大小组结果表：")  # 打印提示
    print(to_markdown(pd.DataFrame(size_table)))  # 打印 markdown 表

    print_section("第4步：稳健性检验（7 项）")  # 打印第 4 步标题
    print("4.1 不缩尾：用原始 co2_intensity 跑 M3")  # 打印小节标题
    raw_formula = f"{RAW_DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL}) + {CORE_X}"  # 原始因变量公式
    raw_classic = fit_classic(raw_formula, df)  # 普通 OLS
    raw_robust = fit_robust(raw_formula, df, "HC3")  # HC3 稳健 OLS
    print(f"  N={int(raw_robust.nobs)}  R²={raw_classic.rsquared:.4f}  "  # 打印摘要
          f"b={float(raw_robust.params[CORE_X]):.4f}  p={float(raw_robust.pvalues[CORE_X]):.3g}")  # 继续打印
    print(f"  对比：缩尾模型 M3 的 R² = {r2_m3:.4f}")  # 打印缩尾模型对比
    raw_note = f"原始因变量（不缩尾）；R²={raw_classic.rsquared:.4f}（缩尾模型 {r2_m3:.4f}）"  # 组装备注
    rows.append(build_row("robustness", "R1_raw_y", raw_formula, raw_robust, raw_classic,  # 构造结果行
                          np.nan, raw_note))  # 追加到结果列表

    print("\n4.1b 因变量上下各剔除 1% 后跑 M3（补充对照）")  # 打印小节标题
    low_y = float(df[DEPENDENT].quantile(0.01))  # 计算因变量 1% 分位
    high_y = float(df[DEPENDENT].quantile(0.99))  # 计算因变量 99% 分位
    trim_y_mask = df[DEPENDENT].between(low_y, high_y)  # 构造保留掩码
    sub_y = subset_frame(df, trim_y_mask)  # 取出子样本
    trim_y_formula = f"{DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL}) + {CORE_X}"  # 区间样本公式
    trim_y_classic = fit_classic(trim_y_formula, sub_y)  # 普通 OLS
    trim_y_robust = fit_robust(trim_y_formula, sub_y, "HC3")  # HC3 稳健 OLS
    print(f"  N={int(trim_y_robust.nobs)}  R²={trim_y_classic.rsquared:.4f}  "  # 打印摘要
          f"b={float(trim_y_robust.params[CORE_X]):.4f}  p={float(trim_y_robust.pvalues[CORE_X]):.3g}")  # 继续打印
    rows.append(build_row("robustness", "R1b_trim_y", trim_y_formula, trim_y_robust, trim_y_classic,  # 构造结果行
                          np.nan, "因变量上下各剔除 1%"))  # 追加到结果列表

    print("\n4.2 对数变换：ln(Y) ~ ln(total_co2) + C(ship_type) + ln(eexi)")  # 打印小节标题
    log_formula = f"ln_y ~ ln_total_co2 + C({TYPE_COL}) + ln_eexi"  # 对数模型公式
    log_classic = fit_classic(log_formula, df)  # 普通 OLS
    log_robust = fit_robust(log_formula, df, "HC3")  # HC3 稳健 OLS
    log_coef = float(log_robust.params["ln_eexi"])  # 取弹性系数
    print(f"  N={int(log_robust.nobs)}  R²={log_classic.rsquared:.4f}  "  # 打印摘要
          f"弹性={log_coef:.4f}  p={float(log_robust.pvalues['ln_eexi']):.3g}")  # 继续打印
    print(f"  解释：EEXI 提高 1%，碳强度约变化 {log_coef:.2f}%")  # 打印弹性解释
    rows.append(build_row("robustness", "R2_loglog", log_formula, log_robust, log_classic,  # 构造结果行
                          np.nan, "对数-对数模型；系数为弹性", core_term="ln_eexi"))  # 追加到结果列表

    print("\n4.3 剔除 EEXI 上下各 1%（船型内口径，与 01 缩尾一致）跑 M3")  # 打印小节标题
    keep_mask = pd.Series(False, index=df.index)  # 初始化保留掩码
    for type_name in ALL_TYPES:  # 遍历三种船型
        type_mask = df[TYPE_COL] == type_name  # 当前船型掩码
        low_x = float(df.loc[type_mask, CORE_X].quantile(0.01))  # 船型内 1% 分位
        high_x = float(df.loc[type_mask, CORE_X].quantile(0.99))  # 船型内 99% 分位
        keep_mask |= type_mask & df[CORE_X].between(low_x, high_x)  # 累积保留样本
    sub_x = subset_frame(df, keep_mask)  # 取出子样本
    trim_x_formula = f"{DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL}) + {CORE_X}"  # 区间样本公式
    trim_x_classic = fit_classic(trim_x_formula, sub_x)  # 普通 OLS
    trim_x_robust = fit_robust(trim_x_formula, sub_x, "HC3")  # HC3 稳健 OLS
    print(f"  N={int(trim_x_robust.nobs)}  R²={trim_x_classic.rsquared:.4f}  "  # 打印摘要
          f"b={float(trim_x_robust.params[CORE_X]):.4f}  p={float(trim_x_robust.pvalues[CORE_X]):.3g}")  # 继续打印
    rows.append(build_row("robustness", "R3_trim_x", trim_x_formula, trim_x_robust, trim_x_classic,  # 构造结果行
                          np.nan, "剔除 EEXI 1%/99%（船型内）"))  # 追加到结果列表

    print("\n4.4 用 ln(total_co2) 替换线性规模项跑 M3")  # 打印小节标题
    ln_size_formula = f"{DEPENDENT} ~ ln_total_co2 + C({TYPE_COL}) + {CORE_X}"  # 对数规模公式
    ln_size_classic = fit_classic(ln_size_formula, df)  # 普通 OLS
    ln_size_robust = fit_robust(ln_size_formula, df, "HC3")  # HC3 稳健 OLS
    print(f"  N={int(ln_size_robust.nobs)}  R²={ln_size_classic.rsquared:.4f}  "  # 打印摘要
          f"b={float(ln_size_robust.params[CORE_X]):.4f}  p={float(ln_size_robust.pvalues[CORE_X]):.3g}")  # 继续打印
    rows.append(build_row("robustness", "R4_ln_size", ln_size_formula, ln_size_robust, ln_size_classic,  # 构造结果行
                          np.nan, "规模项改为 ln(total_co2)"))  # 追加到结果列表

    print("\n4.5 仅集装箱船子样本跑完整模型")  # 打印小节标题
    container_sub = subset_frame(df, df[TYPE_COL] == REFERENCE_TYPE)  # 取出集装箱船子样本
    container_formula = f"{DEPENDENT} ~ {SIZE_CONTROL} + {CORE_X}"  # 子样本公式（单船型无需虚拟变量）
    container_classic = fit_classic(container_formula, container_sub)  # 普通 OLS
    container_robust = fit_robust(container_formula, container_sub, "HC3")  # HC3 稳健 OLS
    print(f"  N={int(container_robust.nobs)}  R²={container_classic.rsquared:.4f}  "  # 打印摘要
          f"b={float(container_robust.params[CORE_X]):.4f}  p={float(container_robust.pvalues[CORE_X]):.3g}")  # 继续打印
    rows.append(build_row("robustness", "R5_container", container_formula, container_robust,  # 构造结果行
                          container_classic, np.nan, "仅集装箱船子样本"))  # 追加到结果列表

    print("\n4.6 聚类稳健标准误（按 ship_type 聚类，仅 3 个 cluster，仅供参考）")  # 打印小节标题
    cluster_groups = df[TYPE_COL].astype(str)  # 聚类变量转字符串
    cluster_formula = f"{DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL}) + {CORE_X}"  # 聚类模型公式
    cluster_robust = fit_robust(cluster_formula, df, "cluster", groups=cluster_groups)  # 聚类稳健 OLS
    cluster_coef = float(cluster_robust.params[CORE_X])  # 取聚类标准误下的系数
    cluster_se = float(cluster_robust.bse[CORE_X])  # 取聚类标准误
    cluster_p = float(cluster_robust.pvalues[CORE_X])  # 取聚类 p 值
    hc3_se = float(main_results["M3"].bse[CORE_X])  # 取 HC3 标准误
    print(f"  cluster 数={cluster_groups.nunique()}  b={cluster_coef:.4f}  se={cluster_se:.4f}  p={cluster_p:.3g}")  # 打印聚类结果
    print(f"  对比：HC3 标准误 = {hc3_se:.4f}")  # 打印 HC3 对比
    if cluster_groups.nunique() < 30:  # 如果聚类数过少
        print("  [警告] 聚类数仅 3 个，聚类稳健标准误不可靠，主结果以 HC3 为准")  # 打印警告
    rows.append(build_row("robustness", "R6_cluster", cluster_formula, cluster_robust,  # 构造结果行
                          main_classic["M3"], np.nan, "按船型聚类；仅 3 个 cluster，可靠性低",  # 传入结果
                          include_robust_f=False))  # 聚类协方差秩不足，不记录稳健 F

    print("\n4.7 Cook's Distance 影响点分析（基于 M3）")  # 打印小节标题
    try:  # 尝试直接从 HC3 结果提取影响度
        influence = main_results["M3"].get_influence()  # 计算影响度对象
        cooks = influence.cooks_distance[0]  # 取 Cook's D 数组
    except Exception:  # 如果 HC3 结果不支持
        influence = main_classic["M3"].get_influence()  # 改用普通 OLS 结果计算
        cooks = influence.cooks_distance[0]  # 取 Cook's D 数组
    cook_threshold = COOK_MULT / len(df)  # 计算 4/N 阈值
    flag_cook = cooks > cook_threshold  # 标记超过 4/N 的样本
    strict_count = int((cooks > COOK_STRICT).sum())  # 统计超过严格阈值的样本
    flag_count = int(flag_cook.sum())  # 统计超过 4/N 的样本
    flag_share = flag_count / len(df) * 100  # 计算占比（百分比）
    print(f"  N = {len(df)}，4/N 阈值 = {cook_threshold:.6f}")  # 打印阈值
    print(f"  超过 4/N：{flag_count} 艘（{flag_share:.2f}%）")  # 打印超阈值数量与占比
    print(f"  超过 1.0 ：{strict_count} 艘")  # 打印严格阈值数量
    print(f"  最大 Cook's D：{float(np.max(cooks)):.4f}")  # 打印最大影响度
    top_values = np.sort(cooks)[-5:][::-1]  # 取最大的 5 个影响度
    print(f"  前 5 大 Cook's D：{np.round(top_values, 4).tolist()}")  # 打印前 5 大影响度

    cook_sub = subset_frame(df, ~flag_cook)  # 剔除影响点后的子样本
    cook_formula = f"{DEPENDENT} ~ {SIZE_CONTROL} + C({TYPE_COL}) + {CORE_X}"  # M3 公式
    cook_classic = fit_classic(cook_formula, cook_sub)  # 剔除后普通 OLS
    cook_robust = fit_robust(cook_formula, cook_sub, "HC3")  # 剔除后 HC3 稳健 OLS
    coef_before = float(main_results["M3"].params[CORE_X])  # 剔除前 EEXI 系数
    coef_after = float(cook_robust.params[CORE_X])  # 剔除后 EEXI 系数
    coef_change = (coef_after - coef_before) / coef_before * 100  # 系数变化百分比
    r2_before = float(main_results["M3"].rsquared)  # 剔除前 R²
    r2_after = float(cook_classic.rsquared)  # 剔除后 R²
    r2_change = (r2_after - r2_before) / r2_before * 100  # R² 变化百分比
    p_after = float(cook_robust.pvalues[CORE_X])  # 剔除后 p 值
    print(f"  剔除后 N = {int(cook_robust.nobs)}")  # 打印剔除后样本量
    print(f"  {'指标':<10}{'全样本':>12}{'剔除后':>12}{'变化':>12}")  # 打印表头
    print(f"  {'N':<10}{len(df):>12d}{int(cook_robust.nobs):>12d}{'':>12}")  # 打印样本量对比
    print(f"  {'R²':<10}{r2_before:>12.4f}{r2_after:>12.4f}{r2_change:>11.2f}%")  # 打印 R² 对比
    print(f"  {'eexi 系数':<10}{coef_before:>12.4f}{coef_after:>12.4f}{coef_change:>11.2f}%")  # 打印系数对比
    print(f"  {'eexi p 值':<10}{'≈0':>12}{p_after:>12.3g}{'':>12}")  # 打印 p 值对比
    print("  说明：剔除高残差样本会机械抬高 R²，稳健性判据只看系数变化与显著性")  # 打印方法说明
    if abs(coef_change) < 5 and p_after < ALPHA:  # 如果系数变化小于 5% 且仍显著
        print("  结论：系数变化 < 5% 且显著性不变 → 结果稳健，不受少数影响点驱动")  # 打印稳健结论
    else:  # 如果系数变化过大或显著性改变
        print("  结论：系数变化较大或显著性改变 → 结果对影响点敏感，需在报告中说明")  # 打印不稳健提示
    cook_note = f"Cook's D > 4/N：{flag_count} 艘；D > 1：{strict_count} 艘；系数变化 {coef_change:.2f}%"  # 组装备注
    rows.append(build_row("robustness", "R7_cook", cook_formula, cook_robust, cook_classic,  # 构造结果行
                          r2_after - r2_before, cook_note))  # 追加到结果列表

    print_section("第5步：R² Shapley 分解")  # 打印第 5 步标题
    type_term = f"C({TYPE_COL})"  # 船型项公式片段
    subset_terms = {  # 定义 8 个子集
        "none": [],  # 空集
        "size": [SIZE_CONTROL],  # 仅规模
        "type": [type_term],  # 仅船型
        "eexi": [CORE_X],  # 仅 EEXI
        "size+type": [SIZE_CONTROL, type_term],  # 规模+船型
        "size+eexi": [SIZE_CONTROL, CORE_X],  # 规模+EEXI
        "type+eexi": [type_term, CORE_X],  # 船型+EEXI
        "size+type+eexi": [SIZE_CONTROL, type_term, CORE_X],  # 全部
    }  # 结束子集定义
    r2_subset = {}  # 保存各子集 R²
    for key, terms in subset_terms.items():  # 遍历所有子集
        formula = f"{DEPENDENT} ~ 1" if not terms else f"{DEPENDENT} ~ " + " + ".join(terms)  # 组装公式
        subset_r2 = float(smf.ols(formula, data=df).fit().rsquared)  # 拟合子集并取 R²
        r2_subset[key] = 0.0 if abs(subset_r2) < 1e-12 else subset_r2  # 归零浮点误差
        print(f"  R²[{key}] = {r2_subset[key]:.4f}")  # 打印子集 R²
    shapley_size = (1 / 3) * r2_subset["size"]  # 规模：单变量项
    shapley_size += (1 / 6) * ((r2_subset["size+type"] - r2_subset["type"]) + (r2_subset["size+eexi"] - r2_subset["eexi"]))  # 规模：两变量项
    shapley_size += (1 / 3) * (r2_subset["size+type+eexi"] - r2_subset["type+eexi"])  # 规模：三变量项
    shapley_type = (1 / 3) * r2_subset["type"]  # 船型：单变量项
    shapley_type += (1 / 6) * ((r2_subset["size+type"] - r2_subset["size"]) + (r2_subset["type+eexi"] - r2_subset["eexi"]))  # 船型：两变量项
    shapley_type += (1 / 3) * (r2_subset["size+type+eexi"] - r2_subset["size+eexi"])  # 船型：三变量项
    shapley_eexi = (1 / 3) * r2_subset["eexi"]  # EEXI：单变量项
    shapley_eexi += (1 / 6) * ((r2_subset["size+eexi"] - r2_subset["size"]) + (r2_subset["type+eexi"] - r2_subset["type"]))  # EEXI：两变量项
    shapley_eexi += (1 / 3) * (r2_subset["size+type+eexi"] - r2_subset["size+type"])  # EEXI：三变量项
    shapley_total = shapley_size + shapley_type + shapley_eexi  # 三项之和应等于完整模型 R²
    print(f"\nShapley：Size = {shapley_size:.4f}，Type = {shapley_type:.4f}，EEXI = {shapley_eexi:.4f}")  # 打印分解结果
    print(f"三项合计 = {shapley_total:.4f}，完整模型 R² = {r2_subset['size+type+eexi']:.4f}")  # 打印校验
    shapley_df = pd.DataFrame([  # 组装 Shapley 结果表
        {"component": "Size (total_co2)", "shapley_r2": round(shapley_size, DECIMALS),  # 规模贡献
         "share_of_r2": round(shapley_size / shapley_total, DECIMALS)},  # 占总解释力比例
        {"component": "Type (ship_type)", "shapley_r2": round(shapley_type, DECIMALS),  # 船型贡献
         "share_of_r2": round(shapley_type / shapley_total, DECIMALS)},  # 占总解释力比例
        {"component": "EEXI (eexi_value)", "shapley_r2": round(shapley_eexi, DECIMALS),  # EEXI 贡献
         "share_of_r2": round(shapley_eexi / shapley_total, DECIMALS)},  # 占总解释力比例
        {"component": "Total", "shapley_r2": round(shapley_total, DECIMALS),  # 合计
         "share_of_r2": 1.0},  # 合计占比
    ])  # 结束结果表
    print(to_markdown(shapley_df))  # 打印 markdown 表

    print_section("第6步：保存结果并打印汇总表")  # 打印第 6 步标题
    results_df = pd.DataFrame(rows)  # 汇总所有模型结果
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)  # 创建 tables 目录
    results_df.to_csv(OUTPUT_FILE, index=False, encoding=OUTPUT_ENCODING)  # 保存模型结果
    shapley_df.to_csv(SHAPLEY_FILE, index=False, encoding=OUTPUT_ENCODING)  # 保存 Shapley 分解
    print(f"已保存：{OUTPUT_FILE}（{len(results_df)} 行）")  # 打印保存路径与行数
    print(f"已保存：{SHAPLEY_FILE}（{len(shapley_df)} 行）")  # 打印保存路径与行数
    summary_columns = ["section", "model_id", "n", "r2", "r2_adj", "delta_r2", "coef_eexi", "p_hc3", "note"]  # 汇总表展示列
    summary_view = results_df[summary_columns].copy()  # 取出展示列并复制
    numeric_columns = ["n", "r2", "r2_adj", "delta_r2", "coef_eexi"]  # 需要保留小数的列（p 值不四舍五入）
    summary_view[numeric_columns] = summary_view[numeric_columns].round(DECIMALS)  # 只对数值列四舍五入
    print("\n模型结果汇总：")  # 打印提示
    print(to_markdown(summary_view))  # 打印 markdown 汇总表
    print("\n模型分析完成")  # 打印完成提示


if __name__ == "__main__":  # 判断是否作为主程序运行
    main()  # 调用主函数
