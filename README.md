# 基于2023年欧盟MRV三种船型的EEXI设计能效对船舶碳强度差异的解释力分析

## 一句话
EEXI 设计能效能解释多少船舶实际碳强度差异？不同船型是否一样？

## 研究问题
1. EEXI 单独能解释多少碳强度方差？
2. 控制排放规模与船型后，EEXI 的增量解释力是多少？
3. 解释力在船型之间、以及船型内部不同规模组之间是否存在差异？

## 怎样运行
环境：按课程网站《环境配置》页面安装本地开发环境。
- Python 3.12（conda 环境 `shipping`）
- pandas 3.0.6 / numpy 2.5.4 / scipy / scikit-learn
- statsmodels 0.15.0（`python -m pip install statsmodels`）
- matplotlib 3.11.2

把原始数据放进 `data/raw/`，然后在项目根目录依次运行：

```bash
conda activate shipping

python analysis/01_clean.py         # → data/clean/ships_clean.csv（4,105 艘）
python analysis/02_explore.py       # → figures/fig01、fig02、fig03
python analysis/03_model.py         # → tables/model_results.csv 等
python analysis/plot_r2_groups.py   # → figures/fig04
```

> **关于图3**：`02_explore.py` 直接读取仓库内已生成的
> `data/explore/registry_map_ready.csv`（30 组 / 3,467 艘），
> 不需要联网，也不需要 UN/LOCODE 数据。
> 只有更换年份或重建该表时，才运行
> `python analysis/tools/prepare_registry_map.py`
> （该脚本需要 `data/raw/unlocode/unlocode_latest.zip`）。

## 数据从哪里来
| 文件 | 来源 | 性质 | 下载日期 |
|---|---|---|---|
| `data/raw/thrtis_mrv_2023.xlsx` | EMSA THETIS-MRV 官网（欧洲海事安全局） | 〔官〕 | 2026.10.25 |
| `data/raw/unlocode/unlocode_latest.zip` | UN/LOCODE（联合国贸易便利化与电子业务中心） | 〔官〕 | 2026.11.02 |

- 数据年份：2023 年（单年横截面）
- 原始规模：12,829 行 × 62 列
- 清洗后样本：**4,105 艘**（集装箱 1,480 / 散货 1,686 / 油船 939）

## 项目结构
```
MRV_dazuoye/
├── analysis/
│   ├── 01_clean.py                   数据清洗
│   ├── 02_explore.py                 图1、图2，并调用 plot_registry_map.py 生成图3
│   ├── 03_model.py                   模型 M0–M4、异质性、7 项稳健性
│   ├── plot_registry_map.py          图3 绘图（被 02 调用，也可单独运行）
│   ├── plot_r2_groups.py             图4（9 组 R²，读 03 的结果表）
│   └── tools/prepare_registry_map.py 可选：重建图3 汇总表
├── data/
│   ├── raw/                          原始 Excel 与 UN/LOCODE
│   ├── clean/ships_clean.csv         清洗后分析样本（4,105 × 11）
│   └── explore/
│       ├── registry_map_ready.csv    图3 专用汇总表（30 组 / 3,467 艘）
│       └── ne_110m_land.geojson      图3 底图
├── figures/                          fig01–fig04（PNG + PDF）
├── tables/                           model_results.csv、shapley_decomposition.csv
└── narrative/                        report.md、data_log.md、ai_disclosure.md
```

## 预期的结果
| 脚本 | 产物 |
|---|---|
| `01_clean.py` | `data/clean/ships_clean.csv`（4,105 行 × 11 列） |
| `02_explore.py` | `figures/fig01_carbon_intensity_by_ship_type.png/.pdf`、`fig02_eexi_carbon_intensity.png/.pdf`、`fig03_registry_carbon_intensity_map.png/.pdf` |
| `03_model.py` | `tables/model_results.csv`（29 行）、`tables/shapley_decomposition.csv` |
| `plot_r2_groups.py` | `figures/fig04_r2_by_type_size.png/.pdf`、`figures/fig04_statistics.csv` |

关键数字（用于自查）：
```
最终样本量：4105 艘
M0 R²=0.0000 | M1 0.0005 | M2 0.2106 | M3 0.4595 | M4 0.4645
EEXI 系数 2.5256（HC3 SE 0.0714，p≈0）
分船型 R²：集装箱 0.6233 / 油船 0.4553 / 散货 0.0364
Shapley：Size 0.0188 + Type 0.0938 + EEXI 0.3470 = 0.4595
```

## 核心结论（三句话）
1. EEXI 单独解释 41.28%；控制规模与船型后增量 24.89 个百分点；Shapley 贡献 0.3470，占已解释方差的 **75.5%**。
2. 分船型 R²：集装箱 **0.6233** / 油船 **0.4553** / 散货 **0.0364**，解释力存在显著船型异质性。
3. 排放规模单独几乎不解释（R²=**0.0005**）；EEXI 系数在 7 项稳健性检验中稳定在 **2.48–2.65**，Cook's D 剔除后仅变化 **−0.13%**。

## 已知的问题
1. 仅 2023 年单年横截面，无法分析年度变化趋势，也不能做因果推断。
2. 无航速、航线、载货率等运营变量，只能做相关性分析。
3. 仅覆盖挂靠欧盟港口、且有 EEXI 的船舶，不能代表全球船队。
4. 无真实 DWT/GT，只能用年度总 CO₂ 代理规模；且 `total_co2` 与 Y 存在机械关联（Y 的分子即 CO₂）。
5. EEXI 覆盖率仅 55.6%（散货 47.0%、油船 51.3%），存在样本选择。
6. 按船型聚类仅 3 个 cluster，聚类稳健标准误不可靠，主结果以 HC3 为准。
7. 油船大船组存在杠杆值 0.632 的强影响点，HC3 下不显著，不宜强解读。
8. 图3 为注册地口径，不代表航行或排放位置，且仅覆盖 3,467 艘。

## 变量与口径
| 变量 | 含义 | 单位 | 角色 |
|---|---|---|---|
| `co2_intensity_winsor` | 船型内 1%/99% 缩尾后的年度平均碳强度 | gCO₂/(t·nm) | 因变量 Y |
| `eexi_value` | EEXI 设计能效 | gCO₂/(t·nm) | 核心自变量 X |
| `total_co2` | 年度总 CO₂ 排放 | 千吨 | 规模控制（排放规模代理，不是 DWT/GT） |
| `ship_type` | 船型 | — | 固定效应 / 分组 |
| `size_group` | 全样本 total_co2 三分位 | — | 仅满足规范，与船型高度混淆 |
| `size_group_within_type` | 船型内 total_co2 三分位 | — | 异质性分析主用 |
