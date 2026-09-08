# race-video-factory · 数据竞速柱状图视频生产线

把「一份排行榜数据」变成一支**带配音、带内容相关背景、时长可控**的竖屏竞速视频。
从取数到成片全自动，单支约 2~4 分钟。

```
CSV / akshare / 世行 / OWID / 深交所 / 诺奖
        │
        ▼
   adapters 取数 ──► normalize_topic 归一化
        │
        ▼
   文案(xhs/微信) ──► 口播稿按年度定制字数 ──► TTS 配音
        │                                          │
        ▼                                          ▼
   内容相关背景(gpt-image-2) ──► build_race 生成 race.html ◄── 时间轴(变化强度加权)
        │
        ▼
   Playwright 逐帧渲染 ──► ffmpeg 混音(BGM+配音) ──► deliver 归档 D:\AI视频
```

## 30 秒上手

```bash
# 1) 装依赖（Python 3.13 + Node 22 + ffmpeg + Chromium）
pip install -r requirements.txt

# 2) 配密钥（可选：不配则背景占位、配音走免费 edge-tts）
cp .env.example .env      # 填 AZURE_SPEECH_KEY / IMAGE2_API_KEY

# 3) 出一支片
python bin/race one --key szse_area --workspace ./workspace

# 4) 批量出全部
python bin/race all --workspace ./workspace
```

成片落在 `VIDEO_OUT_ROOT/VIDEO_PROJECT_NAME/`（默认 `D:\AI视频\数据竞速\`），
命名为 `NNN_标题.mp4`，同目录还有 `NNN_标题_发布文案.md`（小红书 + 公众号双套）。

## 目录结构

| 路径 | 作用 |
|---|---|
| `bin/race` | 一键入口（`one` / `all` / `list` / `check`） |
| `config/topics_registry.json` | **题材注册表**——新增题材只改这里 |
| `scripts/` | 流水线各阶段脚本 |
| `scripts/adapters/` | 数据源适配器（csv / akshare / wdi / owid / szse / nobel） |
| `tools/` | 质检与运维（徽章英文自检、批量重渲染、补交付…） |
| `docs/` | 架构、新增题材、数据通道、踩坑记录 |

## 三条硬规则

1. **数字不能编造** —— 口播稿只能引用数据摘要里的真实数字，禁止推算插值。
2. **画面不能有英文** —— 徽章用中文简称（沪/粤/藏、美/日/德），单位文案去英文
   （GDP→国内生产总值、ETF→指数基金、Top10→前十）。自检：`tools/check_badge_latin.py`。
3. **时长由年度跨度决定** —— `18 + 年度跨度 × 1.25` 秒，封顶 105 秒（≤2 分钟）。

## 文档

- [docs/01-架构与流水线.md](docs/01-架构与流水线.md) —— 每一步的输入/输出/可调参数
- [docs/02-新增一个题材.md](docs/02-新增一个题材.md) —— 5 分钟加一个新题材
- [docs/03-数据通道.md](docs/03-数据通道.md) —— 六条取数通道的现状与上限
- [docs/04-踩坑记录.md](docs/04-踩坑记录.md) —— 磁盘、删除守卫、TTS 瞬断等
