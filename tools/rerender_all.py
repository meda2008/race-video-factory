# -*- coding: utf-8 -*-
"""全量重渲染（带配音 + 覆盖原编号 + 逐题材清理帧）。

用法:
  python rerender_all.py [--only k1,k2] [--skip k1] [--limit N]

要点：
1. 从 data/slug2no.json 读「题材 -> 原编号」，通过 --topic-no 传给 run.py，
   让 deliver.py 覆盖原编号而不是递增到 069+。
2. 未登记的题材按空号 033/047/050/065 依次分配（保持 001-068 连续）。
3. 每个题材渲染完成后立即删除 out/frames_topic_<slug>，避免 C 盘被中间帧吃满。
"""
import glob, json, os, re, shutil, subprocess, sys, time, datetime

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = 'C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe'
RUN = 'C:/Users/medam/.workbuddy/skills/finance-ranking-video/scripts/run.py'

S2N_PATH = os.path.join(WS, 'data', 'slug2no.json')
FREE_SLOTS = [33, 47, 50, 65]


def load_no_map():
    m = {}
    if os.path.exists(S2N_PATH):
        m = {k: int(v) for k, v in json.load(open(S2N_PATH, encoding='utf-8')).items()}
    return m


def collect_topics():
    """扫全部 topics_registry_*.json，返回 [(registry, key)]，去重。"""
    seen, out = set(), []
    for reg in sorted(glob.glob(os.path.join(WS, 'topics_registry_*.json'))):
        try:
            d = json.load(open(reg, encoding='utf-8'))
        except Exception:
            continue
        for t in d.get('topics', []):
            key = t.get('key') or t.get('slug')
            if not key or key in seen:
                continue
            seen.add(key)
            out.append((reg, key))
    return out


def kill_strays():
    subprocess.run('taskkill /F /IM chrome.exe /T', shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run('taskkill /F /IM ffmpeg.exe /T', shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def free_gb(path='C:/'):
    try:
        t, u, f = shutil.disk_usage(path)
        return f / 1024 ** 3
    except Exception:
        return -1


def clean_frames(slug):
    if os.environ.get('SKIP_CLEAN'):
        return
    d = os.path.join(os.environ.get('FRAMES_ROOT') or os.path.join(WS, 'out'),
                     'frames_topic_' + slug)
    if os.path.isdir(d):
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def main():
    only = skip = set()
    limit = None
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == '--only' and i + 1 < len(argv):
            only = set(x.strip() for x in argv[i + 1].split(',') if x.strip())
        elif a == '--skip' and i + 1 < len(argv):
            skip = set(x.strip() for x in argv[i + 1].split(',') if x.strip())
        elif a == '--limit' and i + 1 < len(argv):
            limit = int(argv[i + 1])

    no_map = load_no_map()
    used = set(no_map.values())
    free_iter = (n for n in FREE_SLOTS if n not in used)

    jobs = []
    for reg, key in collect_topics():
        if only and key not in only:
            continue
        if key in skip:
            continue
        n = no_map.get(key)
        if not n:
            try:
                n = next(free_iter)
            except StopIteration:
                n = None
        jobs.append((key, reg, n))
    if limit:
        jobs = jobs[:limit]

    print('待渲染 %d 个题材 | C盘剩余 %.1f GB' % (len(jobs), free_gb()), flush=True)
    ok, fail = [], []
    t0 = time.time()
    for i, (key, reg, n) in enumerate(jobs, 1):
        print('\n[%d/%d] %s  no=%s  (%.1fGB)  %s' % (
            i, len(jobs), key, n, free_gb(), datetime.datetime.now().strftime('%H:%M:%S')),
            flush=True)
        cmd = [PY, RUN, 'topic_config', '--registry', reg, '--key', key,
               '--workspace', WS]
        if n:
            cmd += ['--topic-no', str(n)]
        log = os.path.join(WS, 'logs', 'rr_%s.log' % key)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, 'w', encoding='utf-8', errors='replace') as lf:
            p = subprocess.run(cmd, cwd=WS, stdout=lf, stderr=subprocess.STDOUT)
        if p.returncode == 0:
            ok.append(key)
            print('   OK', flush=True)
        else:
            fail.append(key)
            print('   FAIL (exit=%d) -> %s' % (p.returncode, log), flush=True)
            with open(log, encoding='utf-8', errors='replace') as lf:
                tail = lf.read()[-800:]
            print('   ' + tail.replace('\n', '\n   ')[-800:], flush=True)
        clean_frames(key)
        if i % 5 == 0:
            kill_strays()
    print('\n===== 完成：成功 %d / 失败 %d | 耗时 %.1f 分钟 | C盘剩余 %.1f GB' % (
        len(ok), len(fail), (time.time() - t0) / 60, free_gb()))
    if fail:
        print('失败题材:', ', '.join(fail))


if __name__ == '__main__':
    main()
