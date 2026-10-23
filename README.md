# 03 红海绕航对亚欧航线的影响

## 一句话
（这个项目回答什么问题？一句话，不超过 40 字）

## 怎样运行
1. 环境：按课程网站《环境配置》页面安装本地开发环境（Python 3.12、pandas、matplotlib）
2. 把原始数据放进 data/raw/（文件清单见下）
3. 依次运行：
   - python analysis/01_clean.py    → 生成 data/clean/voyages.csv
   - python analysis/02_explore.py  → 生成 figures/fig1.png 至 fig3.png
   - python analysis/03_model.py    → 打印表 3 的四个数字

## 数据从哪里来
| 文件 | 来源 | 性质 | 下载日期 |
|---|---|---|---|
| portwatch_2024.csv | （填写） | 〔官〕/〔独〕/〔商〕 | （填写） |

## 预期的结果
（运行之后屏幕上应当出现什么？给出一两行示例输出，便于助教对照）

## 已知的问题
（哪些地方还不完善，哪些结论只在什么条件下成立；如实写出不扣分）