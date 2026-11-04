"""可选脚本：仅在重建地图表时运行。

从 data/clean/ships_clean.csv 与 data/raw/thrtis_mrv_2023.xlsx 提取注册港，
结合 data/raw/unlocode/unlocode_latest.zip 的坐标，生成
data/explore/registry_map_ready.csv（图3 的输入）。
日常复现图3 不需要运行本脚本。
"""
from pathlib import Path
import hashlib
import io
import json
import re
import unicodedata
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data' / 'explore'
SOURCE = ROOT / 'data' / 'raw' / 'unlocode' / 'unlocode_latest.zip'
SOURCE_URL = 'https://unlocode.unece.org/downloads/unlocode-latest.zip'
ACCESS_DATE = '2026-11-02'
MIN_N = 20
OUT.mkdir(parents=True, exist_ok=True)
if not SOURCE.exists():
    raise FileNotFoundError(
        f'未找到 UN/LOCODE 数据：{SOURCE}\n'
        f'请下载 {SOURCE_URL} 并保存到该路径后重试。'
    )

def normalize(value):
    if pd.isna(value):
        return ''
    return ' '.join(unicodedata.normalize('NFKC', str(value)).split()).upper()

# 显式映射常见注册港及其同名、拼写变体，不对未核实名称进行模糊定位。
# Madeira注册地使用Funchal代表点，单独标记，不等同于实际航行地点。
specs = [
    ('Monrovia','LRMLW','Liberia',['MONROVIA','MONROVIA, LIBERIA','MONRUVIA']),
    ('Majuro','MHMAJ','Marshall Islands',['MAJURO','MAJURO, MARSHALL ISLANDS']),
    ('Panama City','PAPTY','Panama',['PANAMA','PANAMA, CIUDAD DE','PANAMA CITY']),
    ('Valletta','MTMLA','Malta',['VALLETTA','VALETTA','VALLETA','LA VALLETTA','VELLETTA','VALLLETTA']),
    ('Hong Kong','HKHKG','China (Hong Kong)',['HONG KONG','HONG KONG, CHINA','HONG KONG,CHINA','HONGKONG']),
    ('Madeira','PTFNC','Portugal',['MADEIRA']),
    ('Funchal','PTFNC','Portugal',['FUNCHAL','FUNCHAL, MADEIRA']),
    ('Singapore','SGSIN','Singapore',['SINGAPORE']),
    ('Nassau','BSNAS','Bahamas',['NASSAU','NASSAU, BAHAMAS']),
    ('Limassol','CYLMS','Cyprus',['LIMASSOL']),
    ('Piraeus','GRPIR','Greece',['PIRAEUS']),
    ('Hamburg','DEHAM','Germany',['HAMBURG']),
    ('Bridgetown','BBBGI','Barbados',['BRIDGETOWN','BRIDGE TOWN']),
    ('Bergen','NOBGO','Norway',['BERGEN']),
    ('Copenhagen','DKCPH','Denmark',['COPENHAGEN','KOBENHAVN','KØBENHAVN']),
    ('Douglas','IMDGS','Isle of Man',['DOUGLAS']),
    ('Istanbul','TRIST','Türkiye',['ISTANBUL','İSTANBUL']),
    ('Egersund','NOEGE','Norway',['EGERSUND','ERGESUND']),
    ('Izmir','TRIZM','Türkiye',['IZMIR']),
    ('Mumbai','INBOM','India',['MUMBAI']),
    ('Guangzhou','CNCAN','China',['GUANGZHOU']),
    ('Marseille','FRMRS','France',['MARSEILLE']),
    ('Harlingen','NLHAR','Netherlands',['HARLINGEN']),
    ('Shanghai','CNSHA','China',['SHANGHAI','SHANG HAI']),
    ('Gibraltar','GIGIB','Gibraltar',['GIBRALTAR']),
    ('Norfolk','USORF','United States',['NORFOLK','NORFOLK, VA']),
    ('Hellerup','DKHLP','Denmark',['HELLERUP']),
    ('Stavanger','NOSTV','Norway',['STAVANGER']),
    ('Rio de Janeiro','BRRIO','Brazil',['RIO DE JANEIRO']),
    ('Tianjin','CNTSN','China',['TIANJIN','TANJIN']),
    ('Rotterdam','NLRTM','Netherlands',['ROTTERDAM']),
    ('Antwerp','BEANR','Belgium',['ANTWERP','ANTWERPEN']),
    ('London','GBLON','United Kingdom',['LONDON']),
    ('Helsinki','FIHEL','Finland',['HELSINKI']),
]

