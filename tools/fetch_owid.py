# -*- coding: utf-8 -*-
"""通用 OWID grapher CSV 取数器 -> 「国家 × 年」宽表 CSV。

用法：
    python fetch_owid.py <slug> <out_name> [--start 1950] [--end 2025] [--min-year 1950]

关键坑（已修）：
- 列名首字母大写：Entity / Code / Year（小写会 KeyError）。
- 聚合体污染：OWID 数据里混着 World/Asia/High-income countries/Europe 等。
  只过滤 `Code != 'OWID_WRL'` 是不够的（Asia、Europe 的 Code 也是空值），
  必须用「Code 是 3 个大写字母的 ISO3 码」这一条硬规则，聚合体一律滤掉。
- 只写「有值的年列」，无数据年份留空（CSV 适配器按未上榜处理）。
"""
import argparse
import csv
import os
import re
import sys
import unicodedata

import pandas as pd
import requests


def _norm(s):
    """名字归一化：去重音 + 转小写 + 折叠空白，用于跨拼写变体比对。"""
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s).strip().lower()

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(WS, 'data', 'topics_csv')
# 统一中文名映射（2026-09-06 起）：entity_cn 覆盖国家/聚合体/企业 600+ 条
sys.path.insert(0, os.path.join(WS, 'scripts_local'))
try:
    import entity_cn as ENTITY_CN
except Exception:                                     # noqa: BLE001
    ENTITY_CN = None
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'}

# 微型属地 / 单一设施经济体排除名单。
# 教训：co-emissions-per-capita 首版里混进了 Sint Maarten (Dutch part)，其 1950 年
# 人均 463.7 吨（炼油厂口径）直接霸占榜首，自动生成的口播稿开口就是
# 「1950年还是Sint Maarten以463.7吨/人领跑」——叙事被噪声彻底毁掉。
# 这类微型属地在「人均/密度」类指标上系统性畸高，默认剔除。
MICRO = {
    'Sint Maarten (Dutch part)', 'Curaçao', 'Aruba', 'New Caledonia', 'Gibraltar',
    'Falkland Islands', 'Virgin Islands (U.S.)', 'Virgin Islands (British)',
    'British Virgin Islands', 'Cayman Islands', 'Bermuda', 'Greenland',
    'Faroe Islands', 'Faeroe Islands', 'Palau', 'Nauru', 'Tuvalu', 'Kiribati',
    'Marshall Islands', 'Saint Kitts and Nevis', 'Antigua and Barbuda',
    'Seychelles', 'San Marino', 'Monaco', 'Liechtenstein', 'Andorra',
    'Turks and Caicos Islands', 'Anguilla', 'Montserrat',
    'Saint Pierre and Miquelon', 'Wallis and Futuna', 'French Polynesia',
    'Guam', 'American Samoa', 'Northern Mariana Islands', 'Tokelau', 'Niue',
    'Cook Islands', 'Saint Helena', 'Saint Barthelemy', 'Isle of Man',
    'Jersey', 'Guernsey',
}
# 注：新加坡、巴林、马耳他等「城市型主权国家」虽数值也偏高，但它们是主权国家、
# 观众有认知，予以保留——剔除只针对无独立主权的属地与微型岛国。

