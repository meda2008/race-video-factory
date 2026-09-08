#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""最终合成：帧 -> 静音视频，再混音（配音主 + BGM 循环 ducking 压低 / 仅 BGM / 兜底粉噪）。

用法：
  python mix_final.py --workspace <ws> [--no-voice]
读取：
  <ws>/out/frames/f*.jpg        渲染帧（0..N）
  <ws>/data/voiceover.mp3       （可选）配音
  <ws>/data/bgm/bgm.mp3         （可选）BGM
写出：
  <ws>/out/_silent.mp4          静音画面
  <ws>/out/_audio.m4a           混音轨
  <ws>/out/sw_yearly_race_voice.mp4  最终成片

关键对齐（本机验证）：
- 视频时长 = N / 30 秒（N = 最大帧序号）。
- 配音满音量；BGM 基准 0.22，有人声时由 sidechaincompress 自动下压。
- 结尾用 `-t <dur>` 截断到视频长度（本机构 ffmpeg 7.1.1 的 afade=t=out 会让整条
  音轨在 ~12s 后变静音，故不使用 afade，直接硬截断，结尾可接受）。

!!! 已踩坑（务必遵守）!!!
1. **绝不可把 `-stream_loop -1` 的 BGM 直接喂给 amix / sidechaincompress**：
   ffmpeg 会在混合约 12s 后把整条音轨变成静音（-91 dB）。
2. **也不可先把 BGM 重新编码成 mp3 循环文件再喂 amix**：重编码后的 mp3
   同样会让 sidechaincompress+amix 在 ~12s 后静音（疑似 mp3 帧/priming 干扰）。
3. **正确做法**：直接用原始 `bgm/bgm.mp3`（不循环、不重编码）喂 sidechaincompress，
   并在 amix 后保留输出 `-t <dur>` 截断到视频长度。要求 BGM 源长于视频
   （本项目 SoundHelix 曲库 5+ 分钟，视频均 ≤ ~75s，满足）。