z = zipfile.ZipFile(SOURCE)
parts = [pd.read_csv(io.BytesIO(z.read(name)), header=None, dtype=str,
                     keep_default_na=False, encoding='utf-8-sig')
         for name in z.namelist() if re.search(r'CodeListPart[123]\.csv$', name)]
locodes = pd.concat(parts, ignore_index=True)
locodes['code'] = locodes[1] + locodes[2]

def get_coordinate(code):
    rows = locodes.loc[locodes['code'].eq(code) & ~locodes[0].eq('X')]
    candidates = rows.loc[rows[10].str.match(r'^\d{4}[NS] \d{5}[EW]$')]
    unique = candidates[10].unique()
    if len(unique) != 1:
        return None
    coordinate = unique[0]
    match = re.fullmatch(r'(\d{2})(\d{2})([NS]) (\d{3})(\d{2})([EW])', coordinate)
    a,b,ns,c,d,ew = match.groups()
    lat = (int(a)+int(b)/60) * (-1 if ns == 'S' else 1)
    lon = (int(c)+int(d)/60) * (-1 if ew == 'W' else 1)
    return lat, lon, coordinate

mapping = {}
for label,code,country,aliases in specs:
    coordinates = get_coordinate(code)
    url = SOURCE_URL
    note = 'UN/LOCODE地点代表坐标；非船舶位置、非排放发生地'
    if label == 'Bridgetown' and coordinates is None:
        coordinates = (13+6.95/60, -(59+38.2/60), '13°06.95 N; 59°38.2 W')
        url = 'https://barbadosport.com/marine-services/'
        note = 'Barbados Port Inc.公布的Bridgetown港坐标'
    if label == 'Madeira':
        note = ('Madeira为注册地区，使用Funchal坐标作示意代表点；'
                '不是精确注册港坐标，不使用葡萄牙大陆同名地点。'
                '依据：https://www.ibc-madeira.com/images/pdf/en-05-ORD_715_89.pdf')
    for alias in aliases:
        mapping[normalize(alias)] = {
            'registry_port_standard': label,
            'registry_country_or_area': country,
            'coordinate_locode': code,
            'latitude': coordinates[0] if coordinates else None,
            'longitude': coordinates[1] if coordinates else None,
            'coordinate_original': coordinates[2] if coordinates else '',
            'coordinate_source': url if coordinates else '',
            'coordinate_access_date': ACCESS_DATE if coordinates else '',
            'geocode_status': ('representative_point' if label == 'Madeira'
                               else 'matched') if coordinates else 'coordinate_missing',
            'coordinate_note': note,
        }

CLEAN_FILE = ROOT / 'data' / 'clean' / 'ships_clean.csv'
RAW_FILE = ROOT / 'data' / 'raw' / 'thrtis_mrv_2023.xlsx'
if not CLEAN_FILE.exists():
    raise FileNotFoundError(f'未找到 {CLEAN_FILE}，请先运行 python analysis/01_clean.py')
clean = pd.read_csv(CLEAN_FILE, encoding='utf-8-sig')
raw_header = pd.read_excel(RAW_FILE, sheet_name='2023', header=2, nrows=0)
imo_col = next(c for c in raw_header.columns if str(c).startswith('IMO Number'))
port_col = next(c for c in raw_header.columns if str(c).startswith('Port of Registry'))
raw = pd.read_excel(RAW_FILE, sheet_name='2023', header=2, usecols=[imo_col, port_col])
raw = raw.rename(columns={imo_col: 'IMO Number', port_col: 'Port of Registry'})
merged = clean.merge(raw, left_on='imo', right_on='IMO Number', how='left',
                     validate='one_to_one', indicator=True)
