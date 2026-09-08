# -*- coding: utf-8 -*-
"""美股财报 -> 「公司 × 季度」宽表 CSV（AI 资本开支 / 芯片营收）。

ak.stock_financial_us_report_em(stock=<代码>, symbol=<表>, indicator='单季报')
返回**长表**，须按 ITEM_NAME 筛科目（不是宽表，直接取列会 KeyError）。

三个必踩的坑，脚本已处理：
1. 资本开支是负数（现金流出），必须 abs()，否则柱子长度为负。
2. 财年错位：微软财年 6 月结束，其 '2025/Q4' 对应 REPORT_DATE='2026-06-30'。
   跨公司一律用 REPORT_DATE 推自然年季度（year + (month-1)//3+1），不信任 REPORT 标签。
3. TSM / SONY 等本币记账，需汇率换算；首版只取美元记账公司。

用法：
    python fetch_us_fin.py capex   --start 2012 --end 2025
    python fetch_us_fin.py revenue --start 2005 --end 2025
"""
import argparse
import csv
import os
import sys
import time

import akshare as ak

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(WS, 'data', 'topics_csv')

# 均为美元记账，避免引入汇率口径污染
UNIVERSE = {
    'capex': [
        ('MSFT', '微软'), ('GOOGL', '谷歌'), ('AMZN', '亚马逊'), ('META', 'Meta'),
        ('ORCL', '甲骨文'), ('AAPL', '苹果'), ('INTC', '英特尔'), ('WMT', '沃尔玛'),
        ('TSLA', '特斯拉'), ('NVDA', '英伟达'),
    ],
    'revenue': [
        ('INTC', '英特尔'), ('NVDA', '英伟达'), ('AMD', 'AMD'), ('QCOM', '高通'),
        ('TXN', '德州仪器'), ('AVGO', '博通'), ('MU', '美光'), ('MRVL', '迈威尔'),
        ('ADI', '亚德诺'), ('NXPI', '恩智浦'),
    ],
    # 以下均为美元记账公司。TSM/ASML/BHP/RIO/TM/SONY/NVO/AZN 等本币记账的一律排除，
    # 避免引入汇率换算的口径污染（首版只做美元口径）。
    'pharma': [
        ('LLY', '礼来'), ('JNJ', '强生'), ('MRK', '默沙东'), ('ABBV', '艾伯维'),
        ('PFE', '辉瑞'), ('BMY', '百时美施贵宝'), ('AMGN', '安进'), ('GILD', '吉利德'),
        ('VTRS', '晖致'), ('MRNA', 'Moderna'),
    ],
    'semiequip': [
        ('AMAT', '应用材料'), ('LRCX', '泛林集团'), ('KLAC', '科磊'), ('TER', '泰瑞达'),
        ('MKS', 'MKS仪器'), ('AEIS', '先进能源'), ('ACLS', 'Axcelis'),
        ('COHU', 'Cohu'), ('ONTO', 'Onto Innovation'), ('FORM', 'FormFactor'),
    ],
    'defense': [
        ('LMT', '洛克希德马丁'), ('RTX', '雷神'), ('NOC', '诺斯罗普格鲁曼'),
        ('GD', '通用动力'), ('BA', '波音'), ('LHX', 'L3Harris'), ('HII', '亨廷顿英格尔斯'),
        ('TXT', '德事隆'), ('LDOS', 'Leidos'), ('BAH', '博思艾伦'),
    ],
    'mining': [
        ('FCX', '自由港麦克莫兰'), ('NEM', '纽蒙特'), ('SCCO', '南方铜业'),
        ('CLF', '克利夫兰克利夫斯'), ('X', '美国钢铁'), ('AA', '美国铝业'),
        ('MOS', '美盛'), ('CF', 'CF工业'), ('MP', 'MP材料'), ('HL', '赫克拉矿业'),
    ],
}
CONF = {
    # mode: (symbol, ITEM_NAME 关键词, 是否取绝对值, 输出名, 单位除数)
    'capex': ('现金流量表', '购买固定资产', True, 'ai_capex', 1e8),        # -> 亿美元
    'revenue': ('综合损益表', '营业收入', False, 'chip_revenue', 1e8),      # -> 亿美元
    'pharma': ('综合损益表', '营业收入', False, 'pharma_revenue', 1e8),
    'semiequip': ('综合损益表', '营业收入', False, 'semiequip_revenue', 1e8),
    'defense': ('综合损益表', '营业收入', False, 'defense_revenue', 1e8),
    'mining': ('综合损益表', '营业收入', False, 'mining_revenue', 1e8),
}


