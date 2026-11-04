# -*- coding: utf-8 -*-
"""生成图1（分布）、图2（关系）与图3（注册地地图）；从任意工作目录运行均可。

命令：python analysis/02_explore.py
输入：data/clean/ships_clean.csv、data/explore/registry_map_ready.csv
输出：figures/fig01-fig03 的 PNG/PDF 与统计表
不修改输入数据，不在绘图阶段再次缩尾或删除船舶。
"""
from pathlib import Path
import argparse
import runpy
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', type=Path, default=ROOT/'figures')
args = parser.parse_args()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)
CLEAN = ROOT/'data/clean/ships_clean.csv'
TYPES = ['Container ship','Bulk carrier','Oil tanker']
LABELS = ['集装箱船','散货船','油船']
COLORS = ['#4477AA','#228833','#EE9944']

installed = {f.name for f in font_manager.fontManager.ttflist}
CJK_FONTS = ['Microsoft YaHei', 'SimHei', 'PingFang SC', 'Hiragino Sans GB',
             'Heiti SC', 'Arial Unicode MS', 'Noto Sans CJK SC',
             'Source Han Sans SC', 'WenQuanYi Zen Hei']
font = next((f for f in CJK_FONTS if f in installed), None)
if font is None:
    print('[警告] 未找到中文字体，中文可能显示为方块；建议安装 Noto Sans CJK SC。')
    font = 'DejaVu Sans'
plt.rcParams.update({'font.sans-serif':[font,'DejaVu Sans'],
                     'axes.unicode_minus':False,'pdf.fonttype':42,'font.size':11})
df = pd.read_csv(CLEAN,encoding='utf-8-sig')
required = {'imo','ship_type','report_year','co2_intensity_winsor','eexi_value','total_co2'}
if not required.issubset(df.columns):
    raise ValueError(f'缺少字段：{required-set(df.columns)}')
if not df.ship_type.isin(TYPES).all() or not df.report_year.eq(2023).all() or df.imo.duplicated().any():
    raise ValueError('船型、报告年度或IMO唯一性检查不通过。')
for column in ['co2_intensity_winsor','eexi_value','total_co2']:
    df[column] = pd.to_numeric(df[column],errors='raise')
    if not (np.isfinite(df[column]) & df[column].gt(0)).all():
        raise ValueError(f'{column}存在无效值，请检查上游清洗。')
samples = [df.loc[df.ship_type.eq(t),'co2_intensity_winsor'] for t in TYPES]
if any(len(s)<3 for s in samples):
    raise ValueError('某船型样本不足。')
print(f'读取分析样本：{len(df)}艘；船型数量：{dict(zip(LABELS,map(len,samples)))}')

def save_figure(fig,name):
    for extension in ['png','pdf']:
        fig.savefig(OUT/f'{name}.{extension}',dpi=300,bbox_inches='tight',facecolor='white')
    plt.close(fig)
    print(f'已生成：{name}.png / .pdf')

# 图1：箱线图展示分布中心、主体离散程度和高值尾部。
fig,ax = plt.subplots(figsize=(12,5.5),layout='constrained')
boxes = ax.boxplot([s.to_numpy() for s in samples],widths=.48,whis=1.5,patch_artist=True,
    medianprops={'color':'#222222','linewidth':2},
    flierprops={'marker':'o','markersize':3,'markerfacecolor':'none',
                'markeredgecolor':'#666666','alpha':.4})
distribution = []
for i,(s,label,color) in enumerate(zip(samples,LABELS,COLORS)):
    boxes['boxes'][i].set_facecolor(color)
    boxes['boxes'][i].set_alpha(.7)
    q1,median,q3 = s.quantile([.25,.5,.75]).to_numpy()
    iqr = q3-q1
    distribution.append({'船型':label,'样本量':len(s),'中位数':median,'Q1':q1,'Q3':q3,
        'IQR':iqr,'P95':s.quantile(.95),'均值':s.mean(),
        '上侧离群点比例':s.gt(q3+1.5*iqr).mean()})
    ax.annotate(f'中位数 {median:.2f}',(i+1.25,median),xytext=(6,0),
                textcoords='offset points',va='center',fontsize=10)
ax.set_xticks([1,2,3],labels=[f'{label}\nn = {len(s):,}' for label,s in zip(LABELS,samples)])
ax.set(xlim=(.5,3.8),ylim=(0,df.co2_intensity_winsor.max()*1.1))
ax.set_ylabel(r'年度运营碳强度 [g CO$_2$/(t·n mile)]')
ax.set_axisbelow(True)
ax.yaxis.grid(True,color='#E3E7EB')
ax.spines[['top','right']].set_visible(False)
save_figure(fig,'fig01_carbon_intensity_by_ship_type')
dist = pd.DataFrame(distribution)
dist.to_csv(OUT/'fig01_statistics.csv',index=False,encoding='utf-8-sig')

# 图2：同船型内部的设计指标与运营指标关系；不合并船型估计总体相关。
fig,axes = plt.subplots(1,3,figsize=(15,5),sharex=True,sharey=True,layout='constrained')
relations = []
for ax,t,label,color in zip(axes,TYPES,LABELS,COLORS):
    g = df.loc[df.ship_type.eq(t)]
    x,y = g.eexi_value,g.co2_intensity_winsor
    if x.nunique()<2 or y.nunique()<2:
        raise ValueError(f'{label}变量无足够变异。')
    r = x.corr(y)
    rho = x.rank().corr(y.rank())
    slope,intercept = np.polyfit(x,y,1)
    predicted = intercept+slope*x
    r2 = 1-((y-predicted)**2).sum()/((y-y.mean())**2).sum()
    ax.scatter(x,y,s=16,color=color,alpha=.3,edgecolors='none',rasterized=True)
    line_x = np.linspace(x.min(),x.max(),200)
    ax.plot(line_x,intercept+slope*line_x,'--',color='#222222',lw=1.6)
    ax.text(.05,.95,f'Pearson r = {r:.3f}\nSpearman ρ = {rho:.3f}',
            transform=ax.transAxes,va='top',fontsize=10)
    ax.set_title(f'{label}（n = {len(g):,}）',fontsize=13)
    ax.set_xlabel(r'EEXI [g CO$_2$/(t·n mile)]')
    ax.set_axisbelow(True)
    ax.grid(True,color='#E5E7EB',lw=.7)
    ax.spines[['top','right']].set_visible(False)
    relations.append({'船型':label,'样本量':len(g),'Pearson_r':r,'Spearman_rho':rho,
                      '一元线性拟合_R_squared':r2,'截距':intercept,'斜率':slope})
axes[0].set_ylabel(r'年度运营碳强度 [g CO$_2$/(t·n mile)]')
axes[0].set_xlim(0,df.eexi_value.max()*1.05)
axes[0].set_ylim(0,df.co2_intensity_winsor.max()*1.06)
save_figure(fig,'fig02_eexi_carbon_intensity')
rel = pd.DataFrame(relations)
rel.to_csv(OUT/'fig02_statistics.csv',index=False,encoding='utf-8-sig')
print(rel.to_string(index=False))

# 图3：直接读取仓库内已生成的 data/explore/registry_map_ready.csv，
# 不重建数据，因此不需要 UN/LOCODE zip，也不需要联网。
runpy.run_path(str(ROOT/'analysis/plot_registry_map.py'),run_name='__main__',
               init_globals={'FIGURES_DIR':OUT,'BATCH_MODE':True})
print('三张探索图已全部生成。')