# OWID 英文名 -> 中文名（只映射榜单常客，未命中的保留英文）
CN = {
    'China': '中国', 'United States': '美国', 'India': '印度', 'Japan': '日本',
    'Russia': '俄罗斯', 'Germany': '德国', 'Brazil': '巴西', 'Indonesia': '印度尼西亚',
    'Iran': '伊朗', 'South Korea': '韩国', 'Saudi Arabia': '沙特阿拉伯',
    'Canada': '加拿大', 'Mexico': '墨西哥', 'South Africa': '南非', 'Turkey': '土耳其',
    'Australia': '澳大利亚', 'United Kingdom': '英国', 'Italy': '意大利',
    'France': '法国', 'Poland': '波兰', 'Kazakhstan': '哈萨克斯坦',
    'Ukraine': '乌克兰', 'Thailand': '泰国', 'Vietnam': '越南', 'Egypt': '埃及',
    'Pakistan': '巴基斯坦', 'Argentina': '阿根廷', 'Netherlands': '荷兰',
    'Spain': '西班牙', 'Malaysia': '马来西亚', 'Nigeria': '尼日利亚',
    'Uzbekistan': '乌兹别克斯坦', 'Norway': '挪威', 'Qatar': '卡塔尔',
    'United Arab Emirates': '阿联酋', 'Iraq': '伊拉克', 'Kuwait': '科威特',
    'Algeria': '阿尔及利亚', 'Venezuela': '委内瑞拉', 'Libya': '利比亚',
    'Oman': '阿曼', 'Turkmenistan': '土库曼斯坦', 'Bangladesh': '孟加拉国',
    'Philippines': '菲律宾', 'Colombia': '哥伦比亚', 'Chile': '智利',
    'Czechia': '捷克', 'Belgium': '比利时', 'Sweden': '瑞典', 'Austria': '奥地利',
    'Switzerland': '瑞士', 'Romania': '罗马尼亚', 'Greece': '希腊',
    'Portugal': '葡萄牙', 'Hungary': '匈牙利', 'Serbia': '塞尔维亚',
    'Bulgaria': '保加利亚', 'Belarus': '白俄罗斯', 'Finland': '芬兰',
    'Denmark': '丹麦', 'Ireland': '爱尔兰', 'New Zealand': '新西兰',
    'Israel': '以色列', 'Singapore': '新加坡', 'Hong Kong': '中国香港',
    'Taiwan': '中国台湾', 'Mongolia': '蒙古', 'Myanmar': '缅甸',
    'Sri Lanka': '斯里兰卡', 'Nepal': '尼泊尔', 'Peru': '秘鲁', 'Morocco': '摩洛哥',
    'Angola': '安哥拉', 'Ethiopia': '埃塞俄比亚', 'Kenya': '肯尼亚',
    'Ghana': '加纳', 'Tanzania': '坦桑尼亚', 'Sudan': '苏丹', 'Zimbabwe': '津巴布韦',
    'Mozambique': '莫桑比克', 'Zambia': '赞比亚', 'Botswana': '博茨瓦纳',
    'Namibia': '纳米比亚', 'Ecuador': '厄瓜多尔', 'Bolivia': '玻利维亚',
    'Paraguay': '巴拉圭', 'Uruguay': '乌拉圭', 'Cuba': '古巴', 'Jordan': '约旦',
    'Lebanon': '黎巴嫩', 'Syria': '叙利亚', 'Tunisia': '突尼斯', 'Azerbaijan': '阿塞拜疆',
    'Slovakia': '斯洛伐克', 'Slovenia': '斯洛文尼亚', 'Croatia': '克罗地亚',
    'Bosnia and Herzegovina': '波黑', 'Lithuania': '立陶宛', 'Latvia': '拉脱维亚',
    'Estonia': '爱沙尼亚', 'Iceland': '冰岛', 'Luxembourg': '卢森堡',
    'Kyrgyzstan': '吉尔吉斯斯坦', 'Tajikistan': '塔吉克斯坦', 'Armenia': '亚美尼亚',
    'Georgia': '格鲁吉亚', 'Cambodia': '柬埔寨', 'Laos': '老挝', 'Brunei': '文莱',
    'Papua New Guinea': '巴布亚新几内亚', 'Trinidad and Tobago': '特立尼达和多巴哥',
    'Bahrain': '巴林', 'Cyprus': '塞浦路斯', 'Malta': '马耳他', 'Jamaica': '牙买加',
    'Albania': '阿尔巴尼亚', 'North Macedonia': '北马其顿', 'Moldova': '摩尔多瓦',
    'Montenegro': '黑山', 'Congo': '刚果（金）', 'Democratic Republic of Congo': '刚果（金）',
    'Congo, Dem. Rep.': '刚果（金）', 'Congo, Rep.': '刚果（布）',
    'Ivory Coast': '科特迪瓦', "Cote d'Ivoire": '科特迪瓦', 'Cameroon': '喀麦隆',
    'Uganda': '乌干达', 'Senegal': '塞内加尔', 'Mali': '马里', 'Niger': '尼日尔',
    'Chad': '乍得', 'Somalia': '索马里', 'Rwanda': '卢旺达', 'Benin': '贝宁',
    'Burkina Faso': '布基纳法索', 'Guinea': '几内亚', 'Madagascar': '马达加斯加',
    'Malawi': '马拉维', 'Afghanistan': '阿富汗', 'Yemen': '也门',
    'North Korea': '朝鲜', 'South Sudan': '南苏丹', 'Eritrea': '厄立特里亚',
    'Mauritania': '毛里塔尼亚', 'Gabon': '加蓬', 'Equatorial Guinea': '赤道几内亚',
    'Suriname': '苏里南', 'Guyana': '圭亚那', 'Honduras': '洪都拉斯',
    'Guatemala': '危地马拉', 'Costa Rica': '哥斯达黎加', 'Panama': '巴拿马',
    'Dominican Republic': '多米尼加', 'Haiti': '海地', 'Nicaragua': '尼加拉瓜',
    'El Salvador': '萨尔瓦多', 'Timor': '东帝汶', 'East Timor': '东帝汶',
    'Fiji': '斐济', 'Bhutan': '不丹', 'Maldives': '马尔代夫', 'Bahrain ': '巴林',
    'Palestine': '巴勒斯坦', 'West Bank and Gaza': '巴勒斯坦',
}


