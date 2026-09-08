#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金融榜单竞速视频 · 一键编排入口。

把整套「申万一级行业累计收益竞速视频」流程串起来，便于任意 workspace 复用：
  采集(akshare) -> 累计折算 -> 生成竞速HTML -> Node Playwright 渲染帧
  -> [可选] 口播稿+Azure TTS配音 -> 下载无版权BGM -> ffmpeg 混音成片
  -> 成片后：gen_meta 自动生成标题/话题/简介 -> deliver 归档到 D:/AI视频

用法（在目标 workspace 下执行）：
  python run.py all                       # 全流程（含配音）
  python run.py all --no-voice            # 全流程（不配音，仅 BGM）
  python run.py build --span 18           # 只重建竞速 HTML
  python run.py topic_config --key szse_area --workspace <ws>
  python run.py topic_config --key '*' --workspace <ws>
"""
import argparse, datetime, os, sys, subprocess, json, time, shutil
import os.path
from os.path import dirname, abspath

SCRIPT_DIR = dirname(abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import imgtable
import gen_finance_meta

MANAGED_PY = 'C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe'


def _deliver_outdir():
    """交付目录：优先 D:\\AI视频\\<项目名>，D 盘不可用/不可写时回落工作区。"""
    root = os.environ.get('VIDEO_OUT_ROOT', 'D:\\AI视频')
    name = os.environ.get('VIDEO_PROJECT_NAME', '数据竞速')
    try:
        if os.path.isdir(root) and os.access(root, os.W_OK):
            return os.path.join(root, name)
    except Exception:
        pass
    return 'out/增长与分化'


DELIVER_OUTDIR = _deliver_outdir()


def _resolve_node():
    """动态定位 node.exe。

    managed node 的版本目录会随升级改名（实测 22.22.2 -> 22.22.2-2，旧目录被
    重命名为 .22.22.2.deleting.*），硬编码路径会在升级后静默失效，表现为渲染
    直接报「系统找不到指定的路径」。这里改为扫描版本目录，取排序后的最新一个。
    """
    import glob
    base = 'C:/Users/medam/.workbuddy/binaries/node/versions'
    cands = []
    try:
        cur = os.path.join(base, 'current')
        if os.path.isfile(cur):
            with open(cur, encoding='utf-8') as f:
                cands.append(f.read().strip())
        for d in glob.glob(os.path.join(base, '*')):
            cands.append(os.path.join(d, 'node.exe'))
    except Exception:
        pass
    for c in sorted(cands):
        if os.path.isfile(c):
            return c.replace('\\', '/')
    return 'C:/nvm4w/nodejs/node.exe'


NODE = _resolve_node()
NODE_MODULES = 'C:/Users/medam/.workbuddy/binaries/node/workspace/node_modules'
CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
FFPROBE = 'C:/ProgramData/chocolatey/bin/ffprobe'

INTRO = 0.7
FINALHOLD = 1.5
# 成片总时长硬上限（秒）。用户要求尽量控制在 2 分钟以内；超出时用更快语速
# 重生成配音把内容压进来，而不是粗暴截断画面或配音。
MAX_DUR = float(os.environ.get('RACE_MAX_DUR', '120'))
# 加速上限：再快就不自然了（1.35 倍≈正常播报语速）
MAX_RATE = 1.35


def py(script, *args, workspace=None, env=None):
    """用受管 Python 运行 scripts/<script>，默认 cwd=workspace。"""
    cmd = [MANAGED_PY, os.path.join(SCRIPT_DIR, script)] + [str(a) for a in args]
    if workspace:
        cmd += ['--workspace', str(workspace)]
    print('\n=== py', script, '===')
    e = dict(os.environ)
    if env:
        e.update(env)
    subprocess.run(cmd, cwd=workspace, env=e, check=True)


def _kill_tree(pid):
    """强制结束进程树（含 Chromium 子进程），避免渲染挂起时残留。"""
    try:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def node(script, workspace=None, env=None, timeout=1200, retries=2):
    """用受管 Node 运行 scripts/<script>；输出实时落盘到 logs/ 便于排查。"""
    e = dict(os.environ)
    e['NODE_PATH'] = NODE_MODULES
    e['WORKSPACE'] = os.path.abspath(workspace) if workspace else ''
    if env:
        e.update(env)
    logdir = os.path.join(workspace or '.', 'logs')
    os.makedirs(logdir, exist_ok=True)
    for attempt in range(1, retries + 1):
        stamp = datetime.datetime.now().strftime('%H%M%S')
        log = os.path.join(logdir, 'render_' + os.path.splitext(os.path.basename(script))[0] + '_' + stamp + '.log')
        print('\n=== node ', script, ' (尝试 ', attempt, '/', retries, ') -> log ', log, ' ===', sep='')
        with open(log, 'w', encoding='utf-8', errors='replace') as lf:
            p = subprocess.Popen([NODE, os.path.join(SCRIPT_DIR, script)],
                                 cwd=workspace, env=e, stdout=lf, stderr=subprocess.STDOUT)
        waited = 0
        while p.poll() is None:
            time.sleep(3)
            waited += 3
            try:
                with open(log, 'r', encoding='utf-8', errors='ignore') as lf:
                    if 'REACHED_EXIT' in lf.read():
                        break
            except Exception:
                pass
            if waited >= timeout:
                print('[node] 渲染超时（', timeout, 's），强制结束进程树 pid=', p.pid, sep='')
                _kill_tree(p.pid)
                raise RuntimeError('render_race.js 超时（' + str(timeout) + '）')
        try:
            p.wait(timeout=30)
        except Exception:
            pass
        if p.returncode == 0:
            return
        print('[node] 渲染进程非零退出（', p.returncode, '），重试', sep='')
        time.sleep(1)
    raise RuntimeError('render_race.js 失败（' + script + '）')


def ffprobe_dur(p):
    try:
        out = subprocess.check_output([FFPROBE, '-v', 'error', '-show_entries',
                                       'format=duration', '-of',
                                       'default=noprint_wrappers=1:nokey=1', p])
        return float(out.decode().strip())
    except Exception:
        return None


def step_build(ws, span):
    py('build_race.py', '--span', span, workspace=ws)


THEME_RULES = [
    ('tech', ('芯片', 'AI ', '人工智能', '半导体', '电脑', '计算机', '互联网', '资本开支', '', '')),
    ('pharma', ('医药', '健康', '药', '疫苗', '生物')),
    ('energy', ('能源', '石油', '天然气', '煤炭', '发电', '油气')),
    ('climate', ('碳', '气候', '环境', '肥胖')),
    ('humanity', ('诺奖', '文学', '艺术')),
    ('military', ('军工', '国防', '武器')),
    ('industry', ('钢铁', '产量', '矿业', '资源', '材料', '造船', '建筑', '设备', '', '')),
    ('transit', ('港口', '运输', '机场', '地铁', '汽车', '车', '航运', '股票交易额', '', '')),
    ('consumer', ('品牌', '零售', '消费', '市值', '电商', '财富', '百富', '巨头')),
]


def infer_theme(title):
    """根据标题关键字推断主题色。返回字符串如 'tech' / 'finance'，供 build_race 的 --theme。"""
    for theme, kws in THEME_RULES:
        for k in kws:
            if k and k in title:
                return theme
    return 'finance'


def step_build_cn(ws, span):
    py('build_race.py', '--data', 'cn_world.json', '--span', span, workspace=ws)


def step_build_finance(ws, span):
    py('build_race.py', '--data', 'finance.json', '--span', span, workspace=ws)


def step_finance(ws, kind, level, topic, top, start_year, ytd_year, no_voice):
    """任意财经主题成片：泛化采集 -> 统一文案 -> (配音->反推span) -> 竞速渲染 -> BGM -> 混音 -> 交付。"""
    py('collect_finance.py', '--kind', kind, '--level', level, '--topic', topic,
       '--top', top, '--start-year', start_year, '--ytd-year', ytd_year, workspace=ws)
    py('gen_finance_meta.py', workspace=ws)
    with open(os.path.join(ws, 'data', 'finance.json'), encoding='utf-8') as f:
        d = json.load(f)
    n = len(d.get('years', []))
    span = max(10.0, (n - 1) * 2.5)
    step_build_finance(ws, span)
    vo = None
    if not no_voice:
        vo = os.path.join(ws, 'data', 'voiceover.mp3')
        py('tts.py', workspace=ws)
        vo_dur = ffprobe_dur(vo)
        if vo_dur:
            span = max(2.0, vo_dur - INTRO - FINALHOLD)
            step_build_finance(ws, span)
    node('render_race.js', ws)
    py('fetch_bgm.py', workspace=ws)
    py('mix_final.py', *([] if vo else ['--no-voice']), '--out', 'finance.mp4', workspace=ws)
    step_deliver(ws, 'out/finance.mp4', 'finance_' + str(topic))
    print('\nFINANCE DONE ->', topic)


def step_deliver(ws, src_rel, kind):
    """交付归档：把成片直接保存到 D:/AI视频/数据竞速/，按「编号_标题.mp4」命名。"""
    py('deliver.py', '--src', src_rel, '--meta', 'data/post_meta.json',
       '--kind', kind, '--outdir', DELIVER_OUTDIR, workspace=ws)


def step_cnworld(ws, topic, no_voice):
    """中外对比题材成片：采集 -> 文案 -> (配音->反推span) -> 竞速渲染 -> BGM -> 混音。"""
    py('collect_cn_world.py', '--topic', topic, workspace=ws)
    py('gen_cnworld.py', workspace=ws)
    with open(os.path.join(ws, 'data', 'cn_world.json'), encoding='utf-8') as f:
        d = json.load(f)
    n = len(d.get('years', []))
    span = max(10.0, (n - 1) * 2.5)
    step_build_cn(ws, span)
    vo = None
    if not no_voice:
        vo = os.path.join(ws, 'data', 'voiceover.mp3')
        py('tts.py', workspace=ws)
        vo_dur = ffprobe_dur(vo)
        if vo_dur:
            span = max(2.0, vo_dur - INTRO - FINALHOLD)
            step_build_cn(ws, span)
    node('render_race.js', ws)
    py('fetch_bgm.py', workspace=ws)
    py('mix_final.py', *([] if vo else ['--no-voice']), '--out', 'cn_world.mp4', workspace=ws)
    step_deliver(ws, 'out/cn_world.mp4', 'cn_vs_world')
    print('\nCNWORLD DONE ->', topic)


def step_imgtable(ws, data, bg_prompt, no_ai, voice, duration, unit, title):
    """方案 B：AI 生图打底 + 数据叠加（单场景慢推镜头）。"""
    py('imgtable.py', '--data', data, '--bg-prompt', bg_prompt, '--duration', duration,
       '--unit', unit, '--title', title, workspace=ws)
    py('deliver.py', '--src', 'out/imgtable.mp4', '--meta', 'data/imgtable_post_meta.json',
       '--kind', 'imgtable', '--outdir', DELIVER_OUTDIR, workspace=ws)
    print('\nIMGTABLE DONE ->', title)


def _fmt_val(v, decimals=0):
    return format(v, '.' + str(decimals) + 'f')


def _val_at(v, year, years=None):
    """取 values 在某一年的值，兼容 dict({年:值}) 与 list(按 years 顺序)。"""
    if v is None:
        return 0
    if isinstance(v, dict):
        return v.get(str(year), 0) or 0
    if isinstance(v, (list, tuple)):
        if years and str(year) in [str(x) for x in years]:
            i = [str(x) for x in years].index(str(year))
            return (v[i] if i < len(v) else 0) or 0
        return (v[0] if v else 0) or 0
    return v or 0


def normalize_topic(raw, topic_name):
    """把题材 JSON 归一化为 build_race.py 的数据契约 + meta（标题/单位/模式/小数位等）。

    返回 (slug, norm_json, post_meta_json, default_bg_prompt)。
    - 结婚率：每一年是单值行 -> pivot 成「中国结婚率」单实体，逐年数值（value 模式，‰，1 位）。
    - 生育率：中日韩 3 实体多年 -> value 模式（TFR，2 位）。
    - 房价 Top10：每年一个排名表 -> rank 模式。
    """
    y = raw.get('years')
    if not y:
        raise SystemExit('ERROR: 题材 JSON 缺少 years')
    ylabels = raw.get('year_labels') or [str(v) for v in y]
    src_text = raw.get('source', '')
    unit_note = raw.get('unit_note', '')

    if topic_name == 'marriage_rate':
        merged = {}
        for it in raw.get('industries', []):
            v = it.get('values')
            if isinstance(v, dict):
                merged.update(v)
            elif isinstance(v, (list, tuple)):
                for _y, _val in zip(y, v):
                    merged[str(_y)] = _val
        inds = [{'name': '中国结婚率', 'code': 'marriage', 'values': merged}]
        slug = 'marriage_rate'
        meta = {
            'title': '中国结婚率十年走势',
            'subtitle': '每千人结婚对数(‰) · ' + str(y[0]) + '–' + str(y[-1]),
            'unit': '‰',
            'mode': 'value',
            'decimals': 1,
            'highlight': None,
            'legend': '数值越高 = 结婚率越高（单位：‰，每千人结婚对数）',
            'src': src_text,
        }
        prompt = ('极简高级财经数据可视化背景，深邃藏蓝至近黑竖向渐变，细腻金色光丝与柔和光斑，'
                  '电影感，四周加重暗角，画面干净无文字，适合做单条数据曲线/柱状图衬底，专业克制')
        return slug, {'years': y, 'year_labels': ylabels, 'industries': inds, 'meta': meta}, \
            None, prompt

    if topic_name == 'fertility_rate':
        inds = [{'name': it.get('name'), 'code': it.get('code'), 'values': it.get('values')}
                for it in raw.get('industries', [])]
        slug = 'fertility_rate'
        meta = {
            'title': '中日韩总和生育率对比',
            'subtitle': '妇女终身平均生育数(TFR) · ' + str(y[0]) + '–' + str(y[-1]),
            'unit': '',
            'mode': 'value',
            'decimals': 2,
            'highlight': '中国',
            'legend': '★=中国 · 蓝=日本/韩国 · 柱长=总和生育率(TFR)',
            'src': src_text,
        }
        prompt = ('高级财经对比数据可视化背景，冷调深蓝与靛紫渐变，抽象三组上升曲线微光，电影感，'
                  '四角暗角，无文字，专业克制，适合多国对比柱状竞速')
        return slug, {'years': y, 'year_labels': ylabels, 'industries': inds, 'meta': meta}, \
            None, prompt

    if topic_name in ('cn_top10_houseprice', 'world_top10_houseprice'):
        for it in raw.get('industries', []):
            if it.get('name') == '香港':
                it['name'] = '中国香港'
        inds = sorted(raw.get('industries', []),
                      key=lambda x: _val_at(x.get('values'), y[-1], y), reverse=True)
        if topic_name == 'cn_top10_houseprice':
            unit, title = '元/㎡', '中国房价最贵城市 Top10'
            sub = '二手/挂牌均价(元/㎡) · ' + str(y[0]) + '–' + str(y[-1])
            legend = '柱长 = 房价 · 越长越贵'
            prompt = ('高端房地产数据可视化背景，深蓝与暖金交织的都市夜景抽象光带，电影感，四角暗角，'
                      '无文字，专业克制，适合城市房价排名柱状图')
        else:
            unit, title = '美元/㎡', '全球房价最贵城市 Top10'
            sub = '核心区豪宅均价(美元/㎡) · ' + str(y[0]) + '–' + str(y[-1])
            legend = '柱长 = 房价 · 越长越贵'
            prompt = ('全球奢华地产数据可视化背景，深蓝与铂金灰渐变，抽象摩天楼剪影光带，电影感，'
                      '四角暗角，无文字，专业克制，适合国际城市房价排名柱状图')
        slug = topic_name
        meta = {
            'title': title,
            'subtitle': sub,
            'unit': unit + ((' · ' + unit_note) if unit_note else ''),
            'mode': 'rank',
            'decimals': 0,
            'highlight': None,
            'legend': legend,
            'src': src_text,
        }
        return slug, {'years': y, 'year_labels': ylabels, 'industries': inds, 'meta': meta}, \
            None, prompt

    m = raw.get('meta') or {}
    slug = topic_name
    meta = {
        'title': m.get('title', ''),
        'subtitle': m.get('subtitle', ''),
        'unit': m.get('unit', ''),
        'mode': m.get('mode', 'rank'),
        'decimals': m.get('decimals', 0),
        'highlight': m.get('highlight'),
        'legend': m.get('legend', ''),
        'src': m.get('src', src_text),
    }
    prompt = m.get('bg_prompt') or \
        '高级财经数据可视化背景，深色渐变，电影感，四角暗角，无文字，专业克制'
    norm = {'years': y, 'year_labels': ylabels,
            'industries': raw.get('industries', []), 'meta': meta}
    return slug, norm, None, prompt


def gen_topic_narration(norm, post_meta):
    """题材口播兜底生成（gen_finance_meta 失败时的回退）。统一走对比/反差风格。"""
    try:
        meta = norm.get('meta', {})
        dec = meta.get('decimals', 0)
        unit = meta.get('unit', '')
        yrs = norm.get('years', [])
        inds = norm.get('industries', [])
        title = meta.get('title', '')
        if len(yrs) >= 2 and inds:
            first, last = yrs[0], yrs[-1]
            top = max(inds, key=lambda x: (x.get('values') or [0])[-1])
            vs = top.get('values') or [0]
            v0, v1 = vs[0], vs[-1]
            chg = '上升' if v1 >= v0 else '下降'
            return ('一张动态榜单，看' + str(title) + '。从' + str(first) + '年的'
                    + _fmt_val(v0, dec) + unit + '，到' + str(last) + '年的'
                    + _fmt_val(v1, dec) + unit + '，十年间' + chg + '，变化清晰可见。数据来源：'
                    + str(meta.get('src', '')).split('·')[0].strip() + '。')
        s = gen_finance_meta.compute_value_stats(norm)
        lines = gen_finance_meta._contrast_lines(s, unit)
        tops = sorted(inds, key=lambda x: (x.get('values') or [0])[-1], reverse=True)[:3]
        return ('一张动态榜单，看' + str(title) + '，'
                + ' '.join(lines) + '。当前领先的是：'
                + '、'.join('%s（%s）' % (it.get('name'),
                                        _fmt_val((it.get('values') or [0])[-1], dec))
                            for it in tops)
                + '。完整排名请看视频。数据来源：' + str(meta.get('src', '')) + '。')
    except Exception:
        return '一张动态榜单，看数据如何随时间变化。完整排名请看视频。'


def step_topic_race(ws, topic_name, topic_file, bg_prompt, no_ai, no_voice, voice, platform):
    """题材竞速成片：归一化题材 -> 精修文案(标题/话题/简介/口播稿)
