#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""泛化财经主题采集：按 --kind 调不同 akshare 接口，统一输出 data/finance.json。

支持的主题类型(--kind)：
  行业  申万一级/二级指数 逐年涨跌幅 -> 复利累计 -> cumul 模式
  指数  宽基指数(沪深300/中证500/创业板/科创50/上证50/中证1000) 逐年 -> cumul
  概念  东财概念板块 年内收益 TOP N -> value 模式(月度累计时间序列)
  ETF   热门 ETF 年内收益 TOP N -> value 模式(月度累计时间序列)
  基金  偏股基金 年内收益 TOP N -> value 模式(单值, 年内榜)

统一输出 data/finance.json：
  { years, year_labels, industries:[{name,code,values:{year:val}}],
    meta:{title,subtitle,unit,highlight,mode,legend,src,latest_date} }
build_race.py 读取 meta.mode 决定 cumul / value 渲染，因此渲染链零改动复用。

用法：
  python collect_finance.py --workspace <ws> --kind 行业 [--level 1|2] [--start-year 2021]
  python collect_finance.py --workspace <ws> --kind 指数
  python collect_finance.py --workspace <ws> --kind 概念 [--topic 人工智能,半导体] [--top 12]
  python collect_finance.py --workspace <ws> --kind ETF  [--topic 半导体ETF,黄金ETF]
  python collect_finance.py --workspace <ws> --kind 基金 [--top 12]
