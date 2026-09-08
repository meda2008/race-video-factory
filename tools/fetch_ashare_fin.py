# -*- coding: utf-8 -*-
"""A股全市场财报 -> 「公司 × 年」宽表 CSV（亏损王 / 赚钱王 / 营收王）。

ak.stock_lrb_em(date='YYYY1231') 一次返回全市场约 5235 只个股的利润表（宽表），
每行一只股票，关键列：股票代码 / 股票简称 / 净利润 / 营业总收入（单位：元）。

建面板的原则：不是「每年各取 Top N 再拼」，而是
    1) 先取任意一年进过 Top N 的所有公司（并集）
    2) 再回填这些公司的完整年度序列
否则不同年份实体集合不一致，竞速图会出现大量空柱。

用法：
    python fetch_ashare_fin.py loss     [--top 15] [--start 2004] [--end 2025]
    python fetch_ashare_fin.py profit   [--top 15]
    python fetch_ashare_fin.py revenue  [--top 15]
"""
import argparse
import csv
import os
import sys
import time

import akshare as ak

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(WS, 'data', 'topics_csv')

# mode -> (表, 列名, 是否取最负, 输出名, 换算除数, 单位说明, 是否「年初至今累计」)
#   cumulative=True  -> 季度值 = 本期累计 − 上期累计（利润表、现金流量表）
#   cumulative=False -> 季度值 = 当期时点数（资产负债表的货币资金/应收账款是时点数，
#                                做差分会得到「变化量」而不是「存量」，竞速含义会错）
MODES = {
    'profit':     ('lrb',  '净利润',                     False, 'ashare_profit',     1e8, '亿元', True),
    'loss':       ('lrb',  '净利润',                     True,  'ashare_loss',       1e8, '亿元', True),
    'revenue':    ('lrb',  '营业总收入',                 False, 'ashare_revenue',    1e8, '亿元', True),
    # 注意利润表里销售费用的真实列名带前缀，是「营业总支出-销售费用」不是「销售费用」
    'sellexp':    ('lrb',  '营业总支出-销售费用',     False, 'ashare_sellexp',    1e8, '亿元', True),
    'cash':       ('zcfz', '资产-货币资金',              False, 'ashare_cash',       1e8, '亿元', False),
    'receivable': ('zcfz', '资产-应收账款',              False, 'ashare_receivable', 1e8, '亿元', False),
    'ocf':        ('xjll', '经营性现金流-现金流量净额',  False, 'ashare_ocf',        1e8, '亿元', True),
    # 分红：现金分红比例是「每 10 股派现多少元」，不是总额，不能除 1e8；只有年报口径
    'dividend':   ('fhps', '现金分红-现金分红比例',     False, 'ashare_dividend',   1.0, '元/10股', False),
}

# 表 -> (akshare 函数, 公司名列, 代码列)。注意分红表用的是「名称/代码」不是「股票简称/股票代码」
TABLES = {
    'lrb':  ('stock_lrb_em',  '股票简称', '股票代码'),
    'zcfz': ('stock_zcfz_em', '股票简称', '股票代码'),
    'xjll': ('stock_xjll_em', '股票简称', '股票代码'),
    'fhps': ('stock_fhps_em', '名称',     '代码'),
}

# 代码黑名单：这些「公司」从未在 A 股上市交易，但东方财富收录了其 IPO 招股书的
# 历史财务数据，混进全市场报表会污染榜单。
#   688688 蚂蚁集团 —— 2020 年科创板 IPO 被叫停前分配的代码，招股书披露了
#                      2017–2019 年财务数据（2018 年销售费用 473.45 亿），
#                      足以挤进销售费用榜前六，但它从未上市。
BLACKLIST_CODES = {'688688'}


def _lbl_tuple(s):
    """'2025Q4' -> (2025, 4)；'2025' -> (2025, 4)"""
    if 'Q' in s:
        return int(s[:4]), int(s[5])
    return int(s), 4


