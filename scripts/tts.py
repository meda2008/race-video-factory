#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 narration.txt 合成为中文配音（Azure Speech 优先，edge-tts 兜底）。

用法：
  python tts.py --workspace <ws>
读取 <ws>/.env 中的 AZURE_SPEECH_KEY / AZURE_SPEECH_REGION（默认 eastasia）
读取 <ws>/data/narration.txt
写出 <ws>/data/voiceover.mp3 并打印时长（秒）
仅依赖 requests（无需 azure SDK）。

可选参数（供其它分支复用，不传则保持原行为）：
  --src <口播稿路径>   默认 data/narration.txt
  --out <配音输出路径> 默认 data/voiceover.mp3
  --rate <语速倍率>    1.0=正常；1.2=快 20%

⚠️ 2026-09-16 修复：「TTS 静默截断」
  长稿走 edge-tts 时，WS 连接中途被重置后 `Communicate.save()` 不报错、
  只写出前面一小段（实测 553 字只写出 20.6s，整支片被压成 20.7s）。
  现在改为：按句切成 ≤220 字的块 → 逐块合成（每块最多重试 4 次）→
  逐块校验时长是否匹配字数 → 拼接。任一块不达标就非零退出，
  由 run.py 的三次重试兜底，**绝不让截断的配音流入成片**。
