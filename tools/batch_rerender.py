#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量重渲染全部题材（换新模板：真实logo/主题背景/黄色外框），复用原口播稿。

策略：
- topic_config 类（56 个 slug）：遍历所有 registry 找到对应 key，跑 run.py topic_config。
  run.py 内部会检测 data/topic_<slug>_narration.txt 存在则还原（保留原口播），
  只重新 TTS 合成 + 用新 build_race 模板渲染 + deliver。
- cnworld（10 个产业）：run.py cnworld --topic <产业>
- finance 申万收益榜（031）：run.py finance --fkind 行业 --start-year 2014
- 失败隔离：每支独立 try/timeout，失败记录不影响其他。
"""
import subprocess, os, json, glob, time, sys

WS = r"C:/Users/medam/WorkBuddy/视频测试/batch2_ws"
SKILL = r"C:/Users/medam/.workbuddy/skills/finance-ranking-video/scripts"
PY = r"C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
RUN = os.path.join(SKILL, "run.py")
LOG_DIR = os.path.join(WS, "logs", "batch_rerender")
os.makedirs(LOG_DIR, exist_ok=True)

# ---- topic_config 白名单（56 个 slug，含 A股/胡润；city_pop 两视频合并为1）----
TC = [
    "city_pop", "fx_reserves", "gold_reserves", "milex", "electricity", "etf_scale",
    "ashare_industry_cap", "stock_mcap", "gdp_per_capita", "m2_gdp", "battery_ev",
    "car_sales", "national_pop", "industry_salary", "fortune_revenue", "crypto",
    "gold_oil", "box_office", "university", "marriage_rate", "world_top10_houseprice",
    "cpi", "life_expectancy", "annual_co2", "child_mortality", "oil_production",
    "primary_energy", "nuclear_energy", "low_carbon_pct", "obesity_rate",
    "beer_per_capita", "air_passengers", "patents", "trade_gdp", "cumulative_co2",
    "ashare_profit", "gas_production", "coal_production", "szse_area", "ai_capex",
    "chip_revenue", "co2_per_capita", "nobel", "pharma_revenue", "semiequip_revenue",
    "defense_revenue", "mining_revenue", "brands",
    "hurun_wealth", "ashare_loss", "ashare_dividend", "ashare_cash", "ashare_revenue",
    "ashare_receivable", "ashare_ocf", "ashare_sellexp",
]

# ---- cnworld 10 个产业（对应 skill topics/cn_vs_world/*.json）----
CN = ["光伏", "大飞机", "家电", "新能源汽车", "植树造林", "汽车",
      "盾构机", "稀土", "造船", "高铁"]

# ---- 建 slug -> registry 映射 ----
regs = glob.glob(os.path.join(WS, "topics_registry_*.json")) + [os.path.join(SKILL, "topics_registry.json")]
slug_reg = {}
for f in regs:
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    for t in d.get("topics", []):
        slug_reg.setdefault(t["key"], f)


def run_cmd(args, tag):
    log = os.path.join(LOG_DIR, f"{tag}.log")
    t0 = time.time()
    try:
        with open(log, "w", encoding="utf-8") as lf:
            r = subprocess.run([PY, RUN] + args, cwd=WS, stdout=lf,
                               stderr=subprocess.STDOUT, timeout=1200)
        ok = r.returncode == 0
        print(f"[{'OK ' if ok else 'FAIL'} {tag}] {time.time()-t0:.0f}s -> {log}",
              flush=True)
        return ok
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT {tag}] -> {log}", flush=True)
        return False
    except Exception as e:
        print(f"[ERR {tag}] {e}", flush=True)
        return False


results = {}
print(f"=== 批量重渲染开始 {time.strftime('%H:%M:%S')} ===", flush=True)
print(f"topic_config: {len(TC)} 支, cnworld: {len(CN)} 支, finance: 1 支", flush=True)

# 1) topic_config
n = 0
for slug in TC:
    n += 1
    reg = slug_reg.get(slug)
    if not reg:
        print(f"[SKIP {slug}] 无 registry", flush=True)
        results[slug] = "noslug"
        continue
    print(f"--- ({n}/{len(TC)}) topic_config {slug} [{os.path.basename(reg)}] ---", flush=True)
    results[slug] = run_cmd(["topic_config", "--key", slug, "--registry", reg], f"tc_{slug}")

# 2) cnworld
for tp in CN:
    print(f"--- cnworld {tp} ---", flush=True)
    results[f"cn_{tp}"] = run_cmd(["cnworld", "--topic", tp], f"cn_{tp}")

# 3) finance 申万收益榜 (031)
print(f"--- finance 申万行业 --start-year 2014 ---", flush=True)
results["finance_sw_031"] = run_cmd(["finance", "--fkind", "行业", "--start-year", "2014"],
                                     "finance_sw_031")

fails = {k: v for k, v in results.items() if v != "OK" and v != "noslug"}
ok_cnt = sum(1 for v in results.values() if v == "OK")
print(f"\n=== 批量重渲染结束 {time.strftime('%H:%M:%S')} ===", flush=True)
print(f"成功 {ok_cnt}/{len(results)} 支", flush=True)
if fails:
    print("失败/跳过：")
    for k, v in fails.items():
        print(f"  {k}: {v}")
print("DONE", flush=True)