def _fetch_period(fn, y, q, col, code_col, name_col, div):
    """取单期次的 {公司名: 原始值}（原始值 = 年初至今累计 / 时点数，未做差分）。"""
    md = {1: '0331', 2: '0630', 3: '0930', 4: '1231'}[q]
    df = None
    for attempt in range(3):
        try:
            df = fn(date=f'{y}{md}')
            break
        except Exception as ex:
            print(f'  {y}{md} 第{attempt + 1}次失败: {str(ex)[:60]}')
            time.sleep(2)
    if df is None:
        print(f'  {y}{md} 放弃')
        return None
    if col not in df.columns:
        raise SystemExit(f'ERROR: 无「{col}」列，实际列={list(df.columns)[:12]}')
    rec = {}
    for _, r in df.iterrows():
        code = str(r[code_col]).strip()
        if code in BLACKLIST_CODES:
            continue
        try:
            v = float(r[col])
        except (TypeError, ValueError):
            continue
        if v != v:
            continue
        rec[str(r[name_col]).strip()] = v / div
    return rec


def _append_mode(a, fn, col, code_col, name_col, div, cumulative, out_name, END_Q):
    """增量模式：只抓「现有 CSV 末年之后」的期次，追加列，实体集合保持不变。

    差分处理：单季值 = 本期累计 − 上年末/上期累计。新增期次若不是从 Q1 开始，
    会额外多取同年内更早期次用于差分（时点型科目 cumulative=False 不做差分）。
    """
    path = os.path.join(CSV_DIR, f'{out_name}.csv')
    if not os.path.exists(path):
        raise SystemExit(f'ERROR: --append-after 需要现有 CSV，但 {path} 不存在')
    rows = list(csv.reader(open(path, encoding='utf-8-sig', newline='')))
    head = [c for c in rows[0][1:] if c.strip()]
    names = [r[0].strip() for r in rows[1:] if r and r[0].strip()]
    cur = {r[0].strip(): r[1:] for r in rows[1:] if r and r[0].strip()}
    ly, lq = _lbl_tuple(head[-1])
    print(f'[append] 现有 {len(names)} 实体 × {len(head)} 列，末列 {head[-1]}')

    # 需要新增的期次
    newp, y, q = [], ly, lq
    while len(newp) < 300:
        q += 1
        if q > 4:
            q, y = 1, y + 1
        if END_Q and (y, q) > END_Q:
            break
        newp.append((y, q))
    if not newp:
        print('  无新期次，跳过')
        return
    print(f'[append] 将追加 {len(newp)} 期：{newp[0][0]}Q{newp[0][1]} ~ {newp[-1][0]}Q{newp[-1][1]}')

    # 需要实际拉取的期次：每年从 Q1 拉到该年最大新增季度（保证差分有上期）
    need = {}
    for (yy, qq) in newp:
        need.setdefault(yy, set()).add(qq)
    pull = []
    for yy in sorted(need):
        for qq in range(1, max(need[yy]) + 1):
            pull.append((yy, qq))

    added = {}          # 期次标签 -> {name: 值}
    prev_year, prev_rec = None, None
    for (yy, qq) in pull:
        rec = _fetch_period(fn, yy, qq, col, code_col, name_col, div)
        if rec is None:
            prev_rec, prev_year = None, yy
            continue
        prev = prev_rec if (cumulative and prev_year == yy) else None
        lbl = f'{yy}Q{qq}'
        if (yy, qq) in newp:
            d = {}
            for nm, v in rec.items():
                if prev and nm in prev:
                    v = v - prev[nm]
                d[nm] = v
            added[lbl] = d
            n_hit = sum(1 for nm in names if nm in d)
            print(f'  + {lbl}  命中 {n_hit}/{len(names)} 实体', flush=True)
        prev_year, prev_rec = yy, rec
        time.sleep(0.3)

    if not added:
        raise SystemExit('ERROR: 增量模式没有取到任何新期次，已放弃写盘（原 CSV 未改动）')

    # 覆盖率护栏：新列命中率低于上一列的 60% 就丢弃该列及之后
    prev_cov = sum(1 for nm in names
                   if len(cur[nm]) >= len(head) and (cur[nm][len(head) - 1] or '').strip())
    prev_cov = prev_cov / max(1, len(names))
    keep = []
    for lbl, d in added.items():
        cov = sum(1 for nm in names if nm in d) / max(1, len(names))
        if cov < max(0.35, prev_cov * 0.6):
            print(f'  ⛔ {lbl} 覆盖率 {cov:.0%} < 门槛（前一年 {prev_cov:.0%}）→ 丢弃该期及之后')
            break
        keep.append(lbl)
        prev_cov = cov
    if not keep:
        raise SystemExit('ERROR: 覆盖率护栏未通过，原 CSV 未改动')

    out_head = head + keep
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + out_head)
        for nm in names:
            row = list(cur[nm])[:len(head)]
            row += [''] * (len(head) - len(row))
            for lbl in keep:
                v = added[lbl].get(nm)
                row.append('' if v is None else f'{v:.2f}')
            w.writerow([nm] + row)
    print(f'  写出 {path}：{len(names)} 实体 × {len(out_head)} 列（+{len(keep)}）')

    last = keep[-1]
    top = sorted([(nm, added[last][nm]) for nm in names if nm in added[last]],
                 key=lambda kv: -kv[1])[:8]
    print(f'{last} Top8:', [(n, round(v, 1)) for n, v in top])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=list(MODES))
    ap.add_argument('--top', type=int, default=15)
    ap.add_argument('--start', type=int, default=2004)
    ap.add_argument('--end', type=int, default=2025)
    ap.add_argument('--max-entities', type=int, default=34,
                    help='实体数上限，超过则按「进榜次数×进榜名次」再筛一轮')
    ap.add_argument('--freq', choices=['yearly', 'quarterly'], default='yearly',
                    help='数据粒度：yearly 年报（默认）；quarterly 季度（2026-09 起全表支持：'
                         'lrb/xjll 取单季值=累计差分，zcfz 取时点值）')
    ap.add_argument('--end-auto', action='store_true',
                    help='自动探测「实际已披露的最新报告期」，覆盖 --end')
    ap.add_argument('--append-after', default='',
                    help='增量模式：只抓取该期次（如 2025Q4）之后的期次并追加到现有 CSV，'
                         '保持实体集合不变。比全量重取快 40 倍（2026-09-06 新增）')
    a = ap.parse_args()

    tbl_key, col, want_loss, out_name, div, unit, cumulative = MODES[a.mode]
    tbl, name_col, code_col = TABLES[tbl_key]
    fn = getattr(ak, tbl)
    if a.freq == 'quarterly' and tbl_key == 'fhps':
        raise SystemExit('ERROR: 分红(fhps) 只有年度报告期，不支持 quarterly')

    # ---- 自动探测最新报告期：从「今年可能的最晚报告期」往回试 ----
    if a.end_auto:
        import datetime as _dt
        today = _dt.date.today()
        latest = None
        # 报告期披露滞后：一季报4月底、半年报8月底、三季报10月底、年报4月底
        for back in range(0, 8):
            y = today.year - (back // 4)
            q = 4 - (back % 4)          # 4,3,2,1
            md = {1: '0331', 2: '0630', 3: '0930', 4: '1231'}[q]
            ds = f'{y}{md}'
            try:
                _df = fn(date=ds)
                if _df is not None and len(_df) > 100:
                    latest = (y, q)
                    break
            except Exception:
                continue
        if latest is None:
            raise SystemExit('ERROR: 自动探测最新报告期失败')
        print(f'[auto] 探测到最新已披露报告期：{latest[0]}Q{latest[1]}')
        a.end = latest[0]
        if a.freq == 'quarterly':
            END_Q = latest
        else:
            END_Q = None
            # 年报口径：若当年年报尚未披露（Q<4），回退一年
            if latest[1] < 4:
                a.end = latest[0] - 1
                print(f'[auto] 年报口径：{latest[0]} 年报未披露，末年回退到 {a.end}')
    else:
        END_Q = None

    if a.append_after and not a.end_auto:
        raise SystemExit('ERROR: --append-after 必须搭配 --end-auto（否则无法判断最新报告期）')
    if a.append_after:
        _append_mode(a, fn, col, code_col, name_col, div, cumulative, out_name, END_Q)
        return

    years = list(range(a.start, a.end + 1))
    if a.freq == 'quarterly':
        # 报告期：0331/0630/0930/1231
        periods = ['0331', '0630', '0930', '1231']
    else:
        periods = ['1231']
    yearly = {}
    for y in years:
        cumul = {}      # 累计值（name -> 累计值）
        prev = None
        for qi, md in enumerate(periods):
            # 自动探测模式下，超过「已披露最新报告期」的一律不取
            if END_Q and (y, qi + 1) > END_Q:
                continue
            for attempt in range(3):
                try:
                    df = fn(date=f'{y}{md}')
                    break
                except Exception as ex:
                    print(f'  {y}{md} 第{attempt + 1}次失败: {str(ex)[:60]}')
                    time.sleep(2)
                    df = None
            if df is None:
                print(f'  {y}{md} 放弃')
                continue
            if col not in df.columns:
                raise SystemExit(f'ERROR: {tbl} 无「{col}」列，实际列={list(df.columns)[:12]}')
            rec = {}
            n_block = 0
            for _, r in df.iterrows():
                code = str(r[code_col]).strip()
                if code in BLACKLIST_CODES:
                    n_block += 1
                    continue
                name = str(r[name_col]).strip()
                try:
                    v = float(r[col])
                except (TypeError, ValueError):
                    continue
                if v != v:  # NaN
                    continue
                rec[name] = v / div
            # 计算单季值：仅「累计型」科目做差分（时点型科目直接取当期值）
            for name, v in rec.items():
                pv = prev.get(name) if prev else None
                if a.freq == 'quarterly' and cumulative and qi > 0 and pv is not None:
                    v = v - pv
                # 年报口径的标签必须是纯年份（否则年度数据会被标成 2025Q1，
                # 画面 X 轴语义就错了）
                _lbl = f'{y}Q{qi + 1}' if a.freq == 'quarterly' else str(y)
                yearly[_lbl] = yearly.get(_lbl, {})
                yearly[_lbl][name] = v
            prev = rec
            time.sleep(0.3)
        print(f'  {y} 完成（{a.freq}）', flush=True)

    if not yearly:
        raise SystemExit('ERROR: 没有取到任何年份的数据，已放弃写盘')

    # 每年榜单（亏损榜取最负的 N 个，其余取最大的 N 个）
    picks = set()
    score = {}
    for y, rec in yearly.items():
        items = [(n, v) for n, v in rec.items() if (v < 0 if want_loss else v > 0)]
        items.sort(key=lambda kv: kv[1], reverse=not want_loss)
        for rank, (n, v) in enumerate(items[:a.top]):
            picks.add(n)
            score[n] = score.get(n, 0) + (a.top - rank)

    print(f'进过前{a.top}的公司：{len(picks)} 家')
    if len(picks) > a.max_entities:
        keep = sorted(picks, key=lambda n: -score[n])[:a.max_entities]
        print(f'  超上限，按进榜权重保留 {len(keep)} 家')
        picks = set(keep)

    # 只保留至少有 3 期数据的公司，避免僵尸行
    picks = {n for n in picks
             if sum(1 for rec in yearly.values() if n in rec) >= 3}
    print(f'  ≥3期数据的：{len(picks)} 家')

    order = sorted(picks, key=lambda n: -score.get(n, 0))
    ycols = sorted(yearly.keys(), key=lambda k: (int(k[:4]), int(k[5]) if 'Q' in k else 0))
    path = os.path.join(CSV_DIR, f'{out_name}.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + ycols)
        for n in order:
            row = []
            for y in ycols:
                v = yearly.get(y, {}).get(n)
                row.append('' if v is None else f'{v:.2f}')
            w.writerow([n] + row)
    print('写出', path)

    last = ycols[-1]
    rec = yearly.get(last, {})
    top = sorted([(n, rec[n]) for n in order if n in rec],
                 key=lambda kv: kv[1], reverse=not want_loss)[:8]
    print(f'{last} Top8:', [(n, round(v, 1)) for n, v in top])


if __name__ == '__main__':
    main()
