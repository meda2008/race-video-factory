# -*- coding: utf-8 -*-
"""A股适配器：申万行业 / 东方财富行业板块 / ETF 的年度涨跌幅 -> 累计竞速题材。

用 akshare 拉历史行情，按年计算涨跌幅并复利累计（起点=100），产出 mode='cumul'
的累计竞速题材（与 skill 原「申万行业累计竞速」同构，可直接竞速）。

akshare 接口会随版本变动，这里做了：
- 实体列表列名自适应（新 '行业代码'/'行业名称' 或旧 'index_code'/'index_name'）；
- ETF 用 fund_etf_spot_em(6位代码) + fund_etf_hist_em（稳定可用）；
- 申万一级/二级历史优先 index_zh_a_hist，带重试（上游 sw_index_hist_em 已下线）；
- 网络失败单实体跳过，最终无数据才报错。

params:
    kind: 'sw_first'(申万一级) | 'sw_second'(申万二级) | 'industry_em'(东财行业) | 'etf'
    start_year: 累计起点年份（默认 2015）
    top_n: 取累计涨幅最高的前 N 个（默认 15）；排序基准为终点累计值
    title/unit/mode/decimals/highlight/legend: 展示 meta（默认 cumul 累计竞速）
    cache: 是否缓存到 <ws>/_cache_ashare（默认 True，避免重复拉取）
"""
import os
import time

import akshare as ak
import pandas as pd

from .base import BaseAdapter

CACHE_DIR = '_cache_ashare'


def _retry(fn, attempts=3, sleep=1.5):
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as e:  # 含网络 RemoteDisconnected / 解析异常，整体重试
            last = e
            time.sleep(sleep)
    raise last


def _cache_path(ws, kind, code):
    d = os.path.join(ws, CACHE_DIR) if ws else CACHE_DIR
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{kind}_{code}.csv")


