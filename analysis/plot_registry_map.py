# -*- coding: utf-8 -*-
"""图3：按船型分面的注册地运营碳强度地图。可直接在Jupyter运行。"""
from pathlib import Path
import json
import urllib.request
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import Normalize
from matplotlib.patches import Polygon

# 修改此处可将整个项目放到其他文件夹。
PROJECT_ROOT = (Path(__file__).resolve().parents[1] if '__file__' in globals()
                else Path.cwd())
INPUT_FILE = PROJECT_ROOT / 'data' / 'explore' / 'registry_map_ready.csv'
LAND_FILE = PROJECT_ROOT / 'data' / 'explore' / 'ne_110m_land.geojson'
OUTPUT_DIR = Path(globals().get('FIGURES_DIR', PROJECT_ROOT / 'figures'))
LAND_URL = ('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/'
            'master/geojson/ne_110m_land.geojson')
MIN_GROUP_N = 20
# scatter的s是点面积，面积与船舶数量成正比；主图与局部图完全相同。
AREA_PER_SHIP = 1.5
SHIP_TYPES = ['Container ship', 'Bulk carrier', 'Oil tanker']
SHIP_LABELS = ['集装箱船', '散货船', '油船']

# 字体中不直接使用下标字符，CO2下标由数学公式渲染。
installed = {font.name for font in font_manager.fontManager.ttflist}
CJK_FONTS = ['Microsoft YaHei', 'SimHei', 'PingFang SC', 'Hiragino Sans GB',
             'Heiti SC', 'Arial Unicode MS', 'Noto Sans CJK SC',
             'Source Han Sans SC', 'WenQuanYi Zen Hei']
font = next((name for name in CJK_FONTS if name in installed), None)
if font is None:
    print('[警告] 未找到中文字体，中文可能显示为方块；建议安装 Noto Sans CJK SC。')
    font = 'DejaVu Sans'
plt.rcParams.update({'font.sans-serif': [font, 'DejaVu Sans'],
                     'axes.unicode_minus': False, 'font.size': 10,
                     'pdf.fonttype': 42})

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f'未找到地图数据：{INPUT_FILE}\n'
        f'该文件应随仓库提供；如需重建，请运行 '
        f'python analysis/tools/prepare_registry_map.py'
    )
data = pd.read_csv(INPUT_FILE, encoding='utf-8-sig')
required = {'ship_type', 'registry_port_standard', 'ship_count',
            'co2_intensity_median', 'latitude', 'longitude'}
if not required.issubset(data.columns):
    raise ValueError(f'缺少字段：{sorted(required-set(data.columns))}')
for column in ['ship_count', 'co2_intensity_median', 'latitude', 'longitude']:
    data[column] = pd.to_numeric(data[column], errors='raise')
    if not np.isfinite(data[column]).all():
        raise ValueError(f'{column}存在缺失值或无穷值。')
if not data.latitude.between(-90, 90).all() or not data.longitude.between(-180, 180).all():
    raise ValueError('经纬度超出有效范围。')
if not data.ship_count.ge(MIN_GROUP_N).all():
    raise ValueError('绘图表包含不足20艘的分组，请检查输入文件。')
if data.duplicated(['ship_type', 'registry_port_standard']).any():
    raise ValueError('绘图数据存在重复的船型与注册港组合。')
if not data.ship_type.isin(SHIP_TYPES).all():
    raise ValueError('存在选题以外的船型。')

# 已随本项目缓存底图；换电脑时若没有缓存，首次运行会下载。
if not LAND_FILE.exists():
    LAND_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(LAND_URL, timeout=45) as response:
            land_bytes = response.read()
        json.loads(land_bytes)
        LAND_FILE.write_bytes(land_bytes)
        print(f'已下载底图：{LAND_FILE}')
    except Exception as exc:
        raise RuntimeError(
            f'底图缺失且下载失败：{exc}\n'
            f'请手动下载 {LAND_URL} 并保存为 {LAND_FILE}'
        ) from exc
land = json.loads(LAND_FILE.read_text(encoding='utf-8'))

# 三种船型共用同一个连续色标，不能各自按最小最大值着色。
vmin = float(np.floor(data.co2_intensity_median.min()/5)*5)
vmax = float(np.ceil(data.co2_intensity_median.max()/5)*5)
if vmax == vmin:
    vmax = vmin+5
norm = Normalize(vmin=vmin, vmax=vmax)
cmap = plt.get_cmap('viridis')

port_labels = {
    'Monrovia': '蒙罗维亚', 'Majuro': '马朱罗', 'Panama City': '巴拿马城',
    'Hong Kong': '香港', 'Singapore': '新加坡', 'Nassau': '拿骚',
    'Bridgetown': '布里奇敦', 'Madeira': '马德拉*', 'Valletta': '瓦莱塔',
    'Copenhagen': '哥本哈根', 'Hamburg': '汉堡', 'Limassol': '利马索尔',
    'Piraeus': '比雷埃夫斯', 'Douglas': '道格拉斯',
}
# 标签只作偏移，不改变圆点的真实坐标。
offsets = {
    'Monrovia': (8, -15), 'Majuro': (-10, 10), 'Panama City': (-8, -16),
    'Hong Kong': (7, 8), 'Singapore': (7, -13), 'Nassau': (-8, 10),
    'Bridgetown': (8, -10), 'Madeira': (8, -13), 'Valletta': (-8, -18),
    'Copenhagen': (7, 10), 'Hamburg': (-7, -16), 'Limassol': (7, -5),
    'Piraeus': (-7, 10), 'Douglas': (7, 8),
}