def qkey(date_str):
    """REPORT_DATE -> 自然年季度键，如 '2025Q2'。"""
    d = str(date_str)[:10]
    y, m = int(d[:4]), int(d[5:7])
    return f'{y}Q{(m - 1) // 3 + 1}'


def trim_tail(qs, series, ratio=0.8, topn=10):
    """删掉表尾「上一年 Top-N 公司大部分尚未披露」的期次。

    竞速图只画前 N 根柱子，判定标准是「上一期排前的公司这一期还在不在」，
    而不是全表覆盖率 —— 2026Q3 只有 2/10 家披露时 Top10 命中率仅 20%，直接砍掉。
    """
    qs = list(qs)
    while len(qs) >= 2:
        prev, cur = qs[-2], qs[-1]
        rank = sorted(series, key=lambda n: -series[n].get(prev, 0))[:topn]
        if not rank:
            break
        hit = sum(1 for n in rank if cur in series[n])
        if hit / len(rank) >= ratio:
            break
        print('  ⛔ %s 上一年 Top%d 命中 %.0f%%（<%.0f%%）→ 删除该期'
              % (cur, len(rank), hit / len(rank) * 100, ratio * 100))
        qs.pop()
    return qs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=list(CONF))
    ap.add_argument('--start', type=int, default=2012)
    ap.add_argument('--end', type=int, default=2025)
    ap.add_argument('--end-auto', action='store_true',
                    help='忽略 --end，以取到的实际最新季度为准（补到最新已披露报告期）')
    ap.add_argument('--quarterly', action='store_true', default=True)
    a = ap.parse_args()

    symbol, item_kw, need_abs, out_name, div = CONF[a.mode]
    series = {}
    for code, cn in UNIVERSE[a.mode]:
        try:
            df = ak.stock_financial_us_report_em(stock=code, symbol=symbol, indicator='单季报')
        except Exception as ex:
            print(f'  {code} 失败: {str(ex)[:70]}')
            continue
        sub = df[df['ITEM_NAME'].astype(str).str.contains(item_kw, na=False)]
        rec = {}
        for _, r in sub.iterrows():
            try:
                v = float(r['AMOUNT'])
            except (TypeError, ValueError):
                continue
            if v != v:
                continue
            q = qkey(r['REPORT_DATE'])
            y = int(q[:4])
            if y < a.start or (not a.end_auto and y > a.end):
                continue
            v = abs(v) if need_abs else v
            rec[q] = v / div
        series[cn] = rec
        n = len(rec)
        print(f'  {cn}({code}) {n} 个季度', flush=True)
        time.sleep(0.4)

    series = {k: v for k, v in series.items() if len(v) >= 8}
    if not series:
        raise SystemExit('ERROR: 未取到任何有效序列，已放弃写盘')
    print(f'有效公司 {len(series)} 家')

    # 季度轴：取所有公司季度键的并集并排序
    qs = sorted(set().union(*[set(v) for v in series.values()]),
                key=lambda q: (int(q[:4]), int(q[5:])))
    print(f'季度轴 {qs[0]} ~ {qs[-1]}（{len(qs)} 期）')

    # 覆盖率护栏（2026-09-06 加）：从表尾往前删掉「上一年 Top-N 公司大部分还没披露」
    # 的期次。美股财年错位（微软 6 月结束），同一期次只有个别公司已披露，
    # 直接留着会让竞速末帧大面积掉柱。
    qs2 = trim_tail(qs, series)
    if qs2 != qs:
        print('  ⛔ 截掉覆盖率不足的期次：%s' % (set(qs) - set(qs2)))
        qs = qs2

    order = sorted(series, key=lambda n: -series[n].get(qs[-1], 0))
    path = os.path.join(CSV_DIR, f'{out_name}.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + qs)
        for n in order:
            w.writerow([n] + [('' if q not in series[n] else f'{series[n][q]:.1f}') for q in qs])
    print('写出', path)
    last = qs[-1]
    print(f'{last} 排名:', [(n, round(series[n].get(last, 0), 1))
                             for n in sorted(series, key=lambda x: -series[x].get(last, 0))])


if __name__ == '__main__':
    main()
