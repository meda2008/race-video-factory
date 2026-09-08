#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""读取收益/对比 JSON，生成竞速动画 HTML（out/race.html）。

两种模式：
- cumul（默认）：累计涨跌幅，0 轴=盈亏平衡，红右绿左（申万行业用）。
- value：绝对数值对比（如「中国 vs 外国」各行业指标），柱从左侧起，
         被 --highlight 指定的行（如 中国）金色高亮 + ★，按数值排名发奖牌。

展示文案（标题/副标题/单位/图例/来源/高亮/模式）优先取命令行参数，
其次取输入 JSON 的 meta 字段，最后回退到申万默认值 —— 因此现有申万流程不变。

用法：
  python build_race.py --workspace <ws> [--data sw_industry_cumul.json] [--out out/race.html] [--span 12.0]
  python build_race.py --workspace <ws> --data cn_world.json --mode value --highlight 中国
"""
import argparse, json, os, re, shutil

INTRO, FINALHOLD, FPS = 0.7, 1.5, 30

# 图标 + 边框色：优先用 emoji_lib（覆盖国别/公司/品牌/省份的图标+主色），
# 找不到时根据行业特征自动分桶，保留少量申万行业的兜底（兼容老用法）。
import emoji_lib

LEGACY_SW_EMOJI = {    # 申万行业兼容：emoji_lib 没收录时再用
    "农林牧渔": "🌾", "基础化工": "🧪", "钢铁": "🔩", "有色金属": "🪙", "电子": "💡",
    "家用电器": "📺", "食品饮料": "🥤", "纺织服饰": "👕", "轻工制造": "🪑", "医药生物": "💊",
    "公用事业": "🔌", "交通运输": "🚚", "房地产": "🏘️", "商贸零售": "🛒", "社会服务": "🤝",
    "综合": "🌀", "建筑材料": "🏗️", "建筑装饰": "🏛️", "电力设备": "🔋", "国防军工": "🛡️",
    "计算机": "💻", "传媒": "🎬", "通信": "📡", "银行": "🏦", "非银金融": "📈",
    "汽车": "🚗", "机械设备": "⚙️", "煤炭": "⛏️", "石油石化": "🛢️", "环保": "♻️",
    "美容护理": "💄",
}


def _find_logo(ws, name):
    """查找已下载的真实 logo（SimpleIcons 品牌标 / FlagCDN 国旗）。

    查两个位置，保证「一次下载、多项目复用」：
      1) <ws>/assets/logos/          项目私有
      2) <skill>/assets/logos/       skill 全局（fetch_logos.py 的默认输出目录）

    race.html 在 <ws>/out/，项目内的用 ../assets/... 相对路径；
    skill 目录的用 file:/// 绝对路径（file:// 下两者都能加载）。
    找不到返回 None，由调用方回退到 emoji。
    """
    import re as _re
    import urllib.parse as _up

    # 2026-09-06：CSV 实体名统一中文化后，logo 文件仍按英文原名命名
    # （如 美国 -> united_states.png / 苹果 -> apple.svg），故逐个尝试英文候选。
    cands = [name]
    try:
        import entity_cn as _EC
        if _re.search(r'[\u4e00-\u9fff]', str(name)):
            cands += _EC.en_candidates(name)
            cands.append(_EC.en_name(name))
    except Exception:                                 # noqa: BLE001
        pass

    for nm in cands:
        s = _re.sub(r'[^0-9A-Za-z]+', '_', str(nm)).strip('_')
        if not s:
            s = 'u' + _up.quote(str(nm), safe='').replace('%', '')[:24]
        s = s.lower()
        # 1) 项目内
        for ext in ('svg', 'png'):
            p = os.path.join(ws, 'assets', 'logos', f'{s}.{ext}')
            if os.path.exists(p):
                return f'../assets/logos/{s}.{ext}'
        # 2) skill 全局（assets 在 skill 根目录，即 scripts 的上一级）
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for ext in ('svg', 'png'):
            p = os.path.join(skill_dir, 'assets', 'logos', f'{s}.{ext}')
            if os.path.exists(p):
                return 'file:///' + p.replace('\\', '/')
    return None
    return None


def resolve(meta, arg, key, default):
    if arg is not None:
        return arg
    if meta and key in meta and meta[key]:
        return meta[key]
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--data', default='sw_industry_cumul.json')
    ap.add_argument('--out', default='out/race.html')
    ap.add_argument('--span', type=float, default=12.0)
    ap.add_argument('--title', default=None)
    ap.add_argument('--subtitle', default=None)
    ap.add_argument('--unit', default=None)
    ap.add_argument('--highlight', default=None)
    ap.add_argument('--mode', default=None, choices=['cumul', 'value'])
    ap.add_argument('--legend', default=None)
    ap.add_argument('--src', default=None)
    ap.add_argument('--bg-image', default=None,
                    help='gpt-image-2 生成的背景图路径；提供后替换为 AI 画面打底'
                         '（隐藏 skyline/网格、加暗角以保证文字清晰）')
    ap.add_argument('--decimals', type=int, default=None,
                    help='数值小数位（value 模式用）。不传则：%%->1，空单位->2，其他->0')
    ap.add_argument('--timeline', default=None,
                    help='gen_timeline.py 生成的时间轴 JSON（[{t, year}]），覆盖默认匀速推进，'
                         '使画面年份随解说对齐')
    ap.add_argument('--theme', default=None,
                    help='主题色（finance/tech/energy/climate/consumer/humanity/'
                         'military/industry/transit/pharma），不传则按 meta.theme 或默认 finance')
    a = ap.parse_args()

    ws = os.path.abspath(a.workspace)
    data_path = a.data if os.path.isabs(a.data) else os.path.join(ws, 'data', a.data)
    out_html = a.out if os.path.isabs(a.out) else os.path.join(ws, a.out)
    SPAN = a.span

    with open(data_path, encoding='utf-8') as f:
        data = json.load(f)

    meta = data.get('meta', {})
    title = resolve(meta, a.title, 'title', 'A股行业累计收益竞速')
    subtitle = resolve(meta, a.subtitle, 'subtitle', '申万一级行业 · 累计涨跌幅 · 红涨绿跌')
    unit = resolve(meta, a.unit, 'unit', '%')
    highlight = resolve(meta, a.highlight, 'highlight', None)
    mode = resolve(meta, a.mode, 'mode', 'cumul')
    legend = resolve(meta, a.legend, 'legend',
                     '涨·向右（红） ｜ 跌·向左（绿） ｜ 柱长=累计涨跌幅（0轴=盈亏平衡）')
    src = resolve(meta, a.src, 'src',
                  '数据来源：akshare 申万一级行业指数 · 最后一年为至今(YTD) · 累计=起始年初复利至今')
    theme = resolve(meta, a.theme, 'theme', 'finance')

    # AI 背景图：拷贝到 out/ 同目录（与 race.html 同目录，file:// 同目录可加载），由 HTML 引用
    bg_enabled = False
    if a.bg_image:
        if os.path.exists(a.bg_image):
            out_dir = os.path.dirname(out_html)
            bg_dest = os.path.join(out_dir, 'race_bg.jpg')
            os.makedirs(out_dir, exist_ok=True)
            shutil.copyfile(a.bg_image, bg_dest)
            bg_enabled = True
            print('[bg] AI 背景已注入 ->', bg_dest)
        else:
            print('[bg] 警告：--bg-image 指定的文件不存在，回退 CSS 渐变：', a.bg_image)

    years = data['years']
    # 防御：year_labels 可能不完整（如数据追加了新年份却未同步标签，会导致年度徽标空白）。
    # 先给每个年份兜底标签（=年份键），再用显式标签覆盖，确保年度徽标永不空白。
    ylabels = {y: y for y in years}
    ylabels.update(data.get('year_labels') or {})
    industries = data['industries']

    # 解说驱动时间轴：把 {t, year} 映射为「时间->年份索引」的分段线性插值，注入前端
    timeline_data = None
    if a.timeline:
        with open(a.timeline, encoding='utf-8') as _tf:
            _tl = json.load(_tf)
        # 把解说里的「年份整数」映射到时间轴上的索引：取该年最后一个(季度)标签。
        # 兼容纯年份标签("1960")与季度标签("1950Q4")两种格式。
        def _year_to_idx(yint):
            ys = str(yint)
            cands = [i for i, yv in enumerate(years) if str(yv).startswith(ys)]
            if cands:
                return cands[-1]
            # 退化：找 <= 该年的最大标签
            best = None
            for i, yv in enumerate(years):
                if str(yv)[:4] <= ys:
                    best = i
            return best
        # 新格式：{"t", "idx"} 直接是数据索引，任意粒度通用（月度/季度/年度）
        # 旧格式：{"t", "year"} 是年份整数，回退 _year_to_idx 兼容
        def _idx_of(p):
            i = p.get('idx')
            if isinstance(i, int) and 0 <= i < len(years):
                return i
            return _year_to_idx(p.get('year'))
        _pts = []
        for p in _tl:
            idx = _idx_of(p)
            if idx is not None:
                _pts.append([p['t'], idx])
        _pts.sort(key=lambda x: x[0])
        if _pts:
            timeline_data = _pts
            print('[timeline] 已加载 %d 个年份锚点，竞速改为解说驱动' % len(_pts))
    for it in industries:
        # 图标：优先真实 logo 图片（SimpleIcons 品牌标 / FlagCDN 国旗），
        # 其次 ISO2 代码（国别），最后 emoji（公司/品牌/申万行业）。
        # Windows Chrome 不渲染彩色国旗 emoji（显示成「US」字母），故国别优先取国旗图。
        icon = emoji_lib.icon_for(it['name'])
        if icon in ('', None) or icon == '?':
            icon = LEGACY_SW_EMOJI.get(it['name'], '▪')
        it['emoji'] = icon
        # emx 非空 → 末端徽章用它，且名称里不再重复显示前缀（避免「沪上海」「美美国」）。
        # 只有 emoji（公司/品牌图形）才在名称前再出现一次。
        it['emx'] = icon if re.search(r'[\u4e00-\u9fffA-Za-z]', str(icon)) else ''
        it['logo'] = _find_logo(ws, it['name'])
        # 边框主色：国别用国旗色（取双色代表色的首色），公司用行业色。
        # tint_for_country 对非国别题材会返回灰，默认值不能据此判定「不是国别」，
        # 故直接合并两条路径：先取国别，没有则取公司 emoji 的行业色。
        tc = emoji_lib.tint_for_country(it['name'])
        comp = emoji_lib.emoji(it['name'])
        # 国别灰（#888888）当作 fallback 信号；非国别应走到 emoji 路径
        if tc and tc[0].lower() != '#888888':
            it['tint'] = tc[0]
        else:
            it['tint'] = comp[2] if comp else '#94a3b8'

    max_abs = 1.0
    for it in industries:
        for y in years:
            v = it['values'].get(y)
            if v is not None:
                max_abs = max(max_abs, abs(v))

    # 「变化最突出的一个数据项」：首年→末年绝对变化最大的实体，给它在画面里特殊显示。
    # 只比较首尾都有值的实体，避免把「中途消失」的实体误判成变化最猛。
    mover = None
    best_delta = None
    for it in industries:
        vs = [it['values'].get(y) for y in years]
        fv = next((v for v in vs if v is not None), None)
        lv = next((v for v in reversed(vs) if v is not None), None)
        if fv is None or lv is None:
            continue
        d = abs(lv - fv)
        if best_delta is None or d > best_delta:
            best_delta, mover = d, it['name']

    total = INTRO + SPAN + FINALHOLD
    payload = {
        'years': years, 'ylabels': ylabels, 'industries': industries,
        'maxAbs': max_abs, 'total': total, 'intro': INTRO,
        'finalHold': FINALHOLD, 'fps': FPS,
        'mode': mode, 'unit': unit, 'highlight': highlight,
        'title': title, 'subtitle': subtitle, 'legend': legend, 'src': src,
        'bg': bg_enabled,
        'decimals': (a.decimals if a.decimals is not None else meta.get('decimals')),
        'timeline': timeline_data,
        'theme': theme,
        'mover': mover,
    }
    js_data = json.dumps(payload, ensure_ascii=False)
    html = HTML_TEMPLATE.replace('/*__DATA__*/', 'const PAYLOAD = ' + js_data + ';')

    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    print('wrote', out_html, 'mode=%s total=%.2fs frames=%d maxAbs=%.2f' %
          (mode, total, int(total * FPS), max_abs))


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>竞速图</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:1080px; height:1624px; overflow:hidden; }
  body {
    font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB","SimHei",sans-serif;
    background:
      radial-gradient(circle at 84% 8%, rgba(244,196,48,0.18), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(80,140,255,0.10), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #1d3056 0%, #0d1832 44%, #060b18 100%);
    color:#eaf0ff; position:relative;
  }
  /* ── 主题装饰图形：与题材相关的矢量插画，取代单调纯渐变 ── */
  .theme-deco { position:absolute; inset:0; z-index:0; pointer-events:none; opacity:0.26; }
  .theme-deco svg { width:1080px; height:1624px; }
  body.ai-bg .theme-deco { display:none; }   /* 有 AI 背景图时让位 */

  /* ── 主题背景：按题材类别切换，避免单调金蓝 ── */
  body.theme-tech {
    background:
      radial-gradient(circle at 84% 8%, rgba(106,108,255,0.20), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(170,100,255,0.12), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #2e1a4e 0%, #1a0d33 44%, #0a0518 100%); }
  body.theme-energy {
    background:
      radial-gradient(circle at 84% 8%, rgba(255,107,53,0.22), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(255,160,50,0.14), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #5c1a0a 0%, #2e0d0d 44%, #1a0808 100%); }
  body.theme-climate {
    background:
      radial-gradient(circle at 84% 8%, rgba(52,211,153,0.20), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(16,185,129,0.12), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #0a2e1a 0%, #0a1a14 44%, #05100a 100%); }
  body.theme-consumer {
    background:
      radial-gradient(circle at 84% 8%, rgba(245,158,11,0.22), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(251,191,36,0.14), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #4e2a1a 0%, #2e1a0a 44%, #1a0d05 100%); }
  body.theme-humanity {
    background:
      radial-gradient(circle at 84% 8%, rgba(244,196,48,0.22), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(168,85,247,0.12), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #2e1a3e 0%, #1a0a2e 44%, #0a0518 100%); }
  body.theme-military {
    background:
      radial-gradient(circle at 84% 8%, rgba(125,155,75,0.18), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(80,100,60,0.12), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #2e2e1a 0%, #1a1e0a 44%, #0a0d05 100%); }
  body.theme-industry {
    background:
      radial-gradient(circle at 84% 8%, rgba(180,83,9,0.18), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(120,53,15,0.12), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #2e2e2a 0%, #1a1a1a 44%, #0a0a0a 100%); }
  body.theme-transit {
    background:
      radial-gradient(circle at 84% 8%, rgba(56,189,248,0.22), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(14,165,233,0.14), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #0a2e3e 0%, #0a1a2e 44%, #051018 100%); }
  body.theme-pharma {
    background:
      radial-gradient(circle at 84% 8%, rgba(34,211,238,0.20), transparent 36%),
      radial-gradient(circle at 12% 22%, rgba(103,232,249,0.12), transparent 40%),
      radial-gradient(ellipse at 50% -10%, #0a2e2e 0%, #0a1e1e 44%, #051010 100%); }
  body::before {
    content:""; position:absolute; inset:0; pointer-events:none; z-index:0;
    background-image:
      linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size:60px 60px;
    -webkit-mask-image:radial-gradient(ellipse at 50% 42%, #000 50%, transparent 100%);
            mask-image:radial-gradient(ellipse at 50% 42%, #000 50%, transparent 100%);
  }
  body::after {
    content:""; position:absolute; inset:0; pointer-events:none; z-index:8;
    background:radial-gradient(ellipse at 50% 44%, transparent 56%, rgba(0,0,0,0.55) 100%);
  }
  .stage { position:absolute; inset:0; z-index:2; }

  .skyline { position:absolute; left:0; right:0; bottom:0; width:1080px; height:340px; z-index:1; opacity:0.9; }

  /* gpt-image-2 AI 背景：注入后 body.ai-bg 生效 */
  .bg-img { position:absolute; inset:0; z-index:0; display:none;
    background-size:cover; background-position:center; background-repeat:no-repeat; }
  body.ai-bg { background:#060b18; }
  body.ai-bg::before { display:none; }
  body.ai-bg .skyline { display:none; }
  body.ai-bg::after { background:radial-gradient(ellipse at 50% 42%,
      rgba(0,0,0,0.10) 24%, rgba(0,0,0,0.58) 72%, rgba(0,0,0,0.82) 100%); }

  .title-wrap { position:absolute; top:34px; left:0; right:0; text-align:center; z-index:6; }
  .title {
    font-size:64px; font-weight:800; letter-spacing:4px;
    background:linear-gradient(180deg,#fff6cf 0%,#f8d568 40%,#e8a916 72%,#b9780c 100%);
    -webkit-background-clip:text; background-clip:text; color:transparent;
    -webkit-text-stroke:1px rgba(255,240,180,0.25);
    text-shadow:0 3px 24px rgba(244,196,48,0.35);
  }
  .subtitle { margin-top:6px; font-size:22px; color:#a8bbe0; letter-spacing:1px; font-weight:400; }
  .gold-rule { width:600px; height:3px; margin:14px auto 0; border-radius:3px;
    background:linear-gradient(90deg,transparent,#f4c430 18%,#fff3c0 50%,#f4c430 82%,transparent);
    box-shadow:0 0 14px rgba(244,196,48,0.45); }

  .year-badge { position:absolute; right:54px; bottom:160px; z-index:3; text-align:right; line-height:1;
    transform-origin:right bottom; opacity:0.22; }
  .year-num { font-size:150px; font-weight:800; font-style:italic; letter-spacing:2px;
    background:linear-gradient(180deg,#fff3bf,#f4c430 58%,#c8901a);
    -webkit-background-clip:text; background-clip:text; color:transparent; }
  .year-cap { font-size:26px; color:#f4c430; letter-spacing:10px; margin-top:-10px; opacity:0.55; }

  .chart { position:absolute; left:0; right:0; top:250px; height:1240px; z-index:4; }
  .axis0 { position:absolute; left:640px; top:-6px; bottom:-6px; width:0;
    border-left:1px dashed rgba(255,255,255,0.28); }
  .axis0-label { position:absolute; left:640px; top:-30px; transform:translateX(-50%);
    font-size:16px; color:#9fb1d4; letter-spacing:1px; }
  .row { position:absolute; left:0; right:0; height:40px; will-change:top, display:flex; align-items:center;
    transition: top .45s cubic-bezier(.22,.61,.36,1); }
  .badge { position:absolute; left:30px; width:34px; height:34px; border-radius:50%;
    background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.20);
    display:flex; align-items:center; justify-content:center; font-size:17px; color:#d2dcf3; font-weight:700; }
  /* C. 名次方向箭头：▲=名次上升(涨) / ▼=名次下降(跌) / —=持平 —— 遵循 A股 红涨绿跌：▲红 ▼绿 */
  .delta { position:absolute; left:64px; top:50%; transform:translateY(-50%);
    width:22px; text-align:center; font-size:18px; font-weight:800; z-index:5; }
  .delta.up { color:#ff6b5e; text-shadow:0 0 8px rgba(255,107,94,0.6); }
  .delta.down { color:#43eaa0; text-shadow:0 0 8px rgba(67,234,160,0.6); }
  .delta.flat { color:#7f8db0; }
  .name { position:absolute; left:82px; width:236px; font-size:23px; font-weight:600; color:#eef3ff;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-shadow:0 1px 4px rgba(0,0,0,0.55); }
  .name .em { margin-right:7px; }
  .track { position:absolute; left:262px; width:598px; height:30px; border-radius:8px;
    background:rgba(255,255,255,0.04); }
  .bar { position:absolute; height:30px; border-radius:9px; width:0;
    box-shadow:inset 0 3px 6px rgba(255,255,255,0.28), inset 0 -5px 8px rgba(0,0,0,0.35),
               0 2px 10px rgba(0,0,0,0.30); }
  /* 柱子末端徽章：圆形 + 实体图标 + 国旗色/行业色边框；
     让「数据进度条末端」不再是单调白点，而是一个可视化的 logo */
  .bar-end { position:absolute; right:-18px; top:50%; transform:translateY(-50%);
    width:34px; height:34px; border-radius:50%; background:rgba(255,255,255,0.96);
    border:2.5px solid var(--tint, #f4c430);
    display:flex; align-items:center; justify-content:center;
    font-size:18px; font-weight:800; color:#1a2030;
    box-shadow:0 2px 6px rgba(0,0,0,0.35), 0 0 10px var(--tint, #f4c430);
    z-index:2; line-height:1; }
  .bar-end .glyph { font-size:20px; line-height:1;
    font-family:"Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji","Microsoft YaHei",sans-serif; }
  .bar-end .iso { font-size:14px; letter-spacing:-0.5px; font-weight:800; }
  .bar-end .lg { width:22px; height:22px; object-fit:contain; display:block; }
  /* 变化最突出项：末端徽章放大 + 双层光环 + 名称高亮，一眼锁定黑马（不显示文字标签） */
  .mover .bar-end { width:44px; height:44px; border-width:4px;
    box-shadow:0 0 0 3px rgba(255,255,255,0.9), 0 0 30px 10px rgba(255,221,0,0.9),
               0 3px 10px rgba(0,0,0,0.45); }
  .mover .bar-end .lg { width:28px; height:28px; }
  .mover .bar-end .glyph, .mover .bar-end .iso { font-size:24px; }
  .mover .name { color:#fff8d6; font-weight:800; text-shadow:0 0 12px rgba(244,196,48,0.7); }
  .bar::after { content:""; display:none; }   /* 旧白点已替换为 .bar-end */
  .val { position:absolute; text-align:left; font-size:23px; font-weight:800;
    font-variant-numeric:tabular-nums; letter-spacing:0.5px; text-shadow:0 1px 5px rgba(0,0,0,0.5); white-space:nowrap; }

  .lead .bar { box-shadow:inset 0 3px 6px rgba(255,255,255,0.3), inset 0 -5px 8px rgba(0,0,0,0.3),
    0 0 20px rgba(244,196,48,0.55); }
  /* 变化最突出项：数据条加黄色双描边外框 + 轻微脉冲，突出变化最猛的一项
     放在 .lead 之后定义，确保与第一名同行时外框优先生效 */
  .mover .bar { box-shadow:0 0 0 4px rgba(255,224,0,0.95),
    0 0 0 8px rgba(255,200,0,0.55), 0 0 26px 7px rgba(255,224,0,0.7),
    inset 0 3px 6px rgba(255,255,255,0.35), inset 0 -5px 8px rgba(0,0,0,0.3);
    animation:moverPulse 1.6s ease-in-out infinite; }
  @keyframes moverPulse { 0%,100%{ filter:brightness(1); } 50%{ filter:brightness(1.12); } }
  .lead .badge { background:linear-gradient(180deg,#fdf3c4,#f4c430); color:#3a2a00; border-color:#f4c430;
    box-shadow:0 0 16px rgba(244,196,48,0.6); }
  .medal-1 .badge { background:linear-gradient(180deg,#fff0b0,#f6c945); color:#5a3d00; border:1px solid #ffe089;
    box-shadow:0 0 16px rgba(246,201,69,0.7); }
  .medal-2 .badge { background:linear-gradient(180deg,#eef3fb,#c3ccd9); color:#2b3340; border:1px solid #eef3fb;
    box-shadow:0 0 14px rgba(195,204,217,0.6); }
  .medal-3 .badge { background:linear-gradient(180deg,#f4d9b8,#cd8b4e); color:#3a210c; border:1px solid #f4d9b8;
    box-shadow:0 0 14px rgba(205,139,78,0.6); }

  /* 中外对比：被高亮行（如中国）金色 + ★ */
  .cn .bar { box-shadow:inset 0 3px 6px rgba(255,255,255,0.3), inset 0 -5px 8px rgba(0,0,0,0.3),
    0 0 24px rgba(244,196,48,0.7); }
  .cn .badge { background:linear-gradient(180deg,#fff0b0,#f6c945); color:#5a3d00; border:1px solid #ffe089;
    box-shadow:0 0 18px rgba(246,201,69,0.85); }
  .cn .name { color:#fff3c0; }
  .cn .name::before { content:"★ "; color:#f4c430; font-weight:800; }

  .legend { position:absolute; bottom:70px; left:0; right:0; text-align:center; z-index:6;
    font-size:19px; color:#9fb1d4; letter-spacing:1px; }
  .src { position:absolute; bottom:28px; left:50%; transform:translateX(-50%); z-index:6;
    padding:8px 22px; border-radius:20px; background:rgba(255,255,255,0.05);
    border:1px solid rgba(255,255,255,0.10);
    font-size:15px; color:#8fa0c4; letter-spacing:0.5px; white-space:nowrap; }
</style>
</head>
<body>
<div class="bg-img" id="bgImg"></div>
<div class="theme-deco" id="themeDeco"></div>
<div class="stage">
  <svg class="skyline" viewBox="0 0 1080 340" preserveAspectRatio="xMidYMax meet">
    <g fill="#070d1e">
      <rect x="0" y="150" width="70" height="190"/>
      <rect x="78" y="100" width="58" height="240"/>
      <rect x="146" y="190" width="86" height="150"/>
      <rect x="244" y="70" width="50" height="270"/>
      <rect x="304" y="160" width="74" height="180"/>
      <rect x="392" y="120" width="60" height="220"/>
      <rect x="464" y="200" width="92" height="140"/>
      <rect x="570" y="90" width="54" height="250"/>
      <rect x="638" y="170" width="80" height="170"/>
      <rect x="730" y="130" width="64" height="210"/>
      <rect x="806" y="60" width="46" height="280"/>
      <rect x="864" y="180" width="88" height="160"/>
      <rect x="964" y="120" width="58" height="220"/>
      <rect x="1030" y="160" width="50" height="180"/>
    </g>
    <g fill="#f4c430" opacity="0.55">
      <rect x="96" y="120" width="6" height="6"/><rect x="108" y="150" width="6" height="6"/>
      <rect x="258" y="100" width="6" height="6"/><rect x="270" y="140" width="6" height="6"/>
      <rect x="404" y="150" width="6" height="6"/><rect x="416" y="190" width="6" height="6"/>
      <rect x="584" y="120" width="6" height="6"/><rect x="596" y="160" width="6" height="6"/>
      <rect x="744" y="160" width="6" height="6"/><rect x="756" y="200" width="6" height="6"/>
      <rect x="820" y="90" width="6" height="6"/><rect x="820" y="140" width="6" height="6"/>
      <rect x="978" y="150" width="6" height="6"/><rect x="990" y="190" width="6" height="6"/>
    </g>
  </svg>

  <div class="title-wrap">
    <div class="title" id="ttl">竞速图</div>
    <div class="subtitle" id="sub"></div>
    <div class="gold-rule"></div>
  </div>
  <div class="year-badge">
    <div class="year-num" id="yearNum">2021</div>
    <div class="year-cap" id="yearCap">年度</div>
  </div>
  <div class="chart" id="chart">
    <div class="axis0" id="ax0"></div>
    <div class="axis0-label" id="ax0l">0%</div>
  </div>
  <div class="legend" id="leg"></div>
  <div class="src" id="src"></div>
</div>

<script>
/*__DATA__*/
const YEARS = PAYLOAD.years;
const YLABELS = PAYLOAD.ylabels;
const INDS = PAYLOAD.industries;
const MAXABS = PAYLOAD.maxAbs;
const INTRO = PAYLOAD.intro;
const FINALHOLD = PAYLOAD.finalHold;
const TOTAL = PAYLOAD.total;
const N = YEARS.length;
const SPAN = TOTAL - INTRO - FINALHOLD;
const MODE = PAYLOAD.mode || 'cumul';
const UNIT = PAYLOAD.unit || '%';
const HL = PAYLOAD.highlight || null;
const THEME = PAYLOAD.theme || 'finance';
const MOVER = PAYLOAD.mover || null;   // 变化最突出的实体（首末年差值最大），特殊显示
// 给 body 加 theme class，切换主题化背景色（与 CSS 中 .theme-* 配套）
document.body.classList.add('theme-' + THEME);

// 与题材相关的矢量装饰插画：让背景「有意义」而不是随机渐变。
// 每个主题画一组可辨识的图形（K线/电路/油井/地球…），低透明度铺在背景层。
const DECO = {
  finance: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#f4c430" stroke-width="3">
    <g opacity=".85"><path d="M140 380v150M125 420h30M125 480h30"/><path d="M230 330v190M215 360h30M215 490h30"/><path d="M320 400v140M305 430h30M305 510h30"/>
    <rect x="120" y="430" width="40" height="90" fill="#f4c430" opacity=".5" stroke="none"/>
    <rect x="210" y="350" width="40" height="120" fill="#f4c430" opacity=".45" stroke="none"/>
    <rect x="300" y="430" width="40" height="80" fill="#f4c430" opacity=".4" stroke="none"/></g>
    <circle cx="880" cy="300" r="70" stroke-width="4"/><circle cx="880" cy="300" r="45" stroke-width="2" opacity=".6"/>
    <path d="M880 250v100M830 300h100" stroke-width="2" opacity=".5"/>
    <path d="M760 1300L820 1180l60 70 60-150 60 50" stroke-width="4" opacity=".8"/><path d="M760 1300h240" stroke-width="2" opacity=".4"/></svg>`,
  tech: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#a78bfa" stroke-width="2.5">
    <g opacity=".8"><path d="M100 300h240v120h180"/><path d="M100 420h180v160h240"/><path d="M980 340H740v140H560"/>
    <path d="M100 700h300v130h200"/><path d="M980 720H680v150H480"/></g>
    <g fill="#a78bfa" opacity=".55" stroke="none"><rect x="300" y="380" width="90" height="90" rx="8"/><rect x="620" y="420" width="80" height="80" rx="8"/>
    <rect x="380" y="760" width="90" height="90" rx="8"/><rect x="700" y="800" width="80" height="80" rx="8"/></g>
    <g fill="#a78bfa" opacity=".9" stroke="none"><circle cx="340" cy="425" r="9"/><circle cx="660" cy="460" r="9"/><circle cx="425" cy="805" r="9"/><circle cx="740" cy="840" r="9"/></g>
    <g opacity=".5"><circle cx="180" cy="1150" r="55"/><circle cx="180" cy="1150" r="110"/><circle cx="900" cy="1300" r="45"/><circle cx="900" cy="1300" r="95"/></g></svg>`,
  energy: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#fb923c" stroke-width="3">
    <g opacity=".85"><path d="M220 700l60-260 60 260zM190 700h180M250 700v260M210 960h80"/>
    <path d="M820 760l40-180 40 180zM790 760h140M830 760v200M790 960h80"/></g>
    <g opacity=".7"><path d="M420 1180c0-60 40-80 40-140s-30-60-30-100c40 30 90 90 90 160s-40 80-40 80z"/>
    <path d="M660 1180c0-60 40-80 40-140s-30-60-30-100c40 30 90 90 90 160s-40 80-40 80z"/></g>
    <g opacity=".45"><path d="M60 420h960M60 480h960"/><path d="M300 420v60M780 420v60" stroke-width="6"/></g></svg>`,
  climate: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#34d399" stroke-width="3">
    <circle cx="540" cy="560" r="200" opacity=".8"/><ellipse cx="540" cy="560" rx="200" ry="70" opacity=".5"/>
    <ellipse cx="540" cy="560" rx="70" ry="200" opacity=".5"/><path d="M340 560h400M540 360v400" opacity=".35"/>
    <path d="M540 360c60 60 100 130 100 200s-40 140-100 200c-60-60-100-130-100-200s40-140 100-200z" opacity=".35"/>
    <g opacity=".7"><path d="M200 1180v-180h60v180zM240 1060h-20v-80h20zM270 1180v-140h50v140z"/>
    <path d="M800 1180v-220h70v220zM810 1010h-15v-70h15z"/></g>
    <g opacity=".55"><path d="M170 900c50-40 90-10 90-60s-40-40-40-40c30 20 60 50 60 80s-25 30-25 30z"/></g></svg>`,
  consumer: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#fbbf24" stroke-width="3">
    <g opacity=".8"><path d="M380 500h320l-35 400H415z"/><path d="M470 560v60M570 560v60" opacity=".5"/>
    <path d="M440 500c0-70 50-110 100-110s100 40 100 110" stroke-width="4"/></g>
    <g opacity=".6"><path d="M820 380l30 60 65 10-47 46 11 65-59-31-59 31 11-65-47-46 65-10z" fill="#fbbf24" stroke="none"/>
    <path d="M180 620l22 44 48 7-35 34 9 48-44-23-44 23 9-48-35-34 48-7z" fill="#fbbf24" stroke="none"/></g>
    <g opacity=".5"><rect x="150" y="1080" width="180" height="120" rx="14"/><path d="M150 1120h180M190 1080v120"/>
    <rect x="750" y="1140" width="180" height="120" rx="14"/><path d="M750 1180h180M790 1140v120"/></g></svg>`,
  humanity: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#c084fc" stroke-width="3">
    <g opacity=".85" transform="translate(540 480)"><path d="M0-160l45 95 105 15-76 74 18 105-92-50-92 50 18-105-76-74 105-15z" fill="#c084fc" stroke="none" opacity=".7"/>
    <circle r="150" opacity=".5"/><path d="M-150 0h300M0-150v300" opacity=".3"/></g>
    <g opacity=".6"><path d="M300 760c60 90 130 140 240 140s180-50 240-140" />
    <path d="M300 760c-40 60-50 130-30 190M780 760c40 60 50 130 30 190" opacity=".7"/></g>
    <g opacity=".5" fill="#c084fc" stroke="none"><circle cx="200" cy="1120" r="10"/><circle cx="880" cy="1180" r="10"/><circle cx="320" cy="1300" r="8"/><circle cx="760" cy="1340" r="8"/></g></svg>`,
  military: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#a3b18a" stroke-width="3">
    <g opacity=".8"><path d="M540 260l180 70v190c0 150-90 250-180 300-90-50-180-150-180-300V330z"/></g>
    <g opacity=".5"><circle cx="540" cy="900" r="60"/><circle cx="540" cy="900" r="130"/><circle cx="540" cy="900" r="210"/>
    <path d="M540 900L760 720" stroke-width="4"/></g>
    <g opacity=".45"><path d="M120 1240h840M120 1300h840"/><path d="M200 1240v60M400 1240v60M600 1240v60M800 1240v60" stroke-width="6"/></g></svg>`,
  industry: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#d97706" stroke-width="3">
    <g opacity=".8"><circle cx="300" cy="500" r="90"/><circle cx="300" cy="500" r="30"/>
    <path d="M300 410v-50M300 640v50M210 500h-50M440 500h50M236 436l-35-35M364 564l35 35M364 436l35-35M236 564l-35 35" stroke-width="5"/>
    <circle cx="800" cy="620" r="60"/><circle cx="800" cy="620" r="20"/>
    <path d="M800 560v-35M800 680v35M740 620h-35M860 620h35" stroke-width="4"/></g>
    <g opacity=".6"><path d="M120 1100h300v-120l70 90 70-90v120h300v90H120z"/></g>
    <g opacity=".4"><path d="M150 900h60v-70h60M870 950h60v-70h60"/></g></svg>`,
  transit: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#38bdf8" stroke-width="3">
    <g opacity=".7"><path d="M80 700c200-200 420-200 620-40s280-40 300-120" stroke-dasharray="14 12"/>
    <path d="M80 900c220-160 400-120 560-20s300 20 360-80" stroke-dasharray="14 12" opacity=".7"/></g>
    <g opacity=".8"><path d="M420 1150h240v-90H420zM460 1060h160v-50H460zM540 1010V940"/>
    <path d="M380 1250l40-100h240l40 100z"/></g>
    <g opacity=".5"><rect x="120" y="1300" width="150" height="90" rx="8"/><rect x="285" y="1300" width="150" height="90" rx="8"/>
    <rect x="745" y="1300" width="150" height="90" rx="8"/><rect x="910" y="1300" width="60" height="90" rx="8"/></g></svg>`,
  pharma: `<svg viewBox="0 0 1080 1624" fill="none" stroke="#22d3ee" stroke-width="3">
    <g opacity=".8"><circle cx="300" cy="480" r="34" fill="#22d3ee" stroke="none"/><circle cx="480" cy="400" r="34" fill="#22d3ee" stroke="none"/>
    <circle cx="420" cy="620" r="34" fill="#22d3ee" stroke="none"/><circle cx="600" cy="540" r="34" fill="#22d3ee" stroke="none"/>
    <path d="M300 480l180-80M480 400l-60 220M420 620l180-80M300 480l120 140" stroke-width="4" opacity=".9"/></g>
    <g opacity=".7"><rect x="700" y="900" width="260" height="120" rx="60" transform="rotate(-35 830 960)"/>
    <path d="M760 930l110 60" stroke-width="6" opacity=".6"/></g>
    <g opacity=".45"><circle cx="180" cy="1200" r="50"/><circle cx="340" cy="1300" r="30"/><path d="M180 1200l160 100" stroke-dasharray="8 8"/></g></svg>`
};
(function(){
  const d = document.getElementById('themeDeco');
  if (d) d.innerHTML = DECO[THEME] || DECO.finance || '';
})();
// cumul 模式默认按 % 显示（兼容黄金/原油等增长率题材）；
// 若显式传入非空且非 % 的单位（如「亿元」），则改用该单位，避免财富类题材错显成百分比
const CU = (MODE === 'cumul' && UNIT && UNIT !== '%') ? UNIT : '%';

const CHART_TOP = 0;
const BAR_LEFT = 262, FULLW = 770;
const LABEL_SPACE = 172;                    // 右侧给数值标签预留的固定空间，柱区缩进避免长条压字
const BAR_AREA = FULLW - LABEL_SPACE;       // 柱子实际可伸展宽度（与 .track 宽度保持一致）
const ROW_H = Math.max(34, Math.floor(1180 / Math.max(INDS.length, 1)));

// 0 轴位置：按数据正负范围比例定位
// 全正时退化为左边缘（=value 模式），全负时退化为右边缘，混合时按 |负|/(正+|负|) 比例。
// 此前硬编码 ZERO_X=640（track 正中）导致全正数据 0 轴悬在中间，正柱只占右半。
// 柱区宽度用 BAR_AREA（已为标签预留空间），保证 0 轴与柱子都不触及右侧数字。
let _vMin = 0, _vMax = 0;
for (const it of INDS){
  for (const y of YEARS){
    const v = it.values[y];
    if (v == null) continue;
    if (v < _vMin) _vMin = v;
    if (v > _vMax) _vMax = v;
  }
}
let ZERO_X;
if (_vMin >= 0){
  ZERO_X = BAR_LEFT;                      // 全正：0 轴在左
} else if (_vMax <= 0){
  ZERO_X = BAR_LEFT + BAR_AREA;           // 全负：0 轴在右
} else {
  ZERO_X = BAR_LEFT + (-_vMin / (_vMax - _vMin)) * BAR_AREA;  // 混合：按比例
}
// 值→x 坐标（cumul 模式柱长定位；按 vMin/vMax 线性映射到柱区）
const valueToX = v => BAR_LEFT + ((v - _vMin) / (_vMax - _vMin)) * BAR_AREA;
const BAR_MAX = Math.max(_vMax, -_vMin);
const VAL_LEFT = BAR_LEFT + BAR_AREA + 14;   // 数值标签固定贴在柱区右侧外
const VAL_W = LABEL_SPACE - 14;

// 展示文案注入
document.getElementById('ttl').textContent = PAYLOAD.title;
document.getElementById('sub').textContent = PAYLOAD.subtitle;
document.getElementById('leg').textContent = PAYLOAD.legend;
document.getElementById('src').textContent = PAYLOAD.src;
if (PAYLOAD.bg){
  document.body.classList.add('ai-bg');
  document.getElementById('bgImg').style.backgroundImage = "url('race_bg.jpg')";
}
const ax0 = document.getElementById('ax0');
const ax0l = document.getElementById('ax0l');
if (MODE === 'value') {
  ax0.style.left = BAR_LEFT + 'px';
  ax0l.style.left = BAR_LEFT + 'px';
  ax0l.textContent = '0';
} else {
  // cumul：0 轴按数据范围比例定位
  ax0.style.left = ZERO_X + 'px';
  ax0l.style.left = ZERO_X + 'px';
  ax0l.textContent = (CU === '%') ? '0%' : '0';
}

const chart = document.getElementById('chart');
const yearNum = document.getElementById('yearNum');
const yearCap = document.getElementById('yearCap');
const yearBadge = document.querySelector('.year-badge');

const rows = {};
INDS.forEach(it => {
  const r = document.createElement('div');
  r.className = 'row';
  // 末端徽章：中文单字（省份简称/国家首字）或 emoji（公司品牌），不输出拉丁字母
  const iconStr = it.emx || it.emoji || '?';
  // 有真实 logo 图片就用 <img>（品牌标/国旗），否则用文字徽章
  const glyph = it.logo
      ? '<img class="lg" src="' + it.logo + '" alt="">'
      : '<span class="glyph">' + iconStr + '</span>';
    r.style.setProperty('--tint', it.tint || '#f4c430');
    if (MOVER && it.name === MOVER) r.classList.add('mover');
    // 名称前缀：只在图标是 emoji（公司/品牌）时显示，避免「沪上海」这类重复；
    // 有 logo 时同样不显示，防止与末端徽章重复
  r.innerHTML =
    '<div class="badge"></div>' +
    '<div class="delta"></div>' +
    '<div class="name">' + (it.emx || it.logo ? '' : '<span class="em">' + it.emoji + '</span>') + it.name + '</div>' +
    '<div class="track"></div>' +
    '<div class="bar"><div class="bar-end">' + glyph + '</div></div>' +
    '<div class="val"></div>';
  chart.appendChild(r);
  rows[it.name] = r;
  const _val = r.querySelector('.val');
  _val.style.left = VAL_LEFT + 'px';
  _val.style.width = VAL_W + 'px';
});

function valAt(it, idx){ const v = it.values[YEARS[idx]]; return (v==null)?0:v; }
function lerp(a,b,t){ return a+(b-a)*t; }
function clamp(v,a,b){ return Math.max(a, Math.min(b, v)); }
function easeInOut(t){ return t<0.5 ? 4*t*t*t : 1-Math.pow(-2*t+2,3)/2; }

// 数值格式化：显式 decimals 优先；否则 %%->1 位、空单位->2 位、其余->0 位
function fmtVal(v){
  let d = PAYLOAD.decimals;
  if (d == null){
    if (UNIT === '%') d = 1;
    else if (!UNIT) d = 2;
    else d = 0;
  }
  return v.toFixed(d);
}

function yearFloatAt(elapsed){
  const TL = PAYLOAD.timeline;
  if (TL && TL.length){
    if (elapsed < INTRO) return 0;
    if (elapsed <= TL[0][0]) return TL[0][1];
    if (elapsed >= TL[TL.length-1][0]) return TL[TL.length-1][1];
    for (let i=0;i<TL.length-1;i++){
      if (elapsed <= TL[i+1][0]){
        const a0=TL[i][0], a1=TL[i+1][0], b0=TL[i][1], b1=TL[i+1][1];
        if (a1===a0) return b1;
        return b0 + (b1-b0)*(elapsed-a0)/(a1-a0);
      }
    }
    return TL[TL.length-1][1];
  }
  const p = clamp((elapsed - INTRO) / SPAN, 0, 1);
  return easeInOut(p) * (N - 1);
}

let lastYi = -1;
let lastBadgeAnimT = -9;     // 上次徽标脉冲的 elapsed，节流用：6.5 步/秒时 430ms 动画每 154ms 重启会恒处半动画态
const prevFrameRank = {};   // 上一帧名次（用于 B. 超车脉冲）
const pulseStart = {};      // 各实体最近一次「反超」发生时的 elapsed（驱动确定性脉冲动画）
const PULSE_DUR = 0.6;      // 脉冲时长（秒），由 render 时间驱动，保证逐帧截图能捕捉到
let prevYearRank = {};      // 上一年名次（用于 C. 跨年方向箭头）
function render(elapsed){
  let introScale = 1, yf;
  if (elapsed < INTRO){ introScale = elapsed / INTRO; yf = 0; }
  else { yf = yearFloatAt(elapsed); }

  const lo = Math.floor(yf), hi = Math.min(lo+1, N-1);
  const f = yf - lo;
  const arr = INDS.map(it => ({ it, v: lerp(valAt(it,lo), valAt(it,hi), f) * introScale }));
  arr.sort((a,b)=> b.v - a.v);
  const curRank = {};

  arr.forEach((o, rank)=>{
    const r = rows[o.it.name];
    r.style.top = (CHART_TOP + rank*ROW_H) + 'px';
    const badge = r.querySelector('.badge');
    const bar = r.querySelector('.bar');
    const val = r.querySelector('.val');
    const isHL = (HL && o.it.name === HL);
    badge.textContent = (rank+1);
    curRank[o.it.name] = rank;
    // B. 超车脉冲：名次上升（rank 减小）的瞬间记录事件时间，随后由 render 时间驱动一波确定性脉冲
    //    —— 不能用 WAAPI .animate()：逐帧截图在 render() 后立即进行，实时动画永远停在 t≈0 不可见。
    const pf = prevFrameRank[o.it.name];
    if (pf !== undefined && rank < pf) {
      pulseStart[o.it.name] = elapsed;
    }
    prevFrameRank[o.it.name] = rank;
    // 计算脉冲强度（0..1 的正弦包络），转为静态内联样式，逐帧截图必捕捉
    const ps0 = pulseStart[o.it.name];
    let pScale = 1, pBright = 1, pRing = 0;
    if (ps0 !== undefined) {
      const dt = elapsed - ps0;
      if (dt >= 0 && dt <= PULSE_DUR) {
        const env = Math.sin(Math.PI * (dt / PULSE_DUR));   // 0→1→0
        pScale = 1 + 0.55 * env;        // badge 放大到 1.55
        pBright = 1 + 1.1 * env;        // bar 变亮到 2.1
        pRing = env;                    // 金边光晕强度
      }
    }
    badge.style.transformOrigin = 'center center';
    badge.style.transform = 'scale(' + pScale.toFixed(3) + ')';
    if (pRing > 0.02) {
      badge.style.boxShadow = '0 0 ' + (10 + 18 * pRing).toFixed(1) + 'px rgba(244,196,48,' + (0.4 + 0.5 * pRing).toFixed(2) + ')';
    } else {
      badge.style.boxShadow = '';
    }
    bar.style.filter = 'brightness(' + pBright.toFixed(3) + ')';
    r.classList.remove('lead','medal-1','medal-2','medal-3','cn');
    if (rank===0) r.classList.add('medal-1');
    else if (rank===1) r.classList.add('medal-2');
    else if (rank===2) r.classList.add('medal-3');

    if (MODE === 'value'){
      const w = Math.max(3, o.v / MAXABS * BAR_AREA);
      bar.style.left = BAR_LEFT + 'px';
      bar.style.width = w + 'px';
      if (isHL){
        bar.style.background = 'linear-gradient(90deg,#b9890a,#f4c430 60%,#ffe89a)';
        val.style.color = '#ffd86b';
      } else {
        bar.style.background = 'linear-gradient(90deg,#2b6fb0,#4aa3e0 60%,#9fd6ff)';
        val.style.color = '#8fd0ff';
      }
      val.textContent = fmtVal(o.v) + (UNIT ? ' ' + UNIT : '');
      r.classList.toggle('cn', isHL);
    } else {
      const up = o.v >= 0;
      const xv = valueToX(o.v);
      if (up){
        bar.style.left = ZERO_X + 'px';
        bar.style.width = Math.max(2, xv - ZERO_X) + 'px';
        bar.style.background = 'linear-gradient(90deg,#a01919,#e23b3b 65%,#ff7a6c)';
      } else {
        bar.style.left = xv + 'px';
        bar.style.width = Math.max(2, ZERO_X - xv) + 'px';
        bar.style.background = 'linear-gradient(270deg,#0f7a48,#1fb46e 65%,#43eaa0)';
      }
      const _dec = (CU === '%') ? 2 : (PAYLOAD.decimals != null ? PAYLOAD.decimals : 0);
      val.textContent = (up && CU === '%' ? '+' : '') + o.v.toFixed(_dec) + (CU === '%' ? '%' : ' ' + CU);
      val.style.color = up ? '#ff6b5e' : '#43eaa0';
      if (up && o.v>0 && rank===0) r.classList.add('lead');
    }
  });

  const yi = Math.max(0, Math.min(N-1, Math.round(yf)));
  if (yi !== lastYi){
    // 月度/季度高频步进时，430ms 徽标脉冲会被反复重启、恒处半动画态；
    // 用 lastBadgeAnimT 节流，只有上一次动画真正放完才允许触发新的。
    if (elapsed - lastBadgeAnimT >= 0.45) {
      yearBadge.animate(
        [{transform:'scale(1)', opacity:0.55}, {transform:'scale(1.16)', opacity:1}, {transform:'scale(1)', opacity:1}],
        {duration:430, easing:'ease-out'});
      lastBadgeAnimT = elapsed;
    }
    yearNum.textContent = YLABELS[YEARS[yi]];
    yearCap.textContent = (MODE==='value') ? '年度'
      : ((YEARS[yi]===YEARS[N-1]) ? '至今' : '年度');
    // C. 名次方向箭头：相对上一年（仅在跨年边界刷新，避免逐帧抖动）
    INDS.forEach(it => {
      const r = rows[it.name];
      const dEl = r.querySelector('.delta');
      const pr = prevYearRank[it.name];
      const cr = curRank[it.name];
      if (pr == null) { dEl.textContent='—'; dEl.className='delta flat'; }
      else {
        const delta = pr - cr;   // >0 名次上升
        if (delta > 0) { dEl.textContent='▲'; dEl.className='delta up'; }
        else if (delta < 0) { dEl.textContent='▼'; dEl.className='delta down'; }
        else { dEl.textContent='—'; dEl.className='delta flat'; }
      }
    });
    prevYearRank = Object.assign({}, curRank);
    lastYi = yi;
  }
}

window.renderAt = render;
window.TOTAL = TOTAL;
window.FPS = PAYLOAD.fps;
render(0);
</script>
</body>
</html>
"""
if __name__ == '__main__':
    main()