def _col(df, *candidates):
    """返回 df 中第一个存在的列名（自适应不同 akshare 版本列名）。"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _entity_list(kind, prefetch=0):
    if kind in ('sw_first', 'sw_second'):
        df = _retry(ak.sw_index_first_info if kind == 'sw_first' else ak.sw_index_second_info)
        code_col = _col(df, '行业代码', 'index_code')
        name_col = _col(df, '行业名称', 'index_name')
        if not code_col or not name_col:
            raise SystemExit(f"ERROR: sw 实体列表列名不符预期: {list(df.columns)}")
        ents = [{'code': str(r[code_col]), 'name': str(r[name_col])}
                for _, r in df.iterrows()]
    elif kind == 'industry_em':
        df = _retry(ak.stock_board_industry_name_em)
        code_col = _col(df, '板块名称', 'name', '代码')
        name_col = _col(df, '板块名称', 'name')
        ents = [{'code': str(r[code_col]), 'name': str(r[name_col])}
                for _, r in df.iterrows()]
    elif kind == 'etf':
        df = _retry(ak.fund_etf_spot_em)
        code_col = _col(df, '代码', 'symbol')      # 6 位代码，可直接喂 fund_etf_hist_em
        name_col = _col(df, '名称', 'name')
        ents = [{'code': str(r[code_col]), 'name': str(r[name_col])}
                for _, r in df.iterrows()]
        # ETF 数量庞大（上千），按成交额取头部样本再算累计，避免逐一拉历史
        if prefetch and len(ents) > prefetch:
            vol_col = _col(df, '成交额', 'amount')
            if vol_col:
                df['_vol'] = pd.to_numeric(df[vol_col], errors='coerce').fillna(0)
                df = df.sort_values('_vol', ascending=False)
                keep = set(str(r[code_col]) for _, r in df.head(prefetch).iterrows())
                ents = [e for e in ents if e['code'] in keep]
    else:
        raise SystemExit(f"ERROR: ashare kind={kind} 不支持")
    return ents


def _get_yearly(ws, kind, code):
    cf = _cache_path(ws, kind, code)
    if os.path.exists(cf):
        try:
            return pd.read_csv(cf)
        except Exception:
            pass
    try:
        if kind in ('sw_first', 'sw_second'):
            # 上游 sw_index_hist_em 已下线，退而用通用指数历史接口
            h = _retry(lambda: ak.index_zh_a_hist(
                symbol=code, period='daily',
                start_date='20000101', end_date='20991231'))
        elif kind == 'industry_em':
            h = _retry(lambda: ak.stock_board_industry_hist_em(
                symbol=code, period='daily', adjust=''))
        elif kind == 'etf':
            h = _retry(lambda: ak.fund_etf_hist_em(
                symbol=code, period='daily', adjust=''))
        else:
            raise SystemExit(f"ERROR: ashare kind={kind} 不支持")
    except Exception as e:
        print(f"  [ashare] {code} 取数失败: {e}")
        return None
    if h is None or len(h) == 0:
        return None
    try:
        h.to_csv(cf, index=False)
    except Exception:
        pass
    return h


def _yearly_returns(hist_df):
    """日线行情 -> {年份: 当年涨跌幅%}（年末/年初 - 1）。"""
    if hist_df is None or len(hist_df) == 0:
        return {}
    df = hist_df.copy()
    date_col = _col(df, '日期', 'date') or df.columns[0]
    close_col = _col(df, '收盘', 'close') or df.columns[1]
    df[date_col] = df[date_col].astype(str)
    df['_y'] = df[date_col].str[:4]
    out = {}
    for y, g in df.groupby('_y'):
        try:
            first = float(g[close_col].iloc[0])
            last = float(g[close_col].iloc[-1])
        except Exception:
            continue
        if first in (0, None) or last is None:
            continue
        out[y] = (last / first - 1.0) * 100.0
    return out


class AShareAdapter(BaseAdapter):
    def fetch(self, params):
        ws = params.get('_ws')
        kind = params.get('kind', 'sw_first')
        start_year = int(params.get('start_year', 2015))
        top_n = int(params.get('top_n', 15))
        cache = bool(params.get('cache', True))

        # 1) 实体列表（ETF 按成交额取头部样本，避免上千只逐一拉历史）
        prefetch = int(params.get('prefetch', 0)) or (60 if kind == 'etf' else 0)
        entities = _entity_list(kind, prefetch)

        # 2) 累计（起点=100）
        candidates = []
        for e in entities:
            hist = _get_yearly(ws, kind, e['code']) if cache else None
            if hist is None:
                hist = _get_yearly(ws, kind, e['code'])
            rets = _yearly_returns(hist)
            if not rets:
                continue
            level = 100.0
            vals = {}
            started = False
            for y in sorted(rets):
                yi = int(y)
                if yi < start_year:
                    continue
                if not started:
                    level = 100.0
                    started = True
                else:
                    level = level * (1.0 + rets[y] / 100.0)
                vals[y] = round(level, 2)
            if len(vals) >= 2:
                candidates.append({'name': e['name'], 'code': e['code'], 'vals': vals})

        if not candidates:
            raise SystemExit(
                f"ERROR: ashare({kind}) 未取到任何数据，检查网络/akshare 版本"
                f"（申万历史接口可能已下线，需更换数据源）")

        # 3) 按终点累计值取 top_n
        candidates.sort(key=lambda c: c['vals'][max(c['vals'], key=int)], reverse=True)
        top = candidates[:top_n]

        years = sorted({y for c in top for y in c['vals']})
        industries = [{'name': c['name'], 'code': c['code'],
                       'values': {y: c['vals'].get(y, 0.0) for y in years}}
                      for c in top]

        meta = self._meta(params, default_title='A股年度涨幅榜',
                          default_unit='', default_mode='cumul',
                          default_decimals=0,
                          default_legend='柱长 = 自起点累计(起点=100)')
        src = params.get('source') or f"akshare {kind} 年度涨跌幅(复利累计)"
        return {
            'years': years,
            'year_labels': {y: y for y in years},
            'industries': industries,
            'meta': meta,
            'source': src,
            'bg_prompt': params.get('bg_prompt'),
        }