"""
import argparse, asyncio, os, re, subprocess, sys, glob, requests

FFMPEG = "C:/ProgramData/chocolatey/bin/ffmpeg"
FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe"

# 中文播报实测 ≈4.8 字/秒（与 fit_narration.CHARS_PER_SEC 保持一致）
CHARS_PER_SEC = 4.8
# 实测时长 / 预期时长 低于该比例即判定为「截断」
MIN_OK_RATIO = 0.55
# 单块最大字数（越大越省事，越小越抗网络抖动）
CHUNK_CHARS = 220


def _n_chars(text):
    return len(re.sub(r'\s', '', text or ''))


def _probe_dur(path):
    try:
        return float(subprocess.check_output(
            [FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            stderr=subprocess.DEVNULL).decode().strip())
    except Exception:
        return None


def split_chunks(text, max_chars=CHUNK_CHARS):
    """按句切块：句号/问号/叹号/分号/换行处分句，累积到 max_chars 成一块。

    长句本身超过 max_chars 时，再按逗号/顿号硬切，避免单块过大导致 WS 超时。
    """
    text = re.sub(r'\s+', ' ', (text or '').strip())
    if not text:
        return []
    sents = [s for s in re.split(r'(?<=[。！？；;！\n])', text) if s.strip()]
    if len(sents) == 1 and len(sents[0]) > max_chars:
        sents = [s for s in re.split(r'(?<=[，,、])', sents[0]) if s.strip()]

    chunks, cur = [], ''
    for s in sents:
        if cur and len(cur) + len(s) > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur += s
        while len(cur) > max_chars * 1.5:      # 极端长句：硬切
            chunks.append(cur[:max_chars])
            cur = cur[max_chars:]
    if cur.strip():
        chunks.append(cur)
    return [c for c in (x.strip() for x in chunks) if c]


async def _synth_one(text, voice, out_path, rate=None, tries=4):
    """合成单个分块并校验时长。成功返回时长(秒)，失败返回 None。"""
    import edge_tts
    kw = {}
    if rate is not None and abs(rate - 1.0) > 1e-6:
        kw['rate'] = '%+d%%' % round((rate - 1.0) * 100)
    expect = max(1.0, _n_chars(text) / CHARS_PER_SEC / max(0.5, rate or 1.0))
    last = None
    for i in range(1, tries + 1):
        try:
            comm = edge_tts.Communicate(text, voice, **kw)
            await comm.save(out_path)
            d = _probe_dur(out_path)
            if d and d >= expect * MIN_OK_RATIO:
                return d
            last = '时长 %.1fs 短于预期 %.1fs（疑似 WS 中断截断）' % (d or 0.0, expect)
        except Exception as e:
            last = '%s: %s' % (type(e).__name__, e)
        print('[tts] 分块第 %d/%d 次失败：%s' % (i, tries, last))
        await asyncio.sleep(1.5 * i)
    return None


def _concat(chunks_paths, out):
    """把分块 mp3 拼成一条。多块走 concat 解复用器重编码，单块直接搬运。"""
    if len(chunks_paths) == 1:
        with open(chunks_paths[0], 'rb') as a, open(out, 'wb') as b:
            b.write(a.read())
        return
    lst = os.path.abspath(out) + '.parts.txt'
    with open(lst, 'w', encoding='utf-8') as f:
        for p in chunks_paths:
            # concat 里的相对路径按「清单文件所在目录」解析，必须用绝对路径
            f.write("file '%s'\n" % os.path.abspath(p).replace('\\', '/').replace("'", "'\\''"))
    # 不吞 stderr：拼接失败时（路径/编码器问题）要能看到原因
    subprocess.run([FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', lst,
                    '-c:a', 'libmp3lame', '-b:a', '64k', out], check=True)


def synth_edge(text, out, rate=1.0):
    """分块合成 + 逐块校验 + 拼接。任一环节不达标直接抛错（由上层重试）。"""
    import edge_tts  # noqa: F401
    tmpdir = out + '.parts'
    os.makedirs(tmpdir, exist_ok=True)
    chunks = split_chunks(text)
    print('[tts] edge-tts 分块合成：%d 块（共 %d 字）' % (len(chunks), _n_chars(text)))
    parts, total = [], 0.0
    for i, c in enumerate(chunks):
        p = os.path.join(tmpdir, 'p%03d.mp3' % i)
        d = asyncio.run(_synth_one(c, 'zh-CN-YunxiNeural', p, rate=rate))
        if d is None:
            raise RuntimeError('edge-tts 分块 %d/%d 合成失败（已重试 4 次）' % (i + 1, len(chunks)))
        parts.append(p)
        total += d
    _concat(parts, out)
    expect = max(1.0, _n_chars(text) / CHARS_PER_SEC / max(0.5, rate))
    got = _probe_dur(out) or total
    if got < expect * MIN_OK_RATIO:
        raise RuntimeError('edge-tts 合成结果偏短：%.1fs / 预期 %.1fs（判定为截断）'
                           % (got, expect))
    try:
        for p in glob.glob(os.path.join(tmpdir, 'p*.mp3')):
            os.replace(p, p + '.done')      # 不删除：safe-delete 守卫会杀进程
    except OSError:
        pass
    return got


def synth_azure(text, out, key, region, rate=1.0):
    SSML = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='zh-CN'>
  <voice name='zh-CN-YunxiNeural'>
    <mstts:express-as style='narration-relaxed'>
      <prosody rate='{rate:.2f}' pitch='0%'>
        {text}
      </prosody>
    </mstts:express-as>
  </voice>
</speak>"""
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        # 48kHz 单声道：成片最终会被 mix_final 统一成 立体声 48k，
        # 源用 16kHz 会让 loudnorm 后齿音明显发闷。
        "X-Microsoft-OutputFormat": "audio-48khz-192kbitrate-mono-mp3",
    }
    r = requests.post(url, data=SSML.encode("utf-8"), headers=headers, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"TTS ERROR {r.status_code}: {r.text[:300]}")
    with open(out, "wb") as f:
        f.write(r.content)
    got = _probe_dur(out)
    expect = max(1.0, _n_chars(text) / CHARS_PER_SEC / max(0.5, rate))
    if got is not None and got < expect * MIN_OK_RATIO:
        raise RuntimeError('Azure 合成结果偏短：%.1fs / 预期 %.1fs（判定为截断）' % (got, expect))
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--src', default=None, help='口播稿路径（默认 data/narration.txt）')
    ap.add_argument('--out', default=None, help='配音输出路径（默认 data/voiceover.mp3）')
    ap.add_argument('--rate', type=float, default=1.0,
                    help='语速倍率（1.0=正常；1.2=快20%%）。用于把超长口播压缩进目标时长')
    a = ap.parse_args()
    rate = max(0.5, min(2.0, a.rate))
    ws = os.path.abspath(a.workspace)

    env = {}
    # 向上逐级查找 .env（workspace 常在子目录，密钥在项目根目录）
    cur = ws
    for _ in range(6):
        p = os.path.join(cur, ".env")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    KEY = (env.get("AZURE_SPEECH_KEY") or "").strip()
    REGION = (env.get("AZURE_SPEECH_REGION") or "eastasia").strip()

    src = a.src or os.path.join(ws, "data", "narration.txt")
    out = a.out or os.path.join(ws, "data", "voiceover.mp3")
    text = open(src, encoding="utf-8").read().strip()
    # emoji 喂给 TTS 会读出乱码/跳过，统一剔除
    EMOJI = re.compile(
        r'[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u25A0-\u25FF\u2B00-\u2BFF\uFE0F]')
    text = EMOJI.sub('', text)

    if not KEY:
        print('[tts][warn] AZURE_SPEECH_KEY 未配置 → 走 edge-tts 兜底'
              '（免密钥但抗抖动差，长稿有截断风险；配了 key 会稳得多）', file=sys.stderr)
        got = synth_edge(text, out, rate=rate)
    else:
        try:
            got = synth_azure(text, out, KEY, REGION, rate=rate)
        except Exception as e:
            print('[tts][warn] Azure 失败，回退 edge-tts：%r' % (e,), file=sys.stderr)
            got = synth_edge(text, out, rate=rate)

    print("wrote", out, os.path.getsize(out), "bytes")
    print("DURATION", "%.2f" % got if got is not None else "?")
    print("[tts] 字数 %d → 预期 %.1fs → 实测 %.1fs"
          % (_n_chars(text), _n_chars(text) / CHARS_PER_SEC / max(0.5, rate), got or 0.0))


if __name__ == '__main__':
    main()
