#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用 Azure Speech REST API 把 narration.txt 合成为中文配音（zh-CN-YunxiNeural）。

用法：
  python tts.py --workspace <ws>
读取 <ws>/.env 中的 AZURE_SPEECH_KEY / AZURE_SPEECH_REGION（默认 eastasia）
读取 <ws>/data/narration.txt
写出 <ws>/data/voiceover.mp3 并打印时长（秒）
仅依赖 requests（无需 azure SDK）。

可选参数（供其它分支复用，不传则保持原行为）：
  --src <口播稿路径>   默认 data/narration.txt
  --out <配音输出路径> 默认 data/voiceover.mp3
"""
import argparse, os, sys, requests, subprocess

FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe"


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

    KEY = env.get("AZURE_SPEECH_KEY")
    REGION = env.get("AZURE_SPEECH_REGION") or "eastasia"

    src = a.src or os.path.join(ws, "data", "narration.txt")
    out = a.out or os.path.join(ws, "data", "voiceover.mp3")
    text = open(src, encoding="utf-8").read().strip()

    if not KEY:
        # 无 Azure 密钥 → 回退免费 edge-tts（zh-CN-YunxiNeural），无需任何凭证
        try:
            import asyncio, re as _re, edge_tts
        except Exception as e:
            sys.exit(f"ERROR: AZURE_SPEECH_KEY 缺失且无法加载 edge_tts：{e}")
        EMOJI = _re.compile(
            r'[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u25A0-\u25FF\u2B00-\u2BFF\uFE0F]')
        tts_text = EMOJI.sub('', text)
        tts_text = _re.sub(r'\s+', ' ', tts_text).strip()  # 折叠换行/多余空格

        async def _run():
            # edge-tts 的 rate 形如 "+20%" / "-10%"
            kw = {}
            if abs(rate - 1.0) > 1e-6:
                kw['rate'] = '%+d%%' % round((rate - 1.0) * 100)
            comm = edge_tts.Communicate(tts_text, "zh-CN-YunxiNeural", **kw)
            await comm.save(out)

        asyncio.run(_run())
        print("wrote (edge-tts)", out, os.path.getsize(out), "bytes")
        try:
            dur = subprocess.check_output([FFPROBE, "-v", "error", "-show_entries",
                                           "format=duration", "-of",
                                           "default=noprint_wrappers=1:nokey=1", out]).decode().strip()
            print("DURATION", dur)
        except Exception as e:
            print("probe fail", e)
        return
    SSML = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='zh-CN'>
  <voice name='zh-CN-YunxiNeural'>
    <mstts:express-as style='narration-relaxed'>
      <prosody rate='{rate:.2f}' pitch='0%'>
        {text}
      </prosody>
    </mstts:express-as>
  </voice>
</speak>"""

    url = f"https://{REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
    }
    r = requests.post(url, data=SSML.encode("utf-8"), headers=headers, timeout=120)
    if r.status_code != 200:
        sys.exit(f"TTS ERROR {r.status_code}: {r.text[:500]}")

    with open(out, "wb") as f:
        f.write(r.content)
    print("wrote", out, "bytes", len(r.content))

    try:
        dur = subprocess.check_output([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                       "-of", "default=noprint_wrappers=1:nokey=1", out]).decode().strip()
        print("DURATION", dur)
    except Exception as e:
        print("probe fail", e)


if __name__ == '__main__':
    main()
