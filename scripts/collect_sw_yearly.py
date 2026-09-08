#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取申万一级行业 各全年涨跌幅 + 当年 YTD，输出 CSV 与渲染用 JSON。

用法（在任意 workspace 下）：
  python collect_sw_yearly.py --workspace <ws> [--start-year 2021] [--ytd-year 2026]
输出：
  <ws>/data/sw_industry_yearly.csv   行=行业，列=各年涨跌幅
  <ws>/data/sw_industry_yearly.json  供渲染 / build_cumul.py 使用
"""
import argparse, akshare as ak, pandas as pd, json, os, time, traceback


def pick(df, col_hints):
    cols = {str(c).lower(): c for c in df.columns}
    for h in col_hints:
        for k, v in cols.items():
            if h in k:
                return v
    return None


def annual_return(series_close, year):
    s = series_close[series_close.index.year == year]
    if len(s) < 2:
        return None
    return s.iloc[-1] / s.iloc[0] - 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--start-year', type=int, default=2021)
    ap.add_argument('--ytd-year', type=int, default=None)
    a = ap.parse_args()

    workspace = os.path.abspath(a.workspace)
    data_dir = os.path.join(workspace, 'data')
    os.makedirs(data_dir, exist_ok=True)
    ytd_year = a.ytd_year or time.localtime().tm_year

    FULL_YEARS = list(range(a.start_year, ytd_year))   # 全年（不含当年）
    print(f"[collect] full-years={FULL_YEARS} ytd={ytd_year}")

    info = ak.sw_index_first_info()
    info = info[['行业代码', '行业名称']].copy()
    records = []
    for _, row in info.iterrows():
        code_full = str(row['行业代码']).strip()      # e.g. 801010.SI
        code6 = code_full.replace('.SI', '').replace('.si', '')
        name = str(row['行业名称']).strip()
        try:
            df = ak.index_hist_sw(symbol=code6, period='day')
            if df is None or len(df) == 0:
                print(f"[skip] {name} {code6}: empty")
                continue
            date_col = pick(df, ['日期', 'date'])
            close_col = pick(df, ['收盘', 'close'])
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)[[close_col]].dropna()
            df.columns = ['close']
            vals = {}
            for y in FULL_YEARS:
                r = annual_return(df['close'], y)
                vals[y] = round(r * 100, 2) if r is not None else None
            r = annual_return(df['close'], ytd_year)
            vals[ytd_year] = round(r * 100, 2) if r is not None else None
            latest_date = df.index.max().strftime('%Y-%m-%d')
            records.append({'name': name, 'code': code_full, 'values': vals,
                            'latest_date': latest_date})
            print(f"[ok] {name}: " + ", ".join(f"{k}={v}" for k, v in vals.items()))
        except Exception as e:
            print(f"[err] {name} {code6}: {e}")
            traceback.print_exc()
        time.sleep(0.2)

    all_years = FULL_YEARS + [ytd_year]
    csv_rows = []
    for rec in records:
        row = {'行业名称': rec['name'], '行业代码': rec['code']}
        for y in all_years:
            row[str(y)] = rec['values'].get(y)
        row['数据截止'] = rec['latest_date']
        csv_rows.append(row)
    csv_df = pd.DataFrame(csv_rows)
    csv_path = os.path.join(data_dir, 'sw_industry_yearly.csv')
    csv_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print("CSV ->", csv_path)

    js = {
        'years': [str(y) for y in all_years],
        'year_labels': {str(y): (f"{y}YTD" if y == ytd_year else str(y)) for y in all_years},
        'latest_date': records[0]['latest_date'] if records else '',
        'industries': [
            {'name': r['name'], 'code': r['code'],
             'values': {str(y): r['values'].get(y) for y in all_years}}
            for r in records
        ],
    }
    json_path = os.path.join(data_dir, 'sw_industry_yearly.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(js, f, ensure_ascii=False, indent=2)
    print("JSON ->", json_path)
    print(f"有效行业数: {len(records)}/{len(info)}")


if __name__ == '__main__':
    main()
