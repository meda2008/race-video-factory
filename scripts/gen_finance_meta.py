#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用财经主题文案生成：读 data/finance.json，按 meta.mode 分支产出
口播稿(narration.txt) + 发布文案(post_meta.json / post_meta.txt)。

- mode == 'cumul'：累计收益（申万行业/宽基指数）。沿用「前三/后三/最大跳变」叙事，
  文案不再硬编码"申万一级"，而是通用化（适用于任意 cumul 主题）。
- mode == 'value'：绝对数值对比（中外对比/概念/ETF/基金榜）。
  若 meta.highlight 非空（如"中国"），走"反超/登顶"叙事；
  若为空（概念/ETF/基金 TOP N 榜），走"谁领涨、领先多少"叙事。

platform:
  xhs    -> 小红书风格（emoji 钩子 + #话题 + 软性引导）
  wechat -> 公众号风格（克制干货）

纯本地模板生成，无需联网 / LLM。数字来自真实采集（或题材 JSON），文案可手改或用
khazix-writer / 猫笔刀写作风格 等 skill 二次润色。
"""
import argparse, json, os
from datetime import datetime

PLATFORMS = ('xhs', 'wechat')


def fmt_pct(x):
    if x is None:
        return "—"
    return ("+" if x >= 0 else "") + f"{x:.0f}"


def fmt_abs(x, dec=0):
    """绝对值格式化：按 dec 保留小数位（默认整数），并去掉多余尾零，保证口播与画面数字一致。

    ⚠️ 不能无脑 rstrip('0')：
      - 2190 经 f"{2190:,.0f}" 得到 "2,190"，再 rstrip('0') 会变成 "2,19"（整数末尾的 0 被吃掉）
      - 0 经 f"{0:,.0f}" 得到 "0"，rstrip('0') 会变成空字符串，
        口播出「法国以TWh排在最后」这种丢数字的病句
    故只在「真的有小数位」时才剥尾零，且保证至少留下一位有效数字。
    """
    if x is None:
        return "—"
    ax = abs(x)
    if dec > 0:
        s = f"{ax:,.{dec}f}"
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s or "0"
    return f"{ax:,.0f}"


def fmt_val(x):
    if x is None:
        return "—"
    if abs(x) >= 100 or float(x).is_integer():
        return f"{x:.0f}"
    return f"{x:.1f}"


def year_int(y):
    """从时间标签提取「年份」整数（4 位）。

    ⚠️ 旧实现 int(''.join(filter(str.isdigit, str(y)))) 会把季度/月度后缀的数字也
    拼进去：'2004Q1'→20041、'2025Q4'→20254，二者相减得 213，导致标题出现
    「213年竞速」这种荒谬文案，还顺带把「单季跳升」的年份差算错。
    正确做法：只取标签里最前面的 4 位年份数字。
    """
    import re
    m = re.search(r'\d{4}', str(y))
    return int(m.group()) if m else 0


def topics_for_title(title, mode='value'):
    """按题材标题动态生成话题标签，避免千篇一律的 #A股 通用模板（2026-08-19 补全映射）。

    value 模式：按标题关键词匹配（市值/营收/薪酬/人口/城市/电影/票房/财富/大学…），
               未命中回退「#财经数据」通用标签（不再默认塞 #A股）。
    cumul 模式：加密货币 / 黄金原油 等特定题材单独给标签，其余回退原累计收益标签。
    """
    if mode == 'cumul':
        if '加密' in title or '币' in title:
            return ["#加密货币", "#比特币", "#区块链", "#数据可视化",
                    "#理财干货", "#投资理财", "#数字资产"]
        if '黄金' in title or '原油' in title or '大宗' in title:
            return ["#黄金", "#原油", "#大宗商品", "#数据可视化",
                    "#理财干货", "#投资理财", "#资产配置"]
        return ["#A股", "#数据可视化", "#复利", "#长期投资", "#理财干货",
                "#投资理财", "#我的炒股日记", "#股市复盘", "#行业轮动"]
    # value 模式
    topic_kw = {
        '市值': ['#市值', '#科技股', '#财经数据', '#数据可视化'],
        '营收': ['#世界500强', '#财富', '#大企业', '#财经数据', '#数据可视化'],
        '500强': ['#世界500强', '#财富', '#大企业', '#财经数据', '#数据可视化'],
        '薪酬': ['#薪酬', '#职场', '#打工人', '#数据可视化', '#干货分享'],
        '工资': ['#薪酬', '#职场', '#打工人', '#数据可视化', '#干货分享'],
        '人口': ['#人口', '#数据可视化', '#社会观察', '#财经数据'],
        '城市': ['#城市', '#区域发展', '#数据可视化', '#财经数据'],
        '电影': ['#电影', '#票房', '#数据可视化', '#文娱'],
        '票房': ['#电影', '#票房', '#数据可视化', '#文娱'],
        '财富': ['#财富', '#富豪', '#胡润', '#财经数据', '#数据可视化'],
        '富豪': ['#财富', '#富豪', '#胡润', '#财经数据', '#数据可视化'],
        '大学': ['#大学', '#高校', '#教育', '#数据可视化', '#干货分享'],
        '高校': ['#大学', '#高校', '#教育', '#数据可视化', '#干货分享'],
        '排名': ['#大学', '#高校', '#教育', '#数据可视化', '#干货分享'],
    }
    for k, v in topic_kw.items():
        if k in title:
            return v + ['#投资理财', '#我的炒股日记']
    return ['#财经数据', '#数据可视化', '#理财干货', '#投资理财', '#我的炒股日记']


# ============================================================================
# 解说词风格铁律（用户 2026-08-18 明确，已固化进流水线）：
#   口播必须「有对比 / 有反差 / 有反转」——点出谁被反超、谁掉队、差距拉大；
#   严禁套话式总结（如「条条拉长，红涨绿跌，一目了然」「红涨绿跌」等无信息量收尾）。
#   所有数字须来自真实数据（compute_*_stats 计算），不得编造。
#   时间不足的短口播也要尽量落到具体反差点，而非泛泛而谈。
# ============================================================================

def _contrast_lines(s, unit):
    """通用「对比/反差/反转」口播段落（无套话）。供 value 模式 no-hl 与 generic 分支复用。

    s 须含 compute_value_stats 新增字段：multi / leader0_name / leader1_name /
    top_faller(名称,r0,r1,Δ) / gap_y0 / gap_y1 / gap_ratio。
    返回若干句中文口播（不含开场句）。
    """
    lead, second, margin = s['lead'], s['second'], s['margin']
    lines = []
    if s['multi']:
        if s['leader0_name'] and s['leader1_name'] and s['leader0_name'] != s['leader1_name']:
            lines.append(
                f"{s['y0']}年还是{s['leader0_name']}领跑，到了{s['y1']}年，"
                f"头把交椅已经换成了{s['leader1_name']}。")
        elif lead[1] is not None:
            lines.append(f"截至目前，{lead[0]}以{fmt_val(lead[1])}{unit}高居第一；")
        if s['top_faller']:
            fn, r0, r1, _ = s['top_faller']
            lines.append(f"反观{fn}，从{s['y0']}年的第{r0}名滑到第{r1}名，是掉队最狠的一个。")
    else:
        if lead[1] is not None:
            lines.append(f"截至目前，{lead[0]}以{fmt_val(lead[1])}{unit}居首；")
    if second and margin is not None and not (s['top_faller'] and s['top_faller'][0] == second[0]):
        lines.append(f"第二是{second[0]}，{fmt_val(second[1])}{unit}，落后约{fmt_val(margin)}{unit}。")
    if s['multi'] and s['gap_y0'] is not None and s['gap_y1'] is not None:
        g0, g1 = fmt_val(s['gap_y0']), fmt_val(s['gap_y1'])
        if s['gap_ratio'] and s['gap_ratio'] >= 1.5:
            lines.append(
                f"最高与最低之间的鸿沟，从{s['y0']}年的{g0}{unit}拉大到{s['y1']}年的{g1}{unit}"
                f"——涨得最猛的，和掉队的，从来不是同一批。")
        else:
            lines.append(f"一头一尾的差距，也从{g0}{unit}拉到了{g1}{unit}。")
    elif not s['multi'] and s['gap_y1'] is not None and lead[1] is not None:
        g1 = fmt_val(s['gap_y1'])
        lines.append(f"而垫底的那家，还不到{lead[0]}的零头，这中间的差距就有{g1}{unit}。")
    return lines


# ---------------- cumul 模式 stats / 文案 ----------------
def compute_cumul_stats(data):
    years = data['years']
    labels = data.get('year_labels', {})
    first, last = years[0], years[-1]
    last_label = labels.get(last, last)

    rows = []
    for it in data['industries']:
        v = it['values'].get(last)
        if v is None:
            continue
        rows.append((it['name'], v))
    rows.sort(key=lambda x: x[1], reverse=True)

    top3 = rows[:3]
    bottom3 = rows[-3:][::-1]
    best = None
    for it in data['industries']:
        vals = it['values']
        for i in range(1, len(years)):
            y0, y1 = years[i - 1], years[i]
            v0, v1 = vals.get(y0), vals.get(y1)
            if v0 is None or v1 is None:
                continue
            j = v1 - v0
            if best is None or abs(j) > abs(best[2]):
                best = (it['name'], labels.get(y1, y1), j)
    return {
        'first': first, 'last': last, 'last_label': last_label,
        'span': year_int(last) - year_int(first),
        'n': len(rows), 'top3': top3, 'bottom3': bottom3,
        'best_jump': best, 'lead': top3[0], 'tail': bottom3[0],
    }


def narration_cumul(title, s):
    sy, ly = s['first'], s['last_label']
    span = s['span']
    lead, tail = s['lead'], s['tail']
    # tail 描述：正数（即使是全正数据中的垫底）不能说"跌了"；只有真正为负才用"跌"
    if tail[1] < 0:
        tail_clause = f"而{tail[0]}累计跌了{fmt_abs(tail[1])}%，排在最后。"
    else:
        tail_clause = f"而{tail[0]}累计仅涨{fmt_abs(tail[1])}%，垫底在最后。"
    lines = [
        f"从{sy}年到{ly}，我们用动态榜单跑了一场累计收益竞速。",
        f"{span}年下来，{lead[0]}累计涨了{fmt_abs(lead[1])}%，一路领跑；",
        tail_clause,
    ]
    jump = s['best_jump']
    lead_gap = fmt_abs(lead[1] - tail[1])
    if jump and abs(jump[2]) >= 30:
        lines.append(
            f"其中{jump[0]}在{jump[1]}一年就拉开约{fmt_abs(jump[2])}个百分点，"
            f"把分化彻底坐实——头尾之间，已经隔出{lead_gap}个百分点的鸿沟。")
    else:
        lines.append(f"同一段时间，有人翻倍有人腰斩：领跑的{lead[0]}和垫底的{tail[0]}，"
                     f"差出{lead_gap}个百分点。")
    return "\n".join(lines)


def copy_cumul(title, s, platform):
    sy, ly = s['first'], s['last_label']
    span = s['span']
    lead, tail = s['lead'], s['tail']
    la, ta = fmt_abs(lead[1]), fmt_abs(tail[1])
    # tail 描述：正数（全正数据中的垫底）不能说"跌"；只有真正为负才用"跌"
    if tail[1] < 0:
        tail_down = f"跌去{ta}%"
        tail_down2 = f"深跌{ta}%"
        tail_phrase = f"却跌{ta}%"
    else:
        tail_down = f"仅涨{ta}%"
        tail_down2 = f"仅涨{ta}%"
        tail_phrase = f"仅涨{ta}%"
    if platform == 'xhs':
        titles = [
            f"同样是这个市场，{sy}年至今差距有多大？这张收益榜我直接存了📊",
            f"{s['n']}个标的{sy}至今累计收益：{lead[0]}涨{la}%，{tail[0]}{tail_phrase}",
            f"选对赛道有多重要？一张动态图看懂这几年的分化🏁",
            f"老股民私藏｜{lead[0]}累计{la}%，{tail[0]}{tail_down2}，差距太真实",
            f"{span}年长跑谁在领跑？{lead[0]}用{la}%告诉你答案",
        ]
        topics = topics_for_title(title, 'cumul')
        jump = s['best_jump']
        jump_line = ""
        if jump and abs(jump[2]) >= 30:
            jump_line = (f"{jump[0]}在{jump[1]}一年累计跳升约{fmt_abs(jump[2])}个百分点，"
                         f"直接把差距拉开。\n\n")
        intro = (
            f"用公开数据跑一场从{sy}年至今的收益竞速🏁 {span}年下来，"
            f"{lead[0]}累计涨了{la}%，而{tail[0]}{tail_down}，选对和选错，结局天差地别。\n\n"
            f"{jump_line}"
            f"这份动态榜单建议收藏对照，一眼看清谁在领跑👇")
    else:
        titles = [
            f"{sy}年至今，{title}累计收益全景",
            f"{lead[0]}领跑、{tail[0]}垫底：一张图看懂分化",
            f"近{span}年收益榜：头部与尾部标的差距显著",
        ]
        topics = topics_for_title(title, 'cumul')
        intro = (
            f"本文用公开数据，呈现{sy}年至今的累计收益竞速。"
            f"{lead[0]}以{la}%领跑，{tail[0]}累计{ta}%垫底，分化显著，供对照参考。")
    return titles, topics, intro


# ---------------- cumul 模式（绝对单位，如「亿元」财富竞速）文案 ----------------
# 与「累计涨跌幅(%)」cumul 不同：绝对单位的 cumul（如富豪财富）应按「财富排行竞速」叙述，
# 严禁把数值当百分比（曾误写「钟睒睒累计涨5300%」）。所有数字均为真实财富（亿元）。
def _present(v):
    """CSV 缺值记 0.0，0 视为「当年未上榜」，不作为有效财富参与排名。"""
    return (v or 0) > 0


def _present_at(v, dec=0):
    """在展示精度下仍能读出非零值。

    _present 只判断 >0，但一个 0.003 TWh 的实体（法国天然气产量）虽然 >0，
    按 decimals=0 展示就是 "0"，被写进出口播就成了「法国以0排在最后」这类
    既无信息量又像 bug 的句子。排名统计（尤其 tail）应当跳过它们。
    """
    if not _present(v):
        return False
    # 阈值取「该精度下的 1 个单位」而非 0.5：0.5 是 Python 银行家舍入的边界，
    # f"{0.5:,.0f}" 得到 "0"，于是 0.5 亿的实体会通过检查、却以「0亿美元排在最后」
    # 的病句形式出现（矿业榜的 MP 材料就是这么翻车的）。取 1.0 才能保证读出非零。
    return abs(v) >= 1.0 / (10 ** int(dec or 0))


def _granularity(label):
    """判断时间标签粒度：'year' / 'quarter' / 'month'。

    数据不一定是年度的——深交所地区成交额是月度（'2026-07'）、美股财报是季度（'2025Q4'）。
    文案里若一律写「{标签}年」，就会念出「从2004-12年到2026-07年」这种病句。
    """
    s = str(label)
    if len(s) == 4 and s.isdigit():
        return 'year'
    if len(s) == 6 and s[:4].isdigit() and s[4] in 'Qq' and s[5].isdigit():
        return 'quarter'
    if len(s) == 7 and s[:4].isdigit() and s[4] == '-' and s[5:].isdigit():
        return 'month'
    return 'other'


def _ylabel(label):
    """给时间标签补量词：年度补「年」，月度/季度不加（它们自带月份或季度后缀）。"""
    return f"{label}年" if _granularity(label) == 'year' else str(label)


def _step_word(label):
    """单个时间步长的中文说法：用于「在 XXXX 一{步}就跳升了 Y」。"""
    return {'year': '一年', 'quarter': '一个季度', 'month': '一个月'}.get(
        _granularity(label), '一年')


def compute_cumul_abs_stats(data):
    years = data['years']
    labels = data.get('year_labels', {})
    dec = data.get('meta', {}).get('decimals', 0)
    first, last = years[0], years[-1]
    last_label = labels.get(last, last)

    def val_at(it, y):
        return it['values'].get(y)

    # 用 _present_at（展示精度感知）而非 _present：四舍五入后显示为 0 的实体
    # 不该占据「第一名 / 最后一名」的叙事位置
    last_rows = [(it['name'], val_at(it, last)) for it in data['industries']
                 if _present_at(val_at(it, last), dec)]
    last_rows.sort(key=lambda x: x[1], reverse=True)
    lead = last_rows[0] if last_rows else (None, None)
    tail = last_rows[-1] if last_rows else (None, None)

    first_rows = [(it['name'], val_at(it, first)) for it in data['industries']
                  if _present_at(val_at(it, first), dec)]
    first_rows.sort(key=lambda x: x[1], reverse=True)
    first_lead = first_rows[0] if first_rows else (None, None)

    lead_gap = (lead[1] - tail[1]) if (lead[1] is not None and tail[1] is not None) else None

    # 最大单年财富跳升（连续两年均上榜）；记录起止年用于措辞（连续年 vs 跨年）
    best = None
    for it in data['industries']:
        for i in range(1, len(years)):
            y0, y1 = years[i - 1], years[i]
            v0, v1 = val_at(it, y0), val_at(it, y1)
            if not (_present(v0) and _present(v1)):
                continue
            j = v1 - v0
            if best is None or abs(j) > abs(best[2]):
                best = (it['name'], labels.get(y1, y1), j, labels.get(y0, y0))

    # 掉队最狠：曾登顶（历史最佳排名=1）但末年已跌出榜单，取峰值最高者
    faller = None
    for it in data['industries']:
        best_rank, peak_val, peak_year = None, None, None
        for y in years:
            vs = [(o['name'], val_at(o, y)) for o in data['industries'] if _present(val_at(o, y))]
            vs.sort(key=lambda x: x[1], reverse=True)
            try:
                rk = vs.index((it['name'], val_at(it, y))) + 1
            except ValueError:
                continue
            if best_rank is None or rk < best_rank:
                best_rank = rk
            if peak_val is None or val_at(it, y) > peak_val:
                peak_val = val_at(it, y)
                peak_year = y
        if best_rank == 1 and not _present(val_at(it, last)):
            if faller is None or peak_val > faller[2]:
                faller = (it['name'], peak_year, peak_val)
    return {
        'first': first, 'last': last, 'last_label': last_label,
        'span': year_int(last) - year_int(first),
        'n': len(data['industries']),
        'decimals': dec,
        'first_lead': first_lead, 'lead': lead, 'tail': tail,
        'lead_gap': lead_gap, 'best_jump': best, 'faller': faller,
    }


def narration_cumul_abs(title, s, unit, dec=0):
    sy, ly = s['first'], s['last_label']
    fl, ld, tl = s['first_lead'], s['lead'], s['tail']
    u = unit

    def v(x):
        return f"{fmt_abs(x, dec)}{u}"

    # 单系列（只有 1 个实体，如全国总人口）：走势叙事
    if s['n'] == 1:
        lines = [f"从{_ylabel(sy)}到{_ylabel(ly)}，{ld[0]}的走势是这样的。"]
        fv, lv = fl[1], ld[1]
        delta = (lv or 0) - (fv or 0)
        if delta:
            lines.append(f"从{v(fv)}到{v(lv)}，整体{'增加' if delta > 0 else '减少'}了{fmt_abs(delta, dec)}{u}。")
        jump = s['best_jump']
        if jump and abs(jump[2]) >= 1:
            jname, jlyr, jval, jeyr = (jump + (None,))[:4]
            if jeyr and year_int(jlyr) - year_int(jeyr) == 1:
                lines.append(f"其中{_ylabel(jlyr)}{_step_word(jlyr)}就变化约{fmt_abs(jval, dec)}{u}。")
            else:
                lines.append(f"其中从{_ylabel(jeyr) if jeyr else '起始'}到{_ylabel(jlyr)}累计变化约{fmt_abs(jval, dec)}{u}。")
        return "\n".join(lines)

    # 单一年份（只有 1 年，如单年排名）：静态排位
    if s['span'] == 0:
        lines = [f"这是{ly}年的排位一览。"]
        if ld[0]:
            lines.append(f"{ld[0]}以{v(ld[1])}登顶，{tl[0]}以{v(tl[1])}垫底。")
        if s['lead_gap'] is not None:
            lines.append(f"一头一尾相差{fmt_abs(s['lead_gap'], dec)}{u}。")
        return "\n".join(lines)

    # 多年份多实体：通用竞速叙事（不绑定「富豪/财富」等专属词）
    lines = [f"从{_ylabel(sy)}到{_ylabel(ly)}，我们用动态榜单跑了一场排位竞速。"]
    if fl[0] and ld[0] and fl[0] != ld[0]:
        lines.append(
            f"{_ylabel(sy)}还是{fl[0]}以{v(fl[1])}领跑，到了{_ylabel(ly)}，"
            f"头把交椅已经换成了{ld[0]}（{v(ld[1])}）。")
    elif ld[0]:
        lines.append(f"到了{_ylabel(ly)}，{ld[0]}以{v(ld[1])}登顶。")
    if s['faller']:
        fn, pyr, pv = s['faller']
        lines.append(f"反观{fn}，{pyr}年还以{v(pv)}排在第一，到{ly}年已跌出榜单——掉得最狠。")
    if tl[0] and (not fl[0] or tl[0] != ld[0]):
        lines.append(f"而{tl[0]}以{v(tl[1])}排在最后。")
    jump = s['best_jump']
    gap = s['lead_gap']
    if jump and abs(jump[2]) >= 1:
        jname, jlyr, jval, jeyr = jump
        verb = '跳升' if jump[2] > 0 else '回落'
        if jeyr and year_int(jlyr) - year_int(jeyr) == 1:
            jump_txt = f"其中{jname}在{_ylabel(jlyr)}{_step_word(jlyr)}就{verb}约{fmt_abs(jval, dec)}{u}"
        else:
            jump_txt = f"其中{jname}从{_ylabel(jeyr) if jeyr else '起始'}到{_ylabel(jlyr)}累计{verb}约{fmt_abs(jval, dec)}{u}"
        lines.append(
            f"{jump_txt}，"
            f"把分化彻底坐实——头尾之间，已经隔出{fmt_abs(gap, dec) if gap is not None else '巨大'}{u}的鸿沟。")
    elif gap is not None:
        lines.append(f"一头一尾的差距，也拉到了{fmt_abs(gap, dec)}{u}。")
    return "\n".join(lines)


def copy_cumul_abs(title, s, unit, platform, dec=0):
    sy, ly = s['first'], s['last_label']
    span = s['span']
    ld, tl = s['lead'], s['tail']
    la = fmt_abs(ld[1], dec) if ld[1] is not None else '0'
    ta = fmt_abs(tl[1], dec) if tl[1] is not None else '0'
    fn = s['faller']
    u = unit
    single_year = (span == 0)
    single_ent = (s['n'] == 1)
    span_txt = (f"{span}年" if not single_year else f"{ly}年")
    if platform == 'xhs':
        if single_year:
            titles = [
                f"这是{ly}年的排位一览📊",
                f"{ld[0]} {la}{u}登顶，{tl[0]}垫底",
                f"一张图看懂{ly}年的头部与尾部🏁",
                f"{ld[0]}领跑，{tl[0]}垫底，差距太真实",
                f"{ly}年座次：{ld[0]}用{la}{u}告诉你答案",
            ]
        elif single_ent:
            titles = [
                f"从{sy}到{ly}，{ld[0]}的走势我直接存了📊",
                f"{ld[0]}从{sy}到{ly}：{la}{u}",
                f"一张动态图看懂{ld[0]}的变化🏁",
                f"老股民私藏｜{ld[0]}的{sy}–{ly}走势",
                f"{sy}到{ly}，{ld[0]}用数据说话",
            ]
        else:
            titles = [
                f"从{sy}到{ly}，这份动态榜单建议收藏📊",
                f"{s['n']}个选手{span}年竞速：{ld[0]} {la}{u}登顶，{tl[0]}垫底",
                f"选对赛道有多重要？一张动态图看懂分化🏁",
                f"一张图看懂谁在领跑｜{ld[0]} {la}{u}登顶，{(fn[0] if fn else tl[0])}掉队",
                f"{span}年长跑谁在领跑？{ld[0]}用{la}{u}告诉你答案",
            ]
        topics = topics_for_title(title, 'value')  # 按标题关键词命中（市值/营收/薪酬/人口/城市/电影/票房/财富/大学…）
        jump = s['best_jump']
        jump_line = ""
        if jump and abs(jump[2]) >= 1:
            jname, jlyr, jval, jeyr = jump
            verb = '跳升' if jump[2] > 0 else '回落'
            if jeyr and year_int(jlyr) - year_int(jeyr) == 1:
                jump_line = (f"{jname}在{_ylabel(jlyr)}{_step_word(jlyr)}就{verb}约{fmt_abs(jval, dec)}{u}，"
                             f"直接把差距拉开。\n\n")
            else:
                jump_line = (f"{jname}从{_ylabel(jeyr) if jeyr else '起始'}到{_ylabel(jlyr)}累计{verb}约{fmt_abs(jval, dec)}{u}，"
                             f"直接把差距拉开。\n\n")
        if single_ent:
            intro = (
                f"用公开数据看{ld[0]}从{sy}到{ly}的走势🏁\n\n"
                f"{jump_line}"
                f"这份动态轨迹建议收藏对照，一眼看清变化👇")
        else:
            intro = (
                f"用公开数据跑一场从{sy}到{ly}的竞速🏁 {span_txt}下来，"
                f"{ld[0]}以{la}{u}领跑，而{tl[0]}以{ta}{u}垫底，选对和选错，结局天差地别。\n\n"
                f"{jump_line}"
                f"这份动态榜单建议收藏对照，一眼看清谁在领跑👇")
    else:
        if single_year:
            titles = [
                f"{ly}年{title}排位全景",
                f"{ld[0]}领跑、{tl[0]}垫底：一张图看懂{ly}年分化",
                f"{ly}年榜单：头部与尾部差距显著",
            ]
        elif single_ent:
            titles = [
                f"{sy}年至今，{title}全景",
                f"{ld[0]}从{sy}到{ly}：{la}{u}",
                f"{ld[0]}{sy}–{ly}走势",
            ]
        else:
            titles = [
                f"{sy}年至今，{title}全景",
                f"{ld[0]}领跑、{tl[0]}垫底：一张图看懂分化",
                f"近{span}年榜单：头部与尾部差距显著",
            ]
        topics = topics_for_title(title, 'value')
        if single_ent:
            intro = (f"本文用公开数据，呈现{ld[0]}从{sy}年至今的走势，供对照参考。")
        else:
            intro = (
                f"本文用公开数据，呈现{sy}年至今的排位竞速。"
                f"{ld[0]}以{la}{u}领跑，{tl[0]}以{ta}{u}垫底，分化显著，供对照参考。")
    return titles, topics, intro


# ---------------- value 模式 stats / 文案 ----------------
def compute_value_stats(data):
    years = data['years']
    meta = data.get('meta', {})
    hl = meta.get('highlight') or None
    y0, y1 = years[0], years[-1]
    multi = len(years) > 1
    ents = {it['name']: it['values'] for it in data['industries']}

    def get(name, y):
        return ents.get(name, {}).get(y)

    ranked_last = sorted(data['industries'],
                         key=lambda it: get(it['name'], y1) or -1e9, reverse=True)
    lead = ranked_last[0]
    second = ranked_last[1] if len(ranked_last) > 1 else None
    margin = (get(lead['name'], y1) - get(second['name'], y1)) if second else None

    # 排名变化 / 反转 / 掉队 检测（仅多年度有意义）
    rank_y0 = rank_y1 = None
    leader0_name = leader1_name = None
    top_faller = top_riser = None
    if multi:
        def rank_at(y):
            order = sorted(data['industries'],
                          key=lambda it: get(it['name'], y) or -1e9, reverse=True)
            return {it['name']: i + 1 for i, it in enumerate(order)}
        rank_y0 = rank_at(y0)
        rank_y1 = rank_at(y1)
        order0 = sorted(data['industries'],
                        key=lambda it: get(it['name'], y0) or -1e9, reverse=True)
        leader0_name = order0[0]['name']
        leader1_name = lead['name']
        movers = []
        for it in data['industries']:
            r0 = rank_y0.get(it['name'])
            r1 = rank_y1.get(it['name'])
            if r0 and r1:
                movers.append((it['name'], r0, r1, r1 - r0))  # >0 掉队, <0 上升
        if movers:
            movers.sort(key=lambda x: x[3], reverse=True)
            if movers[0][3] >= 1:
                top_faller = movers[0]
            if movers[-1][3] <= -1:
                top_riser = movers[-1]

    # 鸿沟（最高 - 最低）
    def gap_at(y):
        vals = [get(it['name'], y) for it in data['industries']
                if get(it['name'], y) is not None]
        return (max(vals) - min(vals)) if len(vals) >= 2 else None
    gap_y0 = gap_at(y0) if multi else None
    gap_y1 = gap_at(y1)
    gap_ratio = (gap_y1 / gap_y0) if (gap_y0 not in (None, 0) and gap_y1 is not None) else None

    # 反超检测（仅 highlight 存在时，保留原逻辑）
    overtaken = overtake_year = None
    if hl:
        for i in range(1, len(years)):
            rk = sorted(data['industries'],
                        key=lambda it: get(it['name'], years[i]) or -1e9, reverse=True)
            if rk[0]['name'] == hl:
                prev = sorted(data['industries'],
                              key=lambda it: get(it['name'], years[i - 1]) or -1e9, reverse=True)
                if prev[0]['name'] != hl:
                    overtaken = prev[0]['name']
                    overtake_year = years[i]
                    break
        hl_rank = next(i for i, it in enumerate(ranked_last) if it['name'] == hl) + 1
        hl0, hl1 = get(hl, y0), get(hl, y1)
        mult = (hl1 / hl0) if (hl0 not in (None, 0)) else None
    else:
        hl_rank = None
        hl0 = hl1 = mult = None
    return {
        'hl': hl, 'y0': y0, 'y1': y1, 'years': years, 'multi': multi,
        'lead': (lead['name'], get(lead['name'], y1)),
        'second': ((second['name'], get(second['name'], y1)) if second else None),
        'margin': margin, 'overtaken': overtaken, 'overtake_year': overtake_year,
        'hl_rank': hl_rank, 'hl0': hl0, 'hl1': hl1, 'mult': mult,
        'unit': meta.get('unit', ''), 'title': meta.get('title', ''),
        'span': year_int(y1) - year_int(y0),
        'leader0_name': leader0_name, 'leader1_name': leader1_name,
        'top_faller': top_faller, 'top_riser': top_riser,
        'gap_y0': gap_y0, 'gap_y1': gap_y1, 'gap_ratio': gap_ratio,
    }


def narration_value(title, s):
    unit = s['unit']
    if s['hl']:
        hl = s['hl']
        lines = [
            f"从{s['y0']}年到{s['y1']}年，我们把「{s['title'].split('·')[0].strip()}」做成一场中外竞速，结局很提气。",
        ]
        if s['overtaken'] and s['overtake_year']:
            lines.append(
                f"早年的{s['y0']}年，{hl}只有{fmt_val(s['hl0'])}{unit}，{s['overtaken']}还遥遥领先；"
                f"到了{s['overtake_year']}年，{hl}完成反超，一路把差距拉开。")
        else:
            lines.append(
                f"从{s['y0']}到{s['y1']}，{hl}一路领跑，把外国同行越甩越远。")
        if s['mult'] and s['mult'] >= 2:
            lines.append(f"到最新，{hl}达到{fmt_val(s['hl1'])}{unit}，大约是{s['y0']}年的{int(round(s['mult']))}倍；")
        else:
            lines.append(f"到最新，{hl}达到{fmt_val(s['hl1'])}{unit}；")
        if s['second'] and s['margin'] is not None:
            lines.append(
                f"目前高居第{s['hl_rank']}，比第二的{s['second'][0]}还多出{fmt_val(s['margin'])}{unit}。"
                f"同一个赛道，沉下心搞制造，中国这二十年走出了自己的节奏。")
        else:
            lines.append(f"目前高居第{s['hl_rank']}。沉下心搞制造，中国这二十年走出了自己的节奏。")
    else:
        core = s['title'].split('·')[0].strip()
        lines = [f"一张动态榜单，看{core}。"]
        lines += _contrast_lines(s, unit)
        if not lines[-1].endswith('。'):
            lines[-1] += '。'
    return "\n".join(lines)


def copy_value(title, s, platform):
    unit = s['unit']
    if s['hl']:
        hl = s['hl']
        titles = [
            f"{hl}用{s['span']}年从跟跑变领跑：一张图看懂中外产业逆袭🏁",
            f"{s['overtaken']+'曾遥遥领先，如今被'+hl+'反超' if s['overtaken'] else hl+'一路领跑'}——这张榜太真实",
            f"数据不会骗人：{hl}在「{s['title'].split('·')[0].strip()}」上把外国甩开多远",
            f"大国重器｜{hl}{fmt_val(s['hl1'])}{unit}登顶，当年想都不敢想",
            f"同样是{s['title'].split('·')[0].strip()}，{hl}和外国差出几个身位？",
        ]
        kw_map = {
            '汽车': ['#中国汽车', '#新能源车'], '光伏': ['#中国光伏', '#新能源'],
            '盾构机': ['#盾构机', '#中国基建', '#工程机械'],
            '植树': ['#植树造林', '#绿水青山', '#生态中国'], '造林': ['#植树造林', '#绿水青山'],
            '造船': ['#中国造船', '#造船强国'], '高铁': ['#中国高铁', '#中国速度'],
            '大飞机': ['#大飞机', '#C919', '#中国制造'], '稀土': ['#稀土', '#中国制造'],
            '新能源': ['#新能源车', '#中国新能源'], '家电': ['#中国家电', '#出海'],
        }
        topics = []
        for k, v in kw_map.items():
            if k in s['title']:
                topics += v
                break
        topics += ['#中国制造', '#中国智造', '#工业明珠', '#大国重器', '#数据可视化']
        takeaway = (
            f"{hl}从{fmt_val(s['hl0'])}{unit}做到{fmt_val(s['hl1'])}{unit}"
            + (f"，约{int(round(s['mult']))}倍增长" if s['mult'] and s['mult'] >= 2 else "")
            + (f"，{s['overtake_year']}年反超{s['overtaken']}" if s['overtaken'] else "")
            + "。视频用金色标记中国，谁反超、谁掉队一眼看清👇")
        intro = (
            f"用公开数据跑一场「{s['title']}」的中外竞速🏁 从{s['y0']}到{s['y1']}，"
            f"{hl}从{fmt_val(s['hl0'])}{unit}干到{fmt_val(s['hl1'])}{unit}，"
            + (f"在{s['overtake_year']}年反超{s['overtaken']}、一路登顶。" if s['overtaken'] else "一路领跑。")
            + f"\n\n{takeaway}")
    else:
        lead, second, margin = s['lead'], s['second'], s['margin']
        titles = [
            f"{s['title']}：{lead[0]}以{fmt_val(lead[1])}{unit}登顶🏁",
            f"最新{s['title'].split('·')[0].strip()}：{lead[0]}领先{second[0] if second else ''}约{fmt_val(margin) if margin is not None else ''}{unit}",
            f"一张动态图看懂{s['title'].split('·')[0].strip()}：谁在领跑谁在掉队",
            f"{lead[0]}凭什么最强？这份榜单说清楚了",
            f"数据说话｜{s['title']} TOP 榜单，谁领跑谁掉队一目了然",
        ]
        # 题材关键词 -> 话题（按题材动态生成，避免千篇一律 #A股，2026-08-19 补全映射）
        t = s['title']
        if '概念' in t:
            topics = ['#A股', '#概念板块', '#题材炒作', '#数据可视化', '#理财干货',
                      '#投资理财', '#我的炒股日记']
        elif 'ETF' in t:
            topics = ['#ETF', '#指数基金', '#定投', '#数据可视化', '#理财干货',
                      '#投资理财', '#我的炒股日记']
        elif '基金' in t:
            topics = ['#基金', '#偏股基金', '#公募基金', '#数据可视化', '#理财干货',
                      '#投资理财', '#我的炒股日记']
        else:
            topics = topics_for_title(t, 'value')
        intro = (
            f"用公开数据跑一场「{s['title']}」🏁 "
            f"{lead[0]}以{fmt_val(lead[1])}{unit}高居第一"
            + (f"，比第二的{second[0]}领先约{fmt_val(margin)}{unit}" if second and margin is not None else "")
            + "。动态竞速，谁领跑谁掉队一眼看清👇")
    return titles, topics, intro


# ---------------- value 模式（国内多实体 / 自定义题材）泛化文案 ----------------
def narration_value_generic(title, s):
    """value 模式、非「中外逆袭」题材（如国内城市房价、人口数据）的通用叙事，
    避免把 highlight 当成「中国」去写「中外竞速 / 大国重器」而串味；
    口播统一走「对比 / 反差 / 反转」风格（见 _contrast_lines），无套话。"""
    unit = s['unit']
    core = s['title'].split('·')[0].strip()
    if s['hl']:
        hl = s['hl']
        lines = [f"从{s['y0']}年到{s['y1']}年，我们把「{core}」跑成了一场竞速，{hl}的表现最值得说。"]
        if s['hl0'] is not None and s['hl1'] is not None and (s['hl0'] or s['hl1']):
            lines.append(f"{hl}从{s['y0']}年的{fmt_val(s['hl0'])}{unit}，走到{s['y1']}年的{fmt_val(s['hl1'])}{unit}。")
        else:
            lines.append(f"到{s['y1']}年，{hl}来到{fmt_val(s['hl1'])}{unit}。")
        # 反差收尾：领先幅度 or 被谁甩开
        if s['hl_rank'] == 1:
            if s['margin'] is not None and s['second']:
                lines.append(f"它一路领跑、稳居第一，把第二的{s['second'][0]}甩开约{fmt_val(s['margin'])}{unit}。")
            else:
                lines.append("它一路领跑、稳居第一，把其他对手越甩越远。")
        else:
            lead, second, margin = s['lead'], s['second'], s['margin']
            extra = f"不过整场竞速的最终领跑者是{lead[0]}，达到{fmt_val(lead[1])}{unit}"
            if second and margin is not None:
                extra += (f"，比{hl}（第{s['hl_rank']}）多出约{fmt_val(margin)}{unit}"
                          f"——{hl}没能笑到最后。")
            else:
                extra += "。"
            lines.append(extra)
    else:
        lines = [f"一张动态榜单，看{core}。"]
        lines += _contrast_lines(s, unit)
        if not lines[-1].endswith('。'):
            lines[-1] += '。'
    return "\n".join(lines)


def copy_value_generic(title, s, platform):
    """value 模式（非中外逆袭）的小红书 / 公众号文案，按题材关键词智能选话题。"""
    unit = s['unit']
    core = s['title'].split('·')[0].strip()
    lead, second, margin = s['lead'], s['second'], s['margin']
    t = s['title']
    if '房价' in t or '楼市' in t:
        base = ['#房价', '#楼市', '#数据可视化', '#理财干货', '#房产']
    elif '结婚' in t:
        base = ['#结婚率', '#人口', '#数据可视化', '#社会观察']
    elif '生育' in t:
        base = ['#生育率', '#人口', '#数据可视化', '#社会观察']
    elif '收入' in t:
        base = ['#收入', '#数据可视化', '#民生观察']
    elif '城市' in t:
        base = ['#城市', '#数据可视化', '#区域发展']
    else:
        base = ['#财经', '#数据可视化', '#理财干货']
    if platform == 'xhs':
        titles = [
            f"{core}：一张动态图看懂谁在领跑🏁",
            f"{lead[0]}以{fmt_val(lead[1])}{unit}登顶，这份榜单太真实",
            f"数据不会骗人｜{core}，{lead[0]}把对手甩开多远",
            f"建议收藏｜{core}动态排行榜，谁领跑谁掉队一目了然",
            f"同样是{core}，{lead[0]}和{second[0] if second else '其他'}差出几个身位？",
        ]
        topics = base + ['#我的数据日记', '#干货分享']
        intro = (
            f"用公开数据跑一场「{s['title']}」🏁 "
            f"从{s['y0']}到{s['y1']}，{lead[0]}以{fmt_val(lead[1])}{unit}高居第一"
            + (f"，比第二的{second[0]}领先约{fmt_val(margin)}{unit}" if second and margin is not None else "")
            + "。动态竞速，谁领跑谁掉队一眼看清👇")
    else:
        titles = [
            f"{s['title']}：动态竞速全景",
            (f"{lead[0]}领跑、{second[0]}紧随：一张图看懂分化" if second
             else f"{lead[0]}领跑：一张图看懂{s['title']}"),
            f"近{s['span']}年榜单：头部与尾部差距显著",
        ]
        topics = base
        intro = (
            f"本文用公开数据，呈现{s['title']}的动态竞速。"
            f"{lead[0]}以{fmt_val(lead[1])}{unit}领跑"
            + (f"，{second[0]}以{fmt_val(second[1])}{unit}紧随" if second else "")
            + "，供对照参考。")
    return titles, topics, intro


# ---------------- 单实体(单序列)题材：CPI/GDP/利率等 ----------------
def _single_series(data):
    """单实体题材：返回 (name, y0, y1, v0, v1, chg, pct)。"""
    years = data['years']
    it = data['industries'][0]
    vals = it['values']
    y0, y1 = years[0], years[-1]
    v0, v1 = vals.get(y0), vals.get(y1)
    chg = None if (v0 is None or v1 is None) else (v1 - v0)
    pct = None if (v0 in (None, 0) or chg is None) else (chg / v0 * 100.0)
    return it['name'], y0, y1, v0, v1, chg, pct


def narration_single(meta, name, y0, y1, v0, v1, chg, pct):
    unit = meta.get('unit', '') or ''
    src = meta.get('src', '')
    if v0 is None or v1 is None:
        return f"{meta.get('title', '')}。数据有限，详见图表。数据来源：{src}。"
    if pct is not None:
        trend = f"累计{'上升' if chg >= 0 else '下降'}{abs(pct):.1f}%"
    elif chg is not None:
        trend = f"变化{fmt_val(chg)}{unit}"
    else:
        trend = "趋势清晰可见"
    return (f"{meta.get('title', '')}。从{y0}年的{fmt_val(v0)}{unit}，"
            f"到{y1}年的{fmt_val(v1)}{unit}，{trend}。"
            f"数据来源：{src}。")


def copy_single(meta, name, y0, y1, v0, v1, chg, pct, platform):
    unit = meta.get('unit', '') or ''
    title = meta.get('title', '')
    titles = [
        f"{y0}→{y1}：一张图看懂{title}",
        f"{title}这些年怎么变？一眼看清",
        f"一张图看懂：{title}（{y0}–{y1}）",
    ]
    topics = ["#财经", "#数据可视化", "#一张图看懂"]
    kw = {'CPI': '#CPI', 'PPI': '#PPI', 'GDP': '#GDP', '房价': '#房价',
          '人口': '#人口', '利率': '#利率', '存款': '#存款'}
    for k, v in kw.items():
        if k in title:
            topics.append(v)
            break
    v0s = fmt_val(v0) if v0 is not None else '—'
    v1s = fmt_val(v1) if v1 is not None else '—'
    if platform == 'wechat':
        intro = (f"用公开数据，呈现{y0}至{y1}年的{title}走势。"
                 f"从{v0s}{unit}到{v1s}{unit}，"
                 f"趋势一目了然，供对照参考。")
    else:
        intro = (f"用公开数据跑一张「{title}」动态图🏁 "
                 f"从{y0}年的{v0s}{unit}，"
                 f"到{y1}年的{v1s}{unit}，"
                 f"趋势一目了然👇")
    return titles, topics, intro


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--src', default='data/finance.json')
    ap.add_argument('--platform', choices=PLATFORMS, default='xhs')
    ap.add_argument('--out-prefix', default=None,
                    help='输出文件前缀（如 topic_cn_top30_houseindex）；'
                         '不传则写默认 data/narration.txt / post_meta.json / post_meta.txt')
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    src = a.src if os.path.isabs(a.src) else os.path.join(ws, a.src)
    if not os.path.exists(src):
        raise SystemExit(f"ERROR: 找不到 {src}，请先跑 collect_finance.py")

    data = json.load(open(src, encoding='utf-8'))
    meta = data.get('meta', {})
    mode = meta.get('mode', 'cumul')
    ents = data.get('industries', [])

    if len(ents) == 1:
        # 单实体(单序列)题材：CPI/GDP/利率等，不应套用「竞速/高居第一」叙事
        name, y0, y1, v0, v1, chg, pct = _single_series(data)
        titles, topics, intro = copy_single(meta, name, y0, y1, v0, v1, chg, pct, a.platform)
        narration = narration_single(meta, name, y0, y1, v0, v1, chg, pct)
        kind = mode
        race_type = meta.get('race_type', 'single')
        extra_stats = {'single': True, 'name': name, 'y0': y0, 'y1': y1,
                       'v0': v0, 'v1': v1,
                       'pct': (round(pct, 2) if pct is not None else None)}
    elif mode == 'cumul':
        unit = meta.get('unit', '')
        metric_kind = meta.get('metric_kind', '')
        # 绝对单位（如「亿元」）或 比率/水平型 % 指标（如 M2/GDP 占比，柱长即真实比重）：
        # 按「从X到Y」的真实水平叙述，严禁当累计涨跌幅(%)（曾误写「新加坡累计仅涨%」）。
        # 只有 unit='%' 且 metric_kind 未标记 level 的，才走标准「累计收益」分支（申万行业等真实涨跌幅）。
        if unit not in ('', '%') or metric_kind == 'level':
            s = compute_cumul_abs_stats(data)
            dec = s.get('decimals', 0)
            titles, topics, intro = copy_cumul_abs(meta.get('title', '财富竞速'), s, unit, a.platform, dec)
            narration = narration_cumul_abs(meta.get('title', ''), s, unit, dec)
            kind = 'cumul'
            race_type = 'cumul_abs'
            extra_stats = {'lead': {'name': s['lead'][0], 'val': s['lead'][1]},
                           'tail': {'name': s['tail'][0], 'val': s['tail'][1]},
                           'first_lead': {'name': s['first_lead'][0], 'val': s['first_lead'][1]},
                           'faller': (s['faller'][0] if s['faller'] else None),
                           'best_jump': (s['best_jump'][0] if s['best_jump'] else None),
                           'range': f"{s['first']}→{s['last_label']}", 'n': s['n'],
                           'unit': unit}
        else:
            s = compute_cumul_stats(data)
            titles, topics, intro = copy_cumul(meta.get('title', '累计收益竞速'), s, a.platform)
            narration = narration_cumul(meta.get('title', ''), s)
            kind = 'cumul'
            race_type = meta.get('race_type', 'cumul')
            extra_stats = {'lead': {'name': s['lead'][0], 'cumul': s['lead'][1]},
                           'tail': {'name': s['tail'][0], 'cumul': s['tail'][1]},
                           'best_jump': (s['best_jump'][0] if s['best_jump'] else None),
                           'range': f"{s['first']}→{s['last_label']}", 'n': s['n']}
    else:
        s = compute_value_stats(data)
        race_type = meta.get('race_type', 'general')
        # 有 highlight 且非「中外逆袭」题材 -> 用泛化叙事（国内城市/人口等，避免大国重器串味）；
        # 其余（无 highlight 的概念/ETF/基金，或显式 race_type=cn_vs_world）沿用原叙事。
        if s['hl'] and race_type != 'cn_vs_world':
            titles, topics, intro = copy_value_generic(meta.get('title', '价值对比竞速'), s, a.platform)
            narration = narration_value_generic(meta.get('title', ''), s)
        else:
            titles, topics, intro = copy_value(meta.get('title', '价值对比竞速'), s, a.platform)
            narration = narration_value(meta.get('title', ''), s)
        kind = 'value'
        extra_stats = {'highlight': s['hl'], 'race_type': race_type,
                       'lead': {'name': s['lead'][0], 'val': s['lead'][1]},
                       'second': ({'name': s['second'][0], 'val': s['second'][1]} if s['second'] else None),
                       'overtaken': s['overtaken'], 'overtake_year': s['overtake_year'],
                       'growth_x': (round(s['mult'], 1) if s['mult'] else None)}

    meta_out = {
        'platform': a.platform, 'kind': kind, 'mode': mode, 'race_type': race_type,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'titles': titles, 'topics': topics, 'intro': intro,
        'stats': extra_stats,
    }

    prefix = a.out_prefix
    if prefix:
        nar_path = os.path.join(ws, 'data', f'{prefix}_narration.txt')
        jpath = os.path.join(ws, 'data', f'{prefix}_post_meta.json')
        tpath = os.path.join(ws, 'data', f'{prefix}_post_meta.txt')
    else:
        nar_path = os.path.join(ws, 'data', 'narration.txt')
        jpath = os.path.join(ws, 'data', 'post_meta.json')
        tpath = os.path.join(ws, 'data', 'post_meta.txt')
    with open(nar_path, 'w', encoding='utf-8') as f:
        f.write(narration + "\n")
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=2)
    with open(tpath, 'w', encoding='utf-8') as f:
        f.write(f"平台：{('小红书' if a.platform == 'xhs' else '公众号')}  |  生成于 {meta_out['generated_at']}\n")
        f.write(f"题材/标题：{meta.get('title','')}（mode={mode}）\n")
        f.write("=" * 40 + "\n\n")
        f.write("【口播稿】\n" + narration + "\n\n")
        f.write("【标题候选】（挑一个用）\n")
        for i, t in enumerate(titles, 1):
            f.write(f"{i}. {t}\n")
        f.write("\n【话题 / 标签】\n")
        f.write("  ".join(topics) + "\n\n")
        f.write("【简介】\n")
        f.write(intro + "\n")

    print("wrote", nar_path)
    print("wrote", jpath, "/", tpath)
    print("--- 口播稿 ---\n" + narration)
    print("--- 简介 ---\n" + intro)


if __name__ == '__main__':
    main()
