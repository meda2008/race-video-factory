#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把逐年涨跌幅 JSON 折算为「累计涨跌幅」JSON（2021 年初复利累计到每年末）。

用法：
  python build_cumul.py --workspace <ws>
读取 <ws>/data/sw_industry_yearly.json
写出 <ws>/data/sw_industry_cumul.json

累计口径：从首个年份起，cum = 1.0；每年 cum *= (1 + r/100)；
          该年累计值 = (cum-1)*100。0 轴 = 2021 至今盈亏平衡。
某年数据缺失(None)时，当年累计沿用上一年值（不增长），保持时间轴连续。
"""
import argparse, json, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    src = os.path.join(ws, 'data', 'sw_industry_yearly.json')
    dst = os.path.join(ws, 'data', 'sw_industry_cumul.json')
    if not os.path.exists(src):
        raise SystemExit(f"ERROR: 找不到 {src}，请先跑 collect_sw_yearly.py")

    data = json.load(open(src, encoding='utf-8'))
    years = data['years']
    for it in data['industries']:
        cum = 1.0
        prev_val = 0.0
        vals = {}
        for y in years:
            r = it['values'].get(y)
            if r is None:
                vals[y] = round(prev_val, 2)   # 缺失年：沿用上一年累计
                continue
            cum *= (1 + r / 100.0)
            prev_val = (cum - 1) * 100
            vals[y] = round(prev_val, 2)
        it['values'] = {y: vals[y] for y in years}

    out = {k: data[k] for k in ('years', 'year_labels', 'latest_date') if k in data}
    out['industries'] = [
        {k: it[k] for k in ('name', 'code', 'values')} for it in data['industries']
    ]
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", dst, "years=", years)


if __name__ == '__main__':
    main()