- 无配音时：有 BGM 则铺到 0.22；无 BGM 则 ffmpeg 生成粉噪兜底。
"""
import argparse, os, re, subprocess, glob

FF = "C:/ProgramData/chocolatey/bin/ffmpeg"
FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe"
FPS = 30


def run(cmd):
    print('+', ' '.join(cmd))
    subprocess.run(cmd, check=True)


def _audio_mean_db(path):
    """用 ffmpeg volumedetect 取整片平均音量(dB)。正常混音约 -25dB；静音片约 -91dB。"""
    p = subprocess.run([FF, '-i', path, '-af', 'volumedetect', '-f', 'null', '-'],
                       stderr=subprocess.PIPE, text=True)
    m = re.search(r'mean_volume:\s*([-\d.]+)', p.stderr)
    return float(m.group(1)) if m else None


def _check_audio(path, video_dur, vo_dur=None):
    """混音后自检：① 整片平均音量过低 => 疑似静音 bug，拒绝交付；② 配音与视频时长差过大 => 告警。"""
    mean = _audio_mean_db(path)
    if mean is None:
        print('[mix][warn] 无法测得当量音量，跳过静音自检')
        return
    if mean < -60:
        raise SystemExit(
            f"ERROR 静音自检失败：成片平均音量 {mean:.1f} dB（疑似混音静音 bug），"
            f"已拒绝交付。请检查 BGM 输入是否为原始 mp3（勿用 stream_loop/重编码）与滤镜链。")
    print(f'[mix] 静音自检通过：平均音量 {mean:.1f} dB')
    if vo_dur is not None and abs(vo_dur - video_dur) > 8:
        print(f'[mix][warn] 配音({vo_dur:.1f}s) 与视频({video_dur:.1f}s) 相差 '
              f'{abs(vo_dur - video_dur):.1f}s，可能头尾留白或截断')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--frames-dir', default='out/frames', help='渲染帧目录（默认 out/frames）')
    ap.add_argument('--no-voice', action='store_true')
    ap.add_argument('--out', default=None, help='最终成片输出路径（默认 out/sw_yearly_race_voice.mp4）')
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    out = os.path.join(ws, 'out')
    data = os.path.join(ws, 'data')
    frames = os.path.join(ws, a.frames_dir)
    frames_relpath = os.path.relpath(frames, out)
    vo = os.path.join(data, 'voiceover.mp3')
    bgm = os.path.join(data, 'bgm', 'bgm.mp3')
    final = os.path.join(out, a.out) if a.out else os.path.join(out, 'sw_yearly_race_voice.mp4')
    silent = os.path.join(out, '_silent.mp4')
    aud = os.path.join(out, '_audio.m4a')

    fr = sorted(glob.glob(os.path.join(frames, 'f*.jpg')))
    if not fr:
        raise SystemExit(f"ERROR: 没有帧文件 {frames}")
    idxs = [int(os.path.basename(f)[1:6]) for f in fr]
    N = max(idxs)
    dur = N / FPS
    print(f"[mix] frames=0..{N} video_dur={dur:.3f}s")

    fl = os.path.join(out, 'filelist.txt')
    with open(fl, 'w') as f:
        for i in range(N + 1):
            f.write(f"file '{frames_relpath}/f{i:05d}.jpg'\nduration 0.033333\n")

    run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', fl,
         '-vf', 'format=yuv420p', '-r', '30',
         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-color_range', '1', '-crf', '20', '-preset', 'medium', silent])

    use_voice = (not a.no_voice) and os.path.exists(vo)
    use_bgm = os.path.exists(bgm)

    if use_voice and use_bgm:
        # 原始 bgm.mp3 直接喂 sidechaincompress；输出 -t 截到视频长度。
        # 严禁 stream_loop / 重编码（会导致 ~12s 后整条静音，见文件头说明）。
        run([FF, '-y', '-i', vo, '-i', bgm,
             '-filter_complex',
             "[0:a]aresample=44100,volume=1.0[voc];"
             "[1:a]aresample=44100,volume=0.22[bgm];"
             "[bgm][voc]sidechaincompress=threshold=0.06:ratio=3.5:attack=15:release=250[duck];"
             "[voc][duck]amix=inputs=2:duration=longest:normalize=0[out]",
             '-map', '[out]', '-t', f"{dur}", '-ar', '44100', '-c:a', 'aac', '-b:a', '192k', aud])
    elif use_voice:  # 配音 + 粉噪兜底 BGM
        run([FF, '-y', '-i', vo, '-f', 'lavfi', '-i', f"anoisesrc=color=pink:duration={dur}:sample_rate=44100",
             '-filter_complex',
             "[0:a]aresample=44100,volume=1.0[voc];"
             "[1:a]aresample=44100,lowpass=f=1200,volume=0.12[bgm];"
             "[voc][bgm]amix=inputs=2:duration=longest:normalize=0[out]",
             '-map', '[out]', '-t', f"{dur}", '-ar', '44100', '-c:a', 'aac', '-b:a', '192k', aud])
    elif use_bgm:  # 仅 BGM
        run([FF, '-y', '-i', bgm,
             '-filter_complex', "[0:a]aresample=44100,volume=0.22[a]",
             '-map', '[a]', '-t', f"{dur}", '-ar', '44100', '-c:a', 'aac', '-b:a', '192k', aud])
    else:  # 纯粉噪兜底
        run([FF, '-y', '-f', 'lavfi', '-i', f"anoisesrc=color=pink:duration={dur}:sample_rate=44100",
             '-filter_complex', "lowpass=f=1200,afade=t=in:d=1,afade=t=out:d=2,volume=0.5",
             '-t', f"{dur}", '-c:a', 'aac', '-b:a', '128k', aud])

    run([FF, '-y', '-i', silent, '-i', aud, '-c', 'copy', '-movflags', '+faststart', final])
    print('[mix] DONE ->', final)
    print(subprocess.check_output([FFPROBE, '-v', 'error',
          '-show_entries', 'format=duration,size',
          '-show_entries', 'stream=width,height,codec_name,codec_type,r_frame_rate',
          '-of', 'default=noprint_wrappers=1', final]).decode())

    # --- 静音自检 + 长度校验（防止本机 ffmpeg 7.1.1 的 ~12s 后整条静音 bug 漏出）---
    vo_dur = None
    if os.path.exists(vo):
        try:
            vo_dur = float(subprocess.check_output(
                [FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', vo]).decode().strip())
        except Exception:
            vo_dur = None
    _check_audio(final, dur, vo_dur)


if __name__ == '__main__':
    main()