assert merged['_merge'].eq('both').all()
merged = merged.drop(columns=['IMO Number','_merge']).rename(columns={'Port of Registry':'registry_port_raw'})
merged['registry_port_key'] = merged['registry_port_raw'].map(normalize)

lookup_rows = []
for raw_name, count in merged['registry_port_raw'].fillna('').value_counts().items():
    key = normalize(raw_name)
    row = mapping.get(key, {
        'registry_port_standard': key,
        'registry_country_or_area': '', 'coordinate_locode': '',
        'latitude': None, 'longitude': None, 'coordinate_original': '',
        'coordinate_source': '', 'coordinate_access_date': '',
        'geocode_status': 'missing_registry' if not key else 'pending_review',
        'coordinate_note': '原始注册港缺失' if not key else '尚未核实，不自动模糊匹配或猜测坐标',
    })
    lookup_rows.append({'registry_port_raw':raw_name,'registry_port_key':key,
                        'ship_count':int(count), **row})
lookup = pd.DataFrame(lookup_rows)
keys = lookup.drop_duplicates('registry_port_key').drop(columns=['registry_port_raw','ship_count'])
extended = merged.merge(keys, on='registry_port_key', how='left', validate='many_to_one')
assert len(extended) == len(clean)
pd.testing.assert_frame_equal(extended[clean.columns].reset_index(drop=True), clean.reset_index(drop=True))

group_cols = ['ship_type','registry_port_standard']
summary = extended.groupby(group_cols,dropna=False).agg(
    ship_count=('imo','size'),
    co2_intensity_median=('co2_intensity_winsor','median'),
    co2_intensity_mean=('co2_intensity_winsor','mean'),
    co2_intensity_q1=('co2_intensity_winsor',lambda x:x.quantile(.25)),
    co2_intensity_q3=('co2_intensity_winsor',lambda x:x.quantile(.75)),
    eexi_median=('eexi_value','median'),
    latitude=('latitude','first'), longitude=('longitude','first'),
    registry_country_or_area=('registry_country_or_area','first'),
    geocode_status=('geocode_status','first'),
    coordinate_source=('coordinate_source','first'),
    coordinate_note=('coordinate_note','first'),
).reset_index()
summary['co2_intensity_iqr'] = summary.co2_intensity_q3-summary.co2_intensity_q1
summary['map_eligible'] = summary.ship_count.ge(MIN_N) & summary.latitude.notna() & summary.longitude.notna()
ready = summary.loc[summary.map_eligible].copy()
pending = lookup.loc[~lookup.geocode_status.isin(['matched','representative_point'])].copy()

files = {'ships_with_registry.csv':extended, 'registry_port_lookup.csv':lookup,
         'registry_shiptype_summary.csv':summary,'registry_map_ready.csv':ready,
         'registry_pending_review.csv':pending}
for name,frame in files.items():
    frame.to_csv(OUT/name,index=False,encoding='utf-8-sig',float_format='%.8f')
    check = pd.read_csv(OUT/name,encoding='utf-8-sig')
    assert len(check) == len(frame)

report = {
    'ship_count':len(extended),
    'registry_missing':int(extended.registry_port_key.eq('').sum()),
    'coordinate_covered_ships':int(extended.latitude.notna().sum()),
    'pending_nonmissing_ships':int((extended.geocode_status.eq('pending_review')|extended.geocode_status.eq('coordinate_missing')).sum()),
    'ready_groups':len(ready),'ready_ships':int(ready.ship_count.sum()),
    'min_group_n':MIN_N,
    'source_zip_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
}
(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
print(ready.groupby('ship_type').ship_count.agg(['size','sum']).to_string())
