#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""成片音频规格升级：把目录里「非立体声/48k」的 mp4 升级为
立体声 / 48kHz / -16 LUFS，画面（视频流）与数据原样保留。

背景：历史上 amix 跟随第一个输入把 68 支成片压成了单声道/44.1k。
这些片画面、数据、文案都没问题，唯一缺陷是音频规格。本脚本只重编码
音频（视频流 -c:v copy），不碰取数/文案/渲染，零网络、零内容漂移。

安全约束（与项目铁律一致）：
  · 绝不删除原片：先 os.replace 到 <dir>/_旧版_WARN_bak/ 备份；
  · 重编码产物先写临时文件，ffprobe 校验通过后才 os.replace 回原位；
  · 任一支校验失败 → 从备份回滚，不留下半成品。

用法：
  python tools/upgrade_audio_spec.py                       # 默认 D:\AI视频\数据竞速
  python tools/upgrade_audio_spec.py --dir <目录>
  python tools/upgrade_audio_spec.py --dry                 # 只列待修清单不执行
  python tools/upgrade_audio_spec.py --manifest <json>     # 顺带刷新清单 size_bytes
"""
import argparse, json, os, subprocess, sys, glob

FFMPEG = os.environ.get('FFMPEG', "C:/ProgramData/chocolatey/bin/ffmpeg")
FFPROBE = os.environ.get('FFPROBE', "C:/ProgramData/chocolatey/bin/ffprobe")

TARGET_CH = 2
TARGET_SR = 48000
# 与 scripts/mix_final.py 保持一致：先 aformat 成立体声 48k，再 loudnorm，再 aresample 兜底
AF = "aformat=channel_layouts=stereo:sample_rates=48000,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"


def probe_audio(path):
    try:
        out = subprocess.check_output(
            [FFPROBE, '-v', 'error', '-select_streams', 'a',
             '-show_entries', 'stream=channels,sample_rate',
             '-of', 'default=noprint_wrappers=1', path],
            stderr=subprocess.DEVNULL).decode()
        kv = dict(l.split('=', 1) for l in out.splitlines() if '=' in l)
        return int(kv.get('channels') or 0), int(kv.get('sample_rate') or 0)
    except Exception:
        return 0, 0


def needs_fix(path):
    ch, sr = probe_audio(path)
    return ch != TARGET_CH or sr != TARGET_SR


def reencode(src, dst):
    """仅重编码音频，视频流原样复制。"""
    cmd = [FFMPEG, '-y', '-i', src,
           '-c:v', 'copy',
           '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
           '-af', AF, dst]
    r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0


def update_manifest(manifest_path, d, done):
    try:
        m = json.load(open(manifest_path, encoding='utf-8'))
        videos = m.get('videos', [])
        by_file = {}
        for v in videos:
            by_file[v.get('file')] = v
        upd = 0
        for base in done:
            p = os.path.join(d, base)
            v = by_file.get(base)
            if v and os.path.exists(p):
                v['size_bytes'] = os.path.getsize(p)
                upd += 1
        if upd:
            json.dump(m, open(manifest_path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
            print('清单 size_bytes 更新 %d 条 -> %s' % (upd, manifest_path))
    except Exception as e:
        print('清单更新跳过（不影响成片）：', e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=os.environ.get('VIDEO_OUT_DIR', r'D:\AI视频\数据竞速'))
    ap.add_argument('--backup-dir', default=None,
                    help='备份目录（默认 <dir>/_旧版_WARN_bak）')
    ap.add_argument('--manifest', default=r'D:\AI视频\manifest.json')
    ap.add_argument('--dry', action='store_true', help='只列待修清单不执行')
    a = ap.parse_args()

    d = os.path.abspath(a.dir)
    bak = os.path.abspath(a.backup_dir) if a.backup_dir else os.path.join(d, '_旧版_WARN_bak')
    os.makedirs(bak, exist_ok=True)

    files = sorted(glob.glob(os.path.join(d, '*.mp4')))
    todo = [f for f in files if needs_fix(f)]
    print('扫描 %d 支，待修 %d 支，备份目录 %s' % (len(files), len(todo), bak))
    if a.dry:
        for f in todo:
            ch, sr = probe_audio(f)
            print('  [待修] %s  %dch/%dHz' % (os.path.basename(f), ch, sr))
        return 0

    done, fail = [], []
    for f in todo:
        base = os.path.basename(f)
        bp = os.path.join(bak, base)
        tmp = f + '.tmp_upgrade.mp4'
        # 1) 备份原片（移动，不删除）
        if not os.path.exists(bp):
            os.replace(f, bp)
        # 2) 从备份重编码音频 -> 临时文件
        ok = reencode(bp, tmp)
        # 3) 校验临时文件规格，通过才落回原位
        if ok and not needs_fix(tmp):
            os.replace(tmp, f)
            done.append(base)
            print('✔ %s  (%d/%d)' % (base, len(done), len(todo)))
        else:
            # 回滚：优先用临时产物还原，否则从备份还原
            if os.path.exists(tmp):
                os.replace(tmp, f)
            elif os.path.exists(bp):
                os.replace(bp, f)
            fail.append(base)
            print('✘ FAIL %s（已回滚原片）' % base)
        # 清理可能残留的临时文件
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

    if done and os.path.exists(a.manifest):
        update_manifest(a.manifest, d, done)

    print('\n=== 升级完成：成功 %d / 失败 %d ===' % (len(done), len(fail)))
    if fail:
        print('失败清单：', ', '.join(fail))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
