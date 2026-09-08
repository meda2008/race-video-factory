#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""自动搜索下载匹配视频内容的无版权 BGM。

用法：
  python fetch_bgm.py --workspace <ws>
读取 <ws>/data/bgm_config.json（风格来自其它对话的 bgm_brief.md：电子/light tech house/124BPM）
依次尝试 candidates 中的直链，下载并校验；成功则存为 <ws>/data/bgm/bgm.mp3，回写 chosen_*。
全部失败则写 _NO_DOWNLOAD 标记，交由 mix_final.py 用 ffmpeg 生成兜底 BGM。
"""
import argparse, json, subprocess, os

FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    cfg_path = os.path.join(ws, 'data', 'bgm_config.json')
    if not os.path.exists(cfg_path):
        raise SystemExit(f"ERROR: 找不到 {cfg_path}（需先放置 bgm_config.json）")
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    cands = cfg.get('candidates', [])
    outdir = os.path.join(ws, 'data', 'bgm')
    os.makedirs(outdir, exist_ok=True)
    chosen = None

    # 缓存命中即跳过：bgm.mp3 已存在且有效则不再联网重试（避免慢网卡死）
    dst = os.path.join(outdir, 'bgm.mp3')
    if os.path.exists(dst) and os.path.getsize(dst) >= 50000:
        try:
            dur = float(subprocess.check_output(
                [FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', dst]).decode().strip())
            if dur >= 20:
                print(f'SKIP: bgm.mp3 already valid (dur={dur:.1f}s), skip download')
                cfg['chosen_source'] = cfg.get('chosen_source') or '(cached)'
                cfg['chosen_duration'] = round(dur, 2)
                json.dump(cfg, open(cfg_path, 'w', encoding='utf-8'),
                          ensure_ascii=False, indent=2)
                return
        except Exception as e:
            print('cache probe failed, will re-download:', e)

    for url in cands:
        print("TRY", url)
        tmp = os.path.join(outdir, '_cand.mp3')
        rc = subprocess.run(["curl", "-L", "--max-time", "550", "-o", tmp, url],
                            capture_output=True, text=True).returncode
        if rc != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 50000:
            print("  failed/small, rc=", rc)
            continue
        try:
            dur = float(subprocess.check_output([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                                 "-of", "default=noprint_wrappers=1:nokey=1", tmp]).decode().strip())
        except Exception as e:
            print("  probe fail", e)
            continue
        if dur < 20:
            print("  too short", dur)
            continue
        dst = os.path.join(outdir, "bgm.mp3")
        if os.path.exists(dst):
            os.remove(dst)
        os.replace(tmp, dst)
        chosen = url
        cfg["chosen_source"] = url
        cfg["chosen_duration"] = round(dur, 2)
        cfg["license_note"] = ("SoundHelix 示例曲为免费可商用 Demo 曲库；若用于正式发布，"
                               "建议替换为 CC 署名曲（如 Mixaund《Technology Business》，需在视频简介署名）。")
        print("CHOSEN", url, "dur", dur)
        break

    json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if not chosen:
        print("NO_DOWNLOAD: all candidates failed")
        open(os.path.join(outdir, "_NO_DOWNLOAD"), "w").write("1")


if __name__ == '__main__':
    main()
