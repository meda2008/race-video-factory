#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交付成片全量体检：扫 D:\\AI视频\\<项目>\\*.mp4，逐支查规格并在结尾给汇总。

为什么需要：出片后没人逐支 ffprobe，历史上出现过
  · TTS 静默截断 → 553 字的稿子只出 20.6s，整支片被压成 20.7s 交付；
  · amix 输出跟随第一个输入 → 68 支全是单声道（应为立体声 48k）；
  · 混音静音 bug → 成片平均音量 -91 dB。
这些都是"看一眼缩略图发现不了"的问题，必须靠脚本兜。

用法：
  python tools/qa_delivered.py                       # 体检默认目录 D:\\AI视频\\数据竞速
  python tools/qa_delivered.py --dir <目录>          # 指定目录
  python tools/qa_delivered.py --json out.json       # 顺带落一份 JSON
  python tools/qa_delivered.py --md 体检报告.md       # 顺带落一份 Markdown

退出码：0 = 全部通过；1 = 有 FAIL（便于挂 CI / 批量后自检）。
"""
import argparse, json, os, re, subprocess, sys, glob

FFMPEG = os.environ.get('FFMPEG', "C:/ProgramData/chocolatey/bin/ffmpeg")
FFPROBE = os.environ.get('FFPROBE', "C:/ProgramData/chocolatey/bin/ffprobe")

# 成片规格（与 scripts/mix_final.py 保持一致）
SPEC = {
    'min_dur': 18.0, 'max_dur': 125.0,
    'channels': 2, 'sample_rate': 48000,
    'min_mean_db': -45.0,      # 平均音量低于它 = 疑似静音/哑片
    'width': 1080, 'height': 1624,
}
# 老片（2026-09-16 之前出的）是 单声道/44.1k，属历史遗留：报 WARN 而非 FAIL
LEGACY_BEFORE = '2026-09-16'
CHARS_PER_SEC = 4.8      # 与 fit_narration / tts 一致
TRUNC_RATIO = 0.6        # 实测时长 < 字数预期 × 0.6 → 判定 TTS 截断


def probe(path):
    """取一支片的关键规格。"""
    d = {'file': os.path.basename(path), 'ok': True, 'issues': []}
    try:
        out = subprocess.check_output(
            [FFPROBE, '-v', 'error', '-show_entries',
             'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path],
            stderr=subprocess.DEVNULL).decode().strip()
        d['duration'] = float(out)
    except Exception:
        d['duration'] = None
        d['issues'].append('无法读取时长')
    try:
        out = subprocess.check_output(
            [FFPROBE, '-v', 'error', '-select_streams', 'v',
             '-show_entries', 'stream=width,height',
             '-of', 'default=noprint_wrappers=1', path], stderr=subprocess.DEVNULL).decode()
        kv = dict(l.split('=', 1) for l in out.splitlines() if '=' in l)
        d['width'], d['height'] = int(kv['width']), int(kv['height'])
    except Exception:
        d['width'] = d['height'] = None
    try:
        # 注意：ffprobe 的 csv 输出顺序由它自己决定，不能按请求顺序拆，
        # 必须用 key=value（noprint_wrappers）解析，否则 声道/采样率 会互换。
        out = subprocess.check_output(
            [FFPROBE, '-v', 'error', '-select_streams', 'a',
             '-show_entries', 'stream=channels,sample_rate',
             '-of', 'default=noprint_wrappers=1', path], stderr=subprocess.DEVNULL).decode()
        kv = dict(l.split('=', 1) for l in out.splitlines() if '=' in l)
        if kv.get('channels'):
            d['channels'] = int(kv['channels'])
            d['sample_rate'] = int(kv['sample_rate'])
        else:
            d['channels'] = d['sample_rate'] = None
            d['issues'].append('无音轨')
    except Exception:
        d['channels'] = d['sample_rate'] = None
        d['issues'].append('无音轨')
    if d.get('channels'):
        p = subprocess.run([FFMPEG, '-i', path, '-af', 'volumedetect', '-f', 'null', '-'],
                           stderr=subprocess.PIPE, text=True)
        m = re.search(r'mean_volume:\s*([-\d.]+)', p.stderr)
        d['mean_db'] = float(m.group(1)) if m else None
    return d


def grade(d, spec=SPEC, legacy=False):
    """给一支片打分：PASS / WARN / FAIL，并写清原因。"""
    if d['duration'] is None:
        return 'FAIL'
    dur, ch, sr, db = d['duration'], d.get('channels'), d.get('sample_rate'), d.get('mean_db')
    reasons = []
    if dur < spec['min_dur']:
        reasons.append('时长 %.1fs < 下限 %.0fs（疑似 TTS 截断/渲染不全）' % (dur, spec['min_dur']))
    elif dur > spec['max_dur']:
        reasons.append('时长 %.1fs > 上限 %.0fs' % (dur, spec['max_dur']))
    if ch is None:
        reasons.append('无音轨')
    elif ch != spec['channels']:
        reasons.append('%d 声道（应 %d）' % (ch, spec['channels']))
    if sr and sr != spec['sample_rate']:
        reasons.append('%d Hz（应 %d）' % (sr, spec['sample_rate']))
    if db is not None and db < spec['min_mean_db']:
        reasons.append('平均音量 %.1f dB（疑似哑片）' % db)
    if d.get('width') and (d['width'], d['height']) != (spec['width'], spec['height']):
        reasons.append('分辨率 %sx%s（应 %sx%s）'
                       % (d['width'], d['height'], spec['width'], spec['height']))
    d['reasons'] = reasons
    if not reasons:
        return 'PASS'
    # 声道/采样率不达标在新旧片里含义不同：老片是历史遗留，只提醒不判死
    soft = [r for r in reasons if '声道' in r or 'Hz' in r]
    return 'WARN' if (legacy and len(soft) == len(reasons)) else 'FAIL'


def mtime_date(path):
    import datetime
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=os.environ.get('VIDEO_OUT_DIR', r'D:\AI视频\数据竞速'))
    ap.add_argument('--json', default=None, help='额外输出 JSON')
    ap.add_argument('--md', default=None, help='额外输出 Markdown 报告')
    ap.add_argument('--spec-height', type=int, default=SPEC['height'])
    ap.add_argument('--narr-dir', default=None,
                    help='口播稿目录（<ws>/data）。给了就额外做「TTS 截断」深检')
    ap.add_argument('--slug2no', default=None,
                    help='题材key→成片编号的 JSON（<ws>/data/slug2no.json）')
    a = ap.parse_args()
    SPEC['height'] = a.spec_height

    files = sorted(glob.glob(os.path.join(a.dir, '*.mp4')))
    if not files:
        print('没有找到 mp4：', a.dir)
        return 1
    rows = []
    for f in files:
        d = probe(f)
        d['date'] = mtime_date(f)
        d['grade'] = grade(d, legacy=(d['date'] < LEGACY_BEFORE))
        rows.append(d)

    # 「TTS 截断」深检：成片时长 vs 口播稿字数预期
    trunc = []
    if a.narr_dir and a.slug2no and os.path.isfile(a.slug2no):
        s2n = json.load(open(a.slug2no, encoding='utf-8'))
        bynum = {os.path.basename(f)[:3]: r for r in rows}
        for slug, no in s2n.items():
            p = os.path.join(a.narr_dir, 'topic_%s_narration.txt' % slug)
            if not os.path.exists(p):
                continue
            r = bynum.get('%03d' % int(no))
            if not r or not r.get('duration'):
                continue
            n = len(re.sub(r'\s', '', open(p, encoding='utf-8').read()))
            exp = n / CHARS_PER_SEC
            if exp > 10 and r['duration'] < exp * TRUNC_RATIO:
                r['reasons'].append('疑似 TTS 截断：%.1fs / 口播稿 %d 字预期 %.1fs'
                                    % (r['duration'], n, exp))
                r['grade'] = 'FAIL'
                trunc.append((r['file'], r['duration'], n, exp))

    npass = sum(1 for r in rows if r['grade'] == 'PASS')
    nwarn = sum(1 for r in rows if r['grade'] == 'WARN')
    nfail = sum(1 for r in rows if r['grade'] == 'FAIL')
    durs = [r['duration'] for r in rows if r['duration']]

    print('\n=== 交付体检：%s ===' % a.dir)
    print('共 %d 支｜PASS %d｜WARN %d｜FAIL %d' % (len(rows), npass, nwarn, nfail))
    if durs:
        print('时长：最短 %.1fs｜最长 %.1fs｜平均 %.1fs｜合计 %.1f 分钟'
              % (min(durs), max(durs), sum(durs) / len(durs), sum(durs) / 60))
    print('\n| 评级 | 文件 | 时长 | 声道 | 采样率 | 音量 | 问题 |')
    print('|:-:|---|---:|:-:|--:|--:|---|')
    for r in rows:
        if r['grade'] == 'PASS':
            continue
        print('| %s | %s | %s | %s | %s | %s | %s |' % (
            r['grade'], r['file'][:44],
            '%.1fs' % r['duration'] if r['duration'] else '?',
            r.get('channels') or '-', r.get('sample_rate') or '-',
            '%.1fdB' % r['mean_db'] if r.get('mean_db') is not None else '-',
            '；'.join(r['reasons'])))
    if trunc:
        print('\n⚠️ 疑似 TTS 截断（画面早跑完、旁白才念几句）：')
        for f, d, n, exp in trunc:
            print('  · %s  %.1fs / 稿 %d 字 → 预期 %.1fs' % (f, d, n, exp))
    if nfail == 0 and nwarn == 0:
        print('\n全部通过 ✔')

    if a.json:
        json.dump(rows, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('\nJSON ->', a.json)
    if a.md:
        with open(a.md, 'w', encoding='utf-8') as f:
            f.write('# 交付成片体检报告\n\n目录：`%s`\n\n' % a.dir)
            f.write('共 %d 支｜PASS %d｜WARN %d｜FAIL %d\n\n' % (len(rows), npass, nwarn, nfail))
            f.write('| 评级 | 文件 | 时长 | 声道 | 采样率 | 音量 | 问题 |\n')
            f.write('|:-:|---|---:|:-:|--:|--:|---|\n')
            for r in rows:
                if r['grade'] == 'PASS' and len(rows) > 30:
                    continue
                f.write('| %s | %s | %s | %s | %s | %s | %s |\n' % (
                    r['grade'], r['file'],
                    '%.1fs' % r['duration'] if r['duration'] else '?',
                    r.get('channels') or '-', r.get('sample_rate') or '-',
                    '%.1fdB' % r['mean_db'] if r.get('mean_db') is not None else '-',
                    '；'.join(r['reasons']) or '-'))
        print('Markdown ->', a.md)
    return 1 if nfail else 0


if __name__ == '__main__':
    sys.exit(main())