"""
import argparse, json, os, time, traceback
import akshare as ak
import pandas as pd

# ---------------- 默认标的列表 ----------------
WIDEBASE = [
    ("沪深300", "000300"), ("中证500", "000905"), ("创业板指", "399006"),
    ("科创50", "000688"), ("上证50", "000016"), ("中证1000", "000852"),
]
DEFAULT_CONCEPTS = ["人工智能", "半导体", "新能源车", "储能", "机器人",
                    "CPO", "低空经济", "华为概念", "白酒", "创新药", "军工", "芯片"]
DEFAULT_ETFS = [
    ("沪深300ETF", "510300"), ("科创50ETF", "588000"), ("创业板ETF", "159915"),
    ("半导体ETF", "512480"), ("新能源车ETF", "515030"), ("中证500ETF", "510500"),
    ("券商ETF", "512000"), ("黄金ETF", "518880"), ("医药ETF", "512010"),
    ("军工ETF", "512660"), ("芯片ETF", "159995"), ("酒ETF", "512690"),
]


def get_with_retry(func, *args, tries=3, **kw):
    """akshare 接口偶发连接中断，简单重试以提升采集鲁棒性。"""
    last = None
    for i in range(tries):
        try:
            return func(*args, **kw)
        except Exception as e:
            last = e
            print(f"  [retry {i + 1}/{tries}] {e}")
            time.sleep(0.6 * (i + 1))
    raise last


def pick(df, col_hints):
    cols = {str(c).lower(): c for c in df.columns}
    for h in col_hints:
        for k, v in cols.items():
            if h in k:
                return v
    return None


def year_return(series_close, year):
    s = series_close[series_close.index.year == year]
    if len(s) < 2:
        return None
    return s.iloc[-1] / s.iloc[0] - 1.0


def monthly_cumul_pct(df, ytd_year):
    """给定某标的的日线/月线 df(含 date,close)，算今年各月末相对年初的累计涨跌幅%。
    返回 { 'YYYY-MM': pct } （仅含已过去的月份）。"""
    date_col = pick(df, ['日期', 'date'])
    close_col = pick(df, ['收盘', 'close'])
    if date_col is None or close_col is None:
        return {}
    d = df[[date_col, close_col]].copy()
    d[date_col] = pd.to_datetime(d[date_col])
    d = d.dropna().set_index(date_col)
    d.columns = ['close']
    d = d[d.index.year == ytd_year]
    if len(d) < 2:
        return {}
    base = d['close'].iloc[0]
    out = {}
    for m in range(1, 13):
        sub = d[d.index.month <= m]
        if len(sub) == 0:
            continue
        last = sub['close'].iloc[-1]
        # 只保留已过去的月份（当前月也包含，作为"至今"）
        now = pd.Timestamp.now()
        if m > now.month and ytd_year == now.year:
            break
        out[f"{ytd_year}-{m:02d}"] = round((last / base - 1) * 100, 2)
    return out


# ---------------- 各 kind 采集 ----------------
def collect_industry(ws, level, start_year, ytd_year):
    """申万一级/二级，逐年涨跌幅 -> 复利累计(cumul)。"""
    info = ak.sw_index_first_info() if level == 1 else ak.sw_index_second_info()
    info = info[['行业代码', '行业名称']].copy()
    FULL = list(range(start_year, ytd_year))
    records = []
    for _, row in info.iterrows():
        code_full = str(row['行业代码']).strip()
        code6 = code_full.replace('.SI', '').replace('.si', '')
        name = str(row['行业名称']).strip()
        try:
            df = get_with_retry(ak.index_hist_sw, code6, period='day')
            if df is None or len(df) == 0:
                continue
            date_col = pick(df, ['日期', 'date']); close_col = pick(df, ['收盘', 'close'])
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)[[close_col]].dropna(); df.columns = ['close']
            vals = {}
            cum = 1.0
            for y in FULL:
                r = year_return(df['close'], y)
                if r is not None:
                    cum *= (1 + r)
                vals[str(y)] = round((cum - 1) * 100, 2) if r is not None else None
            r = year_return(df['close'], ytd_year)
            if r is not None:
                cum *= (1 + r)
            vals[str(ytd_year)] = round((cum - 1) * 100, 2)
            records.append({'name': name, 'code': code_full,
                            'values': vals, 'latest': df.index.max().strftime('%Y-%m-%d')})
            print(f"[ok] {name}: {vals}")
        except Exception as e:
            print(f"[err] {name}: {e}")
        time.sleep(0.15)
    years = [str(y) for y in FULL] + [str(ytd_year)]
    return records, years, {
        'title': f"申万{'一级' if level==1 else '二级'}行业累计收益竞速",
        'subtitle': '申万行业指数 · 累计涨跌幅 · 红涨绿跌',
        'unit': '%', 'highlight': None, 'mode': 'cumul',
        'legend': '涨·向右(红) ｜ 跌·向左(绿) ｜ 柱长=累计涨跌幅(0轴=盈亏平衡)',
        'src': '数据来源：akshare 申万行业指数 · 最后一年为至今(YTD) · 累计=起始年初复利至今',
    }


def collect_index(ws, start_year, ytd_year):
    """宽基指数逐年涨跌幅 -> 复利累计(cumul)。"""
    FULL = list(range(start_year, ytd_year))
    records = []
    for name, code in WIDEBASE:
        try:
            df = get_with_retry(ak.index_zh_a_hist, code, period="yearly",
                                start_date=f"{start_year}0101",
                                end_date=f"{ytd_year}1231")
            if df is None or len(df) == 0:
                print(f"[skip] {name}: empty")
                continue
            date_col = pick(df, ['日期', 'date']); close_col = pick(df, ['收盘', 'close'])
            df[date_col] = pd.to_datetime(df[date_col]); df = df.set_index(date_col)[[close_col]].dropna()
            df.columns = ['close']
            vals = {}; cum = 1.0
            for y in FULL:
                r = year_return(df['close'], y)
                if r is not None:
                    cum *= (1 + r)
                vals[str(y)] = round((cum - 1) * 100, 2) if r is not None else None
            r = year_return(df['close'], ytd_year)
            if r is not None:
                cum *= (1 + r)
            vals[str(ytd_year)] = round((cum - 1) * 100, 2)
            records.append({'name': name, 'code': code, 'values': vals,
                            'latest': df.index.max().strftime('%Y-%m-%d')})
            print(f"[ok] {name}: {vals}")
        except Exception as e:
            print(f"[err] {name}: {e}")
        time.sleep(0.2)
    years = [str(y) for y in FULL] + [str(ytd_year)]
    return records, years, {
        'title': "主流宽基指数累计收益竞速",
        'subtitle': '沪深300/中证500/创业板/科创50/上证50/中证1000 · 累计涨跌幅',
        'unit': '%', 'highlight': None, 'mode': 'cumul',
        'legend': '涨·向右(红) ｜ 跌·向左(绿) ｜ 柱长=累计涨跌幅(0轴=盈亏平衡)',
        'src': '数据来源：akshare 指数历史 · 累计=起始年初复利至今',
    }


def collect_concept(ws, topics, top, ytd_year):
    """东财概念板块年内收益 TOP N -> value(月度累计时间序列)。"""
    try:
        board = get_with_retry(ak.stock_board_concept_name_em)
    except Exception as e:
        print(f"[err] 概念列表获取失败: {e}")
        return [], [], {}
    name_col = pick(board, ['名称', 'name'])
    avail = set(board[name_col].astype(str).tolist())
    # 解析要抓的名称
    if topics:
        names = [t.strip() for t in topics.split(',') if t.strip()]
    else:
        names = [c for c in DEFAULT_CONCEPTS if c in avail][:top] or avail
    if not names:
        names = list(avail)[:top]
    print(f"[concept] 抓取 {len(names)} 个概念: {names}")
    records = []
    for name in names:
        try:
            df = get_with_retry(ak.stock_board_concept_hist_em, name, period="monthly",
                                start_date=f"{ytd_year}0101",
                                end_date=f"{ytd_year}1231")
            mc = monthly_cumul_pct(df, ytd_year)
            if not mc:
                continue
            records.append({'name': name, 'code': name, 'values': mc,
                            'latest': f"{ytd_year}年内"})
            print(f"[ok] {name}: 末月 {list(mc.values())[-1]}%")
        except Exception as e:
            print(f"[err] {name}: {e}")
        time.sleep(0.25)
    # 取末月累计收益 TOP N 排序
    if records:
        last_key = max(records[0]['values'].keys())
        records.sort(key=lambda r: r['values'].get(last_key, -1e9), reverse=True)
        records = records[:top]
    years = sorted(records[0]['values'].keys()) if records else []
    ylabels = {y: (f"{int(y.split('-')[1])}月" if y != years[-1] else "至今") for y in years} if years else {}
    return records, years, {
        'title': "概念板块年内收益竞速",
        'subtitle': f"{ytd_year}年内累计涨跌幅 · TOP{len(records)} 概念",
        'unit': '%', 'highlight': None, 'mode': 'value',
        'legend': '柱长 = 年内累计涨跌幅 · 越长越强',
        'src': '数据来源：akshare 东财概念板块 · 年内累计(相对年初)',
    }


def collect_etf(ws, topics, top, ytd_year):
    """热门 ETF 年内收益 TOP N -> value(月度累计时间序列)。"""
    if topics:
        items = [(t.strip(), t.strip()) for t in topics.split(',') if t.strip()]
        # 若用户给的是名称而非代码，尝试在默认表里匹配代码
        code_map = {n: c for n, c in DEFAULT_ETFS}
        items = [(n, code_map.get(n, n)) for n, _ in items]
    else:
        items = DEFAULT_ETFS[:top]
    records = []
    for name, code in items:
        try:
            df = get_with_retry(ak.fund_etf_hist_em, code, period="monthly",
                                start_date=f"{ytd_year}0101",
                                end_date=f"{ytd_year}1231")
            mc = monthly_cumul_pct(df, ytd_year)
            if not mc:
                continue
            records.append({'name': name, 'code': code, 'values': mc, 'latest': f"{ytd_year}年内"})
            print(f"[ok] {name}: 末月 {list(mc.values())[-1]}%")
        except Exception as e:
            print(f"[err] {name}({code}): {e}")
        time.sleep(0.25)
    if records:
        last_key = max(records[0]['values'].keys())
        records.sort(key=lambda r: r['values'].get(last_key, -1e9), reverse=True)
        records = records[:top]
    years = sorted(records[0]['values'].keys()) if records else []
    ylabels = {y: (f"{int(y.split('-')[1])}月" if y != years[-1] else "至今") for y in years} if years else {}
    return records, years, {
        'title': "热门 ETF 年内收益竞速",
        'subtitle': f"{ytd_year}年内累计涨跌幅 · TOP{len(records)} ETF",
        'unit': '%', 'highlight': None, 'mode': 'value',
        'legend': '柱长 = 年内累计涨跌幅 · 越长越强',
        'src': '数据来源：akshare ETF 历史 · 年内累计(相对年初)',
    }


def collect_fund(ws, top, ytd_year):
    """偏股基金年内收益 TOP N -> value(单值, 年内榜)。"""
    try:
        df = get_with_retry(ak.fund_open_fund_rank_em, "混合型")
    except Exception as e:
        print(f"[err] 基金排行获取失败: {e}")
        return [], [], {}
    name_col = pick(df, ['基金简称', '名称', 'name'])
    ytd_col = pick(df, ['今年以来', '今年以来涨跌幅', '今年'])
    if name_col is None or ytd_col is None:
        print("[err] 基金排行字段不匹配:", list(df.columns))
        return [], [], {}
    df[ytd_col] = pd.to_numeric(df[ytd_col], errors='coerce')
    df = df.dropna(subset=[ytd_col]).sort_values(ytd_col, ascending=False).head(top)
    records = []
    for _, row in df.iterrows():
        v = float(row[ytd_col])
        records.append({'name': str(row[name_col]), 'code': str(row.get('基金代码', '')),
                        'values': {str(ytd_year): round(v, 2)}, 'latest': f"{ytd_year}年内"})
    years = [str(ytd_year)]
    ylabels = {str(ytd_year): "至今"}
    return records, years, {
        'title': "偏股基金年内收益榜",
        'subtitle': f"{ytd_year}年以来涨幅 · TOP{len(records)} 偏股混合基金",
        'unit': '%', 'highlight': None, 'mode': 'value',
        'legend': '柱长 = 今年以来涨跌幅 · 越长越强',
        'src': '数据来源：akshare 基金排行 · 今年以来',
    }


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--kind', required=True, choices=['行业', '指数', '概念', 'ETF', '基金'])
    ap.add_argument('--level', type=int, default=1, help='行业: 1=一级 2=二级')
    ap.add_argument('--topic', default=None, help='概念/ETF: 指定名称(逗号分隔)')
    ap.add_argument('--top', type=int, default=12, help='概念/ETF/基金 取前 N')
    ap.add_argument('--start-year', type=int, default=2021)
    ap.add_argument('--ytd-year', type=int, default=None)
    a = ap.parse_args()

    ws = os.path.abspath(a.workspace)
    data_dir = os.path.join(ws, 'data')
    os.makedirs(data_dir, exist_ok=True)
    ytd_year = a.ytd_year or time.localtime().tm_year

    if a.kind == '行业':
        records, years, meta = collect_industry(ws, a.level, a.start_year, ytd_year)
    elif a.kind == '指数':
        records, years, meta = collect_index(ws, a.start_year, ytd_year)
    elif a.kind == '概念':
        records, years, meta = collect_concept(ws, a.topic, a.top, ytd_year)
    elif a.kind == 'ETF':
        records, years, meta = collect_etf(ws, a.topic, a.top, ytd_year)
    elif a.kind == '基金':
        records, years, meta = collect_fund(ws, a.top, ytd_year)
    else:
        raise SystemExit("未知 kind")

    if not records:
        raise SystemExit("ERROR: 未采集到任何数据，请检查网络或 --topic 参数")

    industries = [{'name': r['name'], 'code': r.get('code', ''),
                   'values': {str(k): v for k, v in r['values'].items()}}
                  for r in records]
    meta['latest_date'] = records[0].get('latest', years[-1])
    out = {
        'years': years,
        'year_labels': ({y: (f"{int(y.split('-')[1])}月" if '-' in y and y != years[-1] else ("至今" if '-' in y else y))
                         for y in years} if meta['mode'] == 'value' and '-' in years[0]
                        else {y: y for y in years}),
        'industries': industries,
        'meta': meta,
    }
    # 修正 year_labels：value 模式月度序列
    if meta['mode'] == 'value' and years and '-' in years[0]:
        out['year_labels'] = {y: (f"{int(y.split('-')[1])}月" if y != years[-1] else "至今") for y in years}

    dst = os.path.join(data_dir, 'finance.json')
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nwrote", dst, f"kind={a.kind} mode={meta['mode']} n={len(industries)} years={len(years)}")
    print("标的:", [i['name'] for i in industries])


if __name__ == '__main__':
    main()
