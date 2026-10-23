# 03 MRV 2023：同型集装箱船的碳强度差异与船龄解释力

一句话：用 2023 年 THETIS-MRV 单年截面，比较四个 TEU 档内部的碳强度差异，
并估计船龄能解释其中多少比例的变异（与“只用 TEU 档均值”的基线对比）。

## 1 怎样运行
- 环境：Python 3.12（Miniforge 的 shipping 环境）+ pandas / numpy / matplotlib / openpyxl
- 把 2023 年导出放进 data/raw/（不改名、不编辑），然后：python analysis/run_all.py
- 全部产物：data/clean/、figures/、tables/；删掉它们也能由脚本重建。

## 2 数据从哪里来
| 文件 | 来源 | 报告期 | 下载日期 | 大小 | SHA256 前 12 位 |
| mrv_2023.xlsx | THETIS-MRV 公开报告 | 2023 | [日期] | [大小] | [前 12 位] |
筛选后 n = [ ]；四个 TEU 档：[ ]/[ ]/[ ]/[ ]；船龄覆盖率 [ ]%（来源：Equasis 人工检索）

## 3 口径
碳强度 I2 = CO2(t) x 1e6 / (DWT x 距离)，单位 g CO2/(t·nm)；船龄 = 2023 - 建造年；
同型 = 同一报告年 + 集装箱船 + 同一 TEU 档。

## 4 预期结果
fig1–fig6 与 tables/desc_2023.csv、model_2023.csv；关键数字：
R2_base = [ ]；R2_full = [ ]；dR2 = [ ]；船龄系数 = [ ]（95% 区间 [ ] ~ [ ]）。
落在三种情形中的第 [A/B/C] 类，理由见报告 4.5。

## 5 已知问题
- TEU 缺失时用 GT 代理分组（局限第 6 条）；
- 未控制载货率与航线明细（公开版无此字段）；
- 船龄为人工检索，覆盖率 [ ]%，按整年计，误差 ±1 年。