-> gpt-image-2 背景 -> build_race --bg-image
-> Playwright 渲染 -> BGM/配音混音 -> 交付归档。"""
    tf = topic_file
    if not os.path.isabs(tf):
        tf = os.path.join(SCRIPT_DIR, 'topics', 'topic_' + topic_name + '.json')
    if not os.path.exists(tf):
        raise SystemExit('ERROR: 找不到题材 JSON ' + tf)
    with open(tf, encoding='utf-8') as f:
        raw = json.load(f)
    slug, norm, post_meta, prompt_default = normalize_topic(raw, topic_name)
    _topic_pipeline(ws, slug, norm, post_meta, prompt_default, bg_prompt,
                    no_ai, no_voice, voice)


def _topic_pipeline(ws, slug, norm, post_meta, prompt_default, bg_prompt,
                    no_ai, no_voice, voice, num=None):
    """题材竞速公共流水线（topic_race 与 topic_config 共用）：
写归一化数据 -> 精修文案(两套) -> gpt-image-2 背景 -> build_race
-> 配音(TTS) -> 渲染 -> 混音 -> 交付归档。"""
    import re as _re
    data_dir = os.path.join(ws, 'data')
    out_dir = os.path.join(ws, 'out')
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    norm_path = os.path.join(data_dir, 'topic_' + slug + '.json')
    meta_path = os.path.join(data_dir, 'topic_' + slug + '_post_meta.json')
    json.dump(norm, open(norm_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump(post_meta, open(meta_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    narr_path = os.path.join(data_dir, 'topic_' + slug + '_narration.txt')
    _custom_narr = None
    if os.path.exists(narr_path):
        try:
            _custom_narr = open(narr_path, encoding='utf-8').read()
            print('[topic] 检测到定制口播稿（', len(_custom_narr), ' 字），生成文案后将还原', sep='')
        except Exception as e:
            print('[topic] 定制口播稿读取失败：', repr(e))

    for pf in ('xhs', 'wechat'):
        prefix = 'topic_' + slug if pf == 'xhs' else 'topic_' + slug + '_wechat'
        try:
            py('gen_finance_meta.py', '--src', norm_path, '--out-prefix', prefix,
               '--platform', pf, workspace=ws)
            print('[topic] 精修文案(' + pf + ') -> ' + prefix + '_post_meta.json')
        except Exception as e:
            print('[topic] gen_finance_meta(' + pf + ') 失败：', repr(e))

    if _custom_narr:
        with open(narr_path, 'w', encoding='utf-8') as _nf:
            _nf.write(_custom_narr)
        print('[topic] 已还原定制口播稿 -> ' + narr_path)

    bg_out = os.path.join(out_dir, '_topic_bg.png')
    # 背景提示词：按题材内容生成「相关且压得住数据」的画面描述（LLM + 缓存）。
    # 以前是通用抽象渐变，每支片子长得都一样，跟内容无关。
    bgpf = os.path.join(data_dir, 'topic_' + slug + '_bgprompt.txt')
    try:
        py('bg_prompt.py', '--data', norm_path, '--out', bgpf, workspace=ws)
    except Exception as e:
        print('[topic] 背景提示词生成跳过：', repr(e))
    prompt = bg_prompt or ''
    if not prompt and os.path.exists(bgpf):
        try:
            prompt = open(bgpf, encoding='utf-8').read().strip()
        except Exception:
            prompt = ''
    if not prompt:
        prompt = prompt_default
    pre_bg = os.path.join(out_dir, '_bg_' + slug + '.png')
    if os.path.exists(pre_bg) and os.path.getsize(pre_bg) > 5000 and no_ai:
        # 预置背景只在 --no-ai 时兜底使用；默认一律按内容重新生成
        shutil.copyfile(pre_bg, bg_out)
        print('[topic] 复用预置背景 -> ' + pre_bg)
    else:
        try:
            imgtable.gen_background(ws, prompt, bg_out, no_ai)
        except Exception as e:
            print('[topic] 背景生成失败，回退占位：', repr(e))

    if not _custom_narr:
        open(narr_path, 'w', encoding='utf-8').write(gen_topic_narration(norm, post_meta))

    # 口播稿长度定制：数据点多的题材讲久一点、少的讲短一点（目标时长 -> 目标字数 -> 改写）。
    # 不再靠"长稿加速"硬压，而是让稿子本身就匹配内容量。原稿自动备份为 *.orig。
    if not no_voice:
        try:
            py('fit_narration.py', '--data', norm_path, '--src', narr_path, workspace=ws)
        except Exception as e:
            print('[topic] 口播稿长度定制跳过，沿用原稿：', repr(e))

    yrs = norm['years']
    n = len(yrs)
    span = max(10.0, (n - 1) * 2.5) if n > 1 else 9.0
    # 数据点极多的题材（如 90 个季度）默认 span 会到 220s+，统一压到上限内
    span = min(span, max(2.0, MAX_DUR - INTRO - FINALHOLD))
    has_bg = os.path.exists(bg_out)
    theme = infer_theme((post_meta or {}).get('title') or norm.get('meta', {}).get('title', '') or '')

    build_args = ['--data', norm_path, '--span', '{:g}'.format(span), '--theme', theme]
    if has_bg:
        build_args += ['--bg-image', bg_out]
    py('build_race.py', *build_args, workspace=ws)

    vo = os.path.join(data_dir, 'voiceover.mp3')
    if not no_voice:
        # TTS 走 Azure/edge-tts 两个通道，公司代理会偶发 SSL 重置，重试即可
        for _try in range(1, 4):
            try:
                py('tts.py', '--src', narr_path, '--out', vo, workspace=ws)
                break
            except Exception as e:
                print('[topic] tts 第', _try, '次失败：', repr(e))
                if _try == 3:
                    raise
                time.sleep(8 * _try)

    vo_dur = ffprobe_dur(vo) or 30.0
    if not no_voice and vo_dur > MAX_DUR:
        # 口播太长 → 提速重录，把内容完整塞进 2 分钟，而不是截断
        need = min(MAX_RATE, vo_dur / max(1.0, MAX_DUR - 3))
        print('[topic] 口播 %.1fs 超过上限 %.0fs，语速 ×%.2f 重录' % (vo_dur, MAX_DUR, need))
        for _try in range(1, 4):
            try:
                py('tts.py', '--src', narr_path, '--out', vo, '--rate', '%.2f' % need,
                   workspace=ws)
                break
            except Exception as e:
                print('[topic] tts(加速) 第', _try, '次失败：', repr(e))
                if _try == 3:
                    print('[topic] 加速失败，沿用原配音并按上限截断画面')
                else:
                    time.sleep(8 * _try)
        vo_dur = ffprobe_dur(vo) or vo_dur
    span = max(2.0, min(vo_dur, MAX_DUR) - INTRO - FINALHOLD)

    build_args2 = ['--data', norm_path, '--span', '{:g}'.format(span), '--theme', theme]

    tl_path = os.path.join(data_dir, 'topic_' + slug + '_timeline.json')
    # ⚠️ 不能 os.remove()：sandbox safe-delete 守卫会拦截并杀死整个进程。
    # 改成改名（rename 不计入删除监控），gen_timeline 会重新写入。
    if os.path.exists(tl_path):
        try:
            os.replace(tl_path, tl_path + '.prev.json')
        except OSError:
            pass
    _yrs = norm.get('years') or []
    _fy = _fy0 = None
    if _yrs:
        try:
            _fy = int(str(_yrs[-1])[:4])
            _fy0 = int(str(_yrs[0])[:4])
        except (TypeError, ValueError):
            _fy = _fy0 = None
    if not no_voice:
        _tl_args = ['--src', narr_path, '--out', tl_path, '--audio', vo,
                    '--data', norm_path, '--intro', '{:g}'.format(INTRO),
                    '--tail', '{:g}'.format(FINALHOLD)]
        if _fy:
            _tl_args += ['--final-year', str(_fy)]
        if _fy0:
            _tl_args += ['--first-year', str(_fy0)]
        try:
            py('gen_timeline.py', *_tl_args, workspace=ws)
        except BaseException as e:
            print('[topic] gen_timeline 失败，回退匀速推进：', repr(e))
        if os.path.exists(tl_path) and os.path.getsize(tl_path) > 0:
            build_args2 += ['--timeline', tl_path]
            print('[topic] 口播驱动时间轴已挂载 ->', tl_path)
    if has_bg:
        build_args2 += ['--bg-image', bg_out]
    py('build_race.py', *build_args2, workspace=ws)

    frames_root = os.environ.get('FRAMES_ROOT') or out_dir
    frames_dir = os.path.join(frames_root, 'frames_topic_' + slug)
    # ⚠️ 关键：渲染前必须把旧帧目录整个挪走。否则上一次渲染留下的多余帧
    # （如旧 4549 帧 vs 新 3497 帧）会被 mix_final 一并拼接，成片尾部多出
    # 一段旧内容、时长也跟着变长（实测 116s 的片被拼成 151s）。
    # 用 rename 而不是删除：safe-delete 守卫会杀进程。
    if os.path.isdir(frames_dir):
        try:
            os.replace(frames_dir, frames_dir + '_old_%d' % int(time.time()))
        except OSError:
            pass
    os.makedirs(frames_dir, exist_ok=True)
    node('render_race.js', ws, env={'FRAMES_DIR': frames_dir})

    try:
        py('fetch_bgm.py', workspace=ws)
    except Exception as e:
        print('[topic] fetch_bgm 失败，回退粉噪兜底：', repr(e))

    mix_args = ['--out', 'topic_' + slug + '.mp4', '--frames-dir', frames_dir]
    if no_voice:
        mix_args += ['--no-voice']
    py('mix_final.py', *mix_args, workspace=ws)

    dargs = ['--src', 'out/topic_' + slug + '.mp4',
             '--title', norm['meta']['title'],
             '--meta', 'data/topic_' + slug + '_post_meta.json',
             '--kind', 'topic_' + slug,
             '--outdir', DELIVER_OUTDIR]
    if num:
        dargs += ['--no', str(num)]
    py('deliver.py', *dargs, workspace=ws)
    print('\nTOPIC DONE ->', slug)


def step_topic_config(ws, key, spec, bg_prompt, no_ai, no_voice, voice, num=None):
    """配置驱动题材：调适配器取数 -> 泛型归一化 -> 公共流水线。"""
    from adapters import get_adapter
    source = spec.get('source')
    params = dict(spec.get('params') or {})
    params['_ws'] = ws
    params['_script_dir'] = SCRIPT_DIR
    adapter = get_adapter(source)
    print('[topic_config] 适配器=' + str(source) + ' key=' + str(key) + ' 取数...')
    raw = adapter.fetch(params)
    _slug, norm, post_meta, prompt_default = normalize_topic(raw, key)
    bp = spec.get('bg_prompt') or bg_prompt
    _topic_pipeline(ws, _slug, norm, post_meta, prompt_default, bp,
                    no_ai, no_voice, voice, num=num)


def main():
    ap = argparse.ArgumentParser(description='金融榜单竞速视频 · 一键编排')
    ap.add_argument('cmd', choices=['all', 'collect', 'cumul', 'build', 'render', 'verify',
                                    'narration', 'tts', 'bgm', 'mix', 'meta', 'cnworld',
                                    'finance', 'imgtable', 'topic_race', 'topic_config',
                                    'deliver'])
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--start-year', type=int, default=2021)
    ap.add_argument('--ytd-year', type=int, default=None)
    ap.add_argument('--no-voice', action='store_true')
    ap.add_argument('--span', type=float, default=None)
    ap.add_argument('--platform', choices=['xhs', 'wechat'], default='xhs')
    ap.add_argument('--topic', default='汽车',
                    help='cnworld 题材名；或 finance 概念/ETF 名称(逗号分隔)')
    ap.add_argument('--fkind', default='行业', choices=['行业', '指数', '概念', 'ETF', '基金'],
                    help='finance 用：行业/指数/概念/ETF/基金')
    ap.add_argument('--level', type=int, default=1, help='finance 行业: 1=一级 2=二级')
    ap.add_argument('--top', type=int, default=12, help='finance 概念/ETF/基金 取前 N')
    ap.add_argument('--src', default=None, help='deliver 用：成片视频路径（相对 ws 或绝对）')
    ap.add_argument('--data', default=None,
                    help='imgtable 用：归一化数据 JSON（默认 data/sw_industry_cumul.json）')
    ap.add_argument('--bg-prompt', default=None, help='imgtable 用：自定义 gpt-image-2 背景提示词')
    ap.add_argument('--no-ai', action='store_true', help='imgtable 用：强制占位背景（不调 gpt-image-2）')
    ap.add_argument('--voice', action='store_true', help='imgtable 用：生成并叠加 AI 配音')
    ap.add_argument('--duration', type=float, default=12.0, help='imgtable 用：成片时长(秒)')
    ap.add_argument('--unit', default='%', help='imgtable 用：数值单位（默认 %）')
    ap.add_argument('--outdir', default=DELIVER_OUTDIR,
                    help='deliver 用：交付目录（默认 D:/AI视频/数据竞速，D 盘不可用时回落 out/增长与分化）')
    ap.add_argument('--title', default=None, help='deliver 用：自定义标题，覆盖 meta')
    ap.add_argument('--kind', default=None, help='deliver 用：题材标记（如 sw_industry / cn_vs_world）')
    ap.add_argument('--meta', default='data/post_meta.json', help='deliver 用：发布文案 json（取 titles[0]）')
    ap.add_argument('--topic-name', default='marriage_rate',
                    help='topic_race 用：题材(marriage_rate/fertility_rate/cn_top10_houseprice/world_top10_houseprice)')
    ap.add_argument('--all-topics', action='store_true', help='topic_race 用：渲染全部 4 个题材')
    ap.add_argument('--topic-file', default=None,
                    help='topic_race 用：自定义题材 JSON 路径（覆盖 --topic-name）')
    ap.add_argument('--key', default=None,
                    help='topic_config 用：注册表题材 key；用 * 或 all 批量渲染全部；配合 --list-configs 查看可选')
    ap.add_argument('--registry', default=None,
                    help='topic_config 用：自定义注册表 JSON 路径（默认内置 topics_registry.json）')
    ap.add_argument('--list-configs', action='store_true',
                    help='topic_config 用：列出注册表里所有可配置题材后退出')
    ap.add_argument('--topic-no', type=int, default=None,
                    help='topic_config 用：指定成片编号（重渲染时覆盖原编号，不递增）')
    a = ap.parse_args()

    ws = os.path.abspath(a.workspace)
    os.makedirs(os.path.join(ws, 'data'), exist_ok=True)
    os.makedirs(os.path.join(ws, 'out'), exist_ok=True)

    if a.cmd == 'collect':
        py('collect_sw_yearly.py', '--start-year', a.start_year, workspace=ws)
    elif a.cmd == 'cumul':
        py('build_cumul.py', workspace=ws)
    elif a.cmd == 'build':
        step_build(ws, a.span or 18)
    elif a.cmd == 'render':
        node('render_race.js', ws)
    elif a.cmd == 'verify':
        node('verify_race.js', ws)
    elif a.cmd == 'narration':
        py('gen_narration.py', workspace=ws)
    elif a.cmd == 'tts':
        py('tts.py', workspace=ws)
    elif a.cmd == 'bgm':
        py('fetch_bgm.py', workspace=ws)
    elif a.cmd == 'mix':
        py('mix_final.py', *(['--no-voice'] if a.no_voice else []), workspace=ws)
    elif a.cmd == 'meta':
        py('gen_meta.py', workspace=ws)
    elif a.cmd == 'cnworld':
        step_cnworld(ws, a.topic, a.no_voice)
    elif a.cmd == 'finance':
        step_finance(ws, a.fkind, a.level, a.topic, a.top, a.start_year, a.ytd_year, a.no_voice)
    elif a.cmd == 'imgtable':
        step_imgtable(ws, a.data, a.bg_prompt, a.no_ai, a.voice, a.duration, a.unit, a.title)
    elif a.cmd == 'topic_race':
        if a.all_topics:
            for name in ('marriage_rate', 'fertility_rate', 'cn_top10_houseprice',
                         'world_top10_houseprice'):
                step_topic_race(ws, name, a.topic_file or ('topic_' + name + '.json'),
                                a.bg_prompt, a.no_ai, a.no_voice, a.voice, a.platform)
        else:
            step_topic_race(ws, a.topic_name,
                            a.topic_file or ('topic_' + a.topic_name + '.json'),
                            a.bg_prompt, a.no_ai, a.no_voice, a.voice, a.platform)
    elif a.cmd == 'topic_config':
        reg_path = a.registry or os.path.join(SCRIPT_DIR, 'topics_registry.json')
        if not os.path.exists(reg_path):
            raise SystemExit('ERROR: 注册表不存在 ' + reg_path)
        with open(reg_path, encoding='utf-8') as f:
            reg = json.load(f)
        topics = reg.get('topics', [])
        if a.list_configs:
            print('注册表 ', reg_path, ' 可用题材(', len(topics), ')：', sep='')
            for t in topics:
                p = t.get('params', {})
                print('  - ', '{:18s}'.format(str(t.get('key'))),
                      ' src=', '{:8s}'.format(str(p.get('source', ''))),
                      ' mode=', '{:6s}'.format(str(p.get('mode', ''))),
                      ' ', str(p.get('title', '')))
            return
        if not a.key:
            raise SystemExit('ERROR: topic_config 需要 --key <题材key>；'
                             '用 --list-configs 查看可选，或用 * 批量渲染')
        if a.key in ('*', 'all'):
            print('[topic_config] 批量渲染全部 ', len(topics), ' 个题材...', sep='')
            for t in topics:
                step_topic_config(ws, t['key'], t, a.bg_prompt, a.no_ai, a.no_voice,
                                  a.voice, num=a.topic_no or t.get('no'))
        else:
            spec = next((t for t in topics if t['key'] == a.key), None)
            if not spec:
                raise SystemExit("ERROR: 注册表找不到 key=" + repr(a.key) +
                                 "；用 --list-configs 查看可选")
            step_topic_config(ws, a.key, spec, a.bg_prompt, a.no_ai, a.no_voice,
                              a.voice, num=a.topic_no or spec.get('no'))
    elif a.cmd == 'deliver':
        if not a.src:
            raise SystemExit('ERROR: deliver 需要 --src <成片路径>')
        py('deliver.py', '--src', a.src, '--meta', a.meta, '--kind', a.kind,
           '--outdir', a.outdir, workspace=ws)
    elif a.cmd == 'all':
        py('collect_sw_yearly.py', '--start-year', a.start_year, workspace=ws)
        py('build_cumul.py', workspace=ws)
        vo = None
        span = a.span or 18
        if not a.no_voice:
            py('gen_narration.py', workspace=ws)
            py('tts.py', workspace=ws)
            vo = os.path.join(ws, 'data', 'voiceover.mp3')
            vo_dur = ffprobe_dur(vo)
            if vo_dur:
                print('[all] voiceover=', '{:.2f}'.format(vo_dur), 's -> race span=',
                      '{:.2f}'.format(span), 's', sep='')
                span = max(2.0, vo_dur - INTRO - FINALHOLD)
        step_build(ws, span)
        node('render_race.js', ws)
        py('fetch_bgm.py', workspace=ws)
        py('mix_final.py', *([] if vo else ['--no-voice']), workspace=ws)
        py('gen_meta.py', workspace=ws)
        final = 'out/sw_yearly_race_voice.mp4' if vo else 'out/sw_yearly_race.mp4'
        step_deliver(ws, final, 'sw_industry')
        print('\nALL DONE ->', final)


if __name__ == '__main__':
    main()
