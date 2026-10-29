# 2023 年挂靠欧盟港口的集装箱船中，同型船内部的碳强度差异有多大？EEXI 设计能效能解释其中多少比例？

## 研究问题
1. EEXI设计能效能解释多少比例的集装箱船运营碳强度差异？
2. 不同规模（按总CO₂排放量分组）的集装箱船中，EEXI的解释力是否存在差异？

## 数据来源
- 数据平台：EMSA THETIS-MRV（欧盟船舶碳排放监测、报告与核查数据库）
- 下载地址：https://www.emsa.europa.eu/
- 数据年份：2023年
- 原始文件：`data/raw/thrtis_mrv_2023.xlsx`
- 筛选后样本：1480艘有EEXI认证的集装箱船

## 项目结构
MRV_dazuoye/
├── data/
│   ├── raw/                # 原始数据（不进 git）
│   │   └── thrtis_mrv_2023.xlsx
│   └── clean/              # 清洗后数据
│       └── container_clean.csv
├── analysis/               # 分析代码
│   ├── 01_clean.py         # 数据清洗脚本
│   ├── 02_explore.py       # 探索性分析与可视化
│   └── 03_model.py         # 回归模型与 R² 分解
├── figures/                # 输出图表
├── tables/                 # 输出表格
├── narrative/              # 报告与文档
│   ├── report.md           # 课程报告正文
│   └── data_log        # 数据清洗日志
└── README.md

## 环境配置
- Python 3.12
- 虚拟环境：conda activate shipping
- 依赖包：pandas, openpyxl, scikit-learn, matplotlib

## 复现步骤
```bash
# 1. 激活环境
conda activate shipping

# 2. 运行数据清洗
python analysis/01_clean.py

# 3. 运行探索性分析
python analysis/02_explore.py

# 4. 运行回归模型
python analysis/03_model.py