def fetch(slug):
    url = f'https://ourworldindata.org/grapher/{slug}.csv?v=1&csvType=full'
    r = requests.get(url, headers=H, timeout=120)
    r.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(r.text))


def to_cn(ent):
    """实体英文名 -> 中文显示名。优先用 entity_cn（覆盖 600+ 实体），
    漏网的再回退到本文件的 CN 表，最后保留英文原名。"""
    if ENTITY_CN is not None:
        got = ENTITY_CN.cn_name(ent)
        if got != ent:
            return got
    return CN.get(ent, CN.get(ent.strip(), ent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('slug')
    ap.add_argument('out')
    ap.add_argument('--start', type=int, default=1950)
    ap.add_argument('--end', type=int, default=2025)
    ap.add_argument('--value-col', default=None,
                    help='数值列名；不传则取 Entity/Code/Year 之外的第一列')
    ap.add_argument('--min-cov', type=float, default=0.70,
                    help='末年覆盖率下限（0-1）；不达标则自动往回退年，防止末帧大面积掉柱')
    ap.add_argument('--keep-micro', action='store_true',
                    help='保留微型属地（默认剔除，见 MICRO 名单说明）')
    a = ap.parse_args()

    df = fetch(a.slug)
    cols = list(df.columns)
    if a.value_col and a.value_col in cols:
        vcol = a.value_col
    else:
        vcol = [c for c in cols if c not in ('Entity', 'Code', 'Year')][0]
    print(f'[{a.slug}] 列={cols} 数值列={vcol} 原始行数={len(df)}')

    # 硬过滤：只保留 ISO3 三字母码的真实国家（滤掉 World/Asia/Europe/OWID_* 等聚合体）
    before = len(df)
    df = df[df['Code'].notna() & df['Code'].astype(str).str.fullmatch(r'[A-Z]{3}')]
    print(f'  聚合体过滤：{before} -> {len(df)} 行（去掉 {before - len(df)}）')

    if not a.keep_micro:
        # 用「去重音 + 转小写」后的名字比对：OWID 的 Entity 未必带重音
        # （名单里写 Curaçao，实际数据里是 Curacao，直接 isin 匹配不上，
        #  结果库拉索 1950 年以 60.3 吨/人霸占人均碳榜首，口播开口就是它）。
        micro_norm = {_norm(x) for x in MICRO}
        b2 = len(df)
        df = df[~df['Entity'].map(lambda e: _norm(e) in micro_norm)]
        if b2 != len(df):
            print(f'  微型属地过滤：{b2} -> {len(df)}（去掉 {b2 - len(df)}）')

    df = df[(df['Year'] >= a.start) & (df['Year'] <= a.end)]
    years = sorted(df['Year'].unique().tolist())
    print(f'  年份 {years[0]}~{years[-1]}（{len(years)} 列）')

    piv = df.pivot_table(index=['Entity', 'Code'], columns='Year', values=vcol, aggfunc='first')
    piv = piv.reindex(columns=years)

    # 只保留「至少 N 年有值」的实体，避免全是空的僵尸行
    piv = piv[piv.notna().sum(axis=1) >= max(3, len(years) // 10)]
    print(f'  实体 {len(piv)} 个')

    # 覆盖率护栏：末年覆盖不足就往回退，绝不为了「够新」让末帧大面积掉柱
    while years and piv[years[-1]].notna().sum() / len(piv) < a.min_cov:
        y = years[-1]
        cov = piv[y].notna().sum() / len(piv)
        print(f'  末年 {y} 覆盖率 {cov * 100:.0f}% < {a.min_cov * 100:.0f}%，回退一年')
        years.pop()
        piv = piv.drop(columns=[y])
    if not years:
        raise SystemExit('ERROR: 没有任何年份达到覆盖率阈值，已放弃写盘')

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'{a.out}.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + [str(y) for y in years])
        for (ent, code), row in piv.iterrows():
            name = to_cn(ent)
            vals = ['' if pd.isna(v) else f'{v:g}' for v in row.tolist()]
            w.writerow([name] + vals)
    print(f'  写出 {path}')

    # 末年覆盖率自检
    last = years[-1]
    n_ok = piv[last].notna().sum()
    print(f'  {last} 年有值 {n_ok}/{len(piv)} ({n_ok / len(piv) * 100:.0f}%)')


if __name__ == '__main__':
    main()