fig, axes = plt.subplots(3, 2, figsize=(17, 12),
                          gridspec_kw={'width_ratios': [2.35, 1]})
fig.subplots_adjust(left=.045, right=.89, bottom=.14, top=.91,
                    wspace=.12, hspace=.28)

for row, (ship_type, ship_label) in enumerate(zip(SHIP_TYPES, SHIP_LABELS)):
    group = data.loc[data.ship_type.eq(ship_type)].copy()
    if group.empty:
        raise ValueError(f'{ship_label}没有可绘图分组。')
    for col in [0, 1]:
        ax = axes[row, col]
        ax.set_facecolor('#F3F8FB')
        for feature in land['features']:
            geometry = feature['geometry']
            polygons = ([geometry['coordinates']] if geometry['type'] == 'Polygon'
                        else geometry['coordinates'])
            for polygon in polygons:
                # 底图仅绘制陆地外轮廓，不涉及行政边界。
                ax.add_patch(Polygon(np.asarray(polygon[0]), closed=True,
                    facecolor='#E3E6E7', edgecolor='#ADB5B9', linewidth=.35,
                    zorder=1))

        # 大圆点先画，小圆点后画，减少小组被遮挡。
        plotted = group.sort_values('ship_count', ascending=False)
        ax.scatter(plotted.longitude, plotted.latitude,
            s=plotted.ship_count*AREA_PER_SHIP,
            c=plotted.co2_intensity_median, cmap=cmap, norm=norm,
            edgecolors='#202A35', linewidths=.65, alpha=.95, zorder=4)
        if col == 0:
            ax.set_xlim(-180, 180)
            ax.set_ylim(-55, 75)
            ax.set_xticks([-180,-120,-60,0,60,120,180])
            ax.set_yticks([-30,0,30,60])
            ax.set_title(f'{ship_label}｜{len(group)}个注册地，'
                         f'{int(group.ship_count.sum()):,}艘',
                         loc='left', fontsize=13, pad=9)
            # 欧洲及马德拉标签放到右侧局部图，避免主图拥挤。
            visible = group.loc[~(group.longitude.between(-25,45)
                                    & group.latitude.between(28,65))]
        else:
            ax.set_xlim(-25,45)
            ax.set_ylim(28,65)
            ax.set_xticks([-20,0,20,40])
            ax.set_yticks([30,40,50,60])
            ax.set_title('欧洲及东北大西洋局部', loc='left', fontsize=11, pad=9)
            visible = group.loc[group.longitude.between(-25,45)
                                 & group.latitude.between(28,65)]
        for record in visible.to_dict('records'):
            name = record['registry_port_standard']
            dx,dy = offsets.get(name,(7,7))
            ax.annotate(port_labels.get(name,name),
                (record['longitude'],record['latitude']),
                xytext=(dx,dy), textcoords='offset points',
                ha='right' if dx < 0 else 'left', fontsize=8.5,
                arrowprops={'arrowstyle':'-', 'color':'#697780','lw':.5},
                zorder=5)
        ax.set_aspect('equal', adjustable='box')
        ax.set_axisbelow(True)
        ax.grid(color='#D7E0E5', linewidth=.45)
        ax.tick_params(labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#BAC4CB')

fig.suptitle('图3  2023年不同船型船舶的注册地与运营碳强度',
             x=.045, ha='left', y=.975, fontsize=18, fontweight='bold')
fig.text(.045,.938,'颜色：组内运营碳强度中位数    圆点面积：船舶数量    '
         '各船型共用色标和面积比例', fontsize=11, color='#475569')

# 共享色标，明确显示碳强度单位。
cax = fig.add_axes([.92,.31,.014,.40])
colorbar = fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax)
colorbar.set_label(r'运营碳强度中位数 [g CO$_2$/(t·n mile)]', fontsize=11)

# 图例中的圆点面积与地图实际面积一致。
handles = [axes[0,0].scatter([],[],s=n*AREA_PER_SHIP,
             facecolor='#AAB4BE',edgecolor='#202A35',linewidth=.65)
           for n in [20,100,400]]
fig.legend(handles,['20艘','100艘','400艘'],title='船舶数量',
           loc='lower left',bbox_to_anchor=(.91,.13),frameon=False,
           labelspacing=1.8,borderaxespad=0)

fig.text(.045,.085,
    f'注：仅展示同一船型、同一注册地至少20艘且有坐标的组合，'
    f'共{len(data)}组、{int(data.ship_count.sum()):,}艘；'
    '运营碳强度已按船型进行1%和99%分位缩尾。\n'
    '* 马德拉使用Funchal代表点。右侧为左侧部分地点的重复放大展示，样本不重复计数。\n'
    '坐标表示注册地，不代表航行或排放位置；底图为等经纬度示意，坐标轴单位为度。',
    fontsize=9,color='#475569',linespacing=1.7,va='top')

OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
for extension in ['png','pdf']:
    path = OUTPUT_DIR / f'fig03_registry_carbon_intensity_map.{extension}'
    fig.savefig(path,dpi=300,bbox_inches='tight',facecolor='white')
    print(f'已保存：{path}')
if not globals().get('BATCH_MODE', False):
    plt.show()
plt.close(fig)
