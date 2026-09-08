const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const WS = process.env.WORKSPACE || (process.argv[2] ? path.resolve(process.argv[2]) : process.cwd());
const HTML = path.join(WS, 'out', 'race.html');
const FRAMES = process.env.FRAMES_DIR ? process.env.FRAMES_DIR : path.join(WS, 'out', 'frames');
const POSTER = path.join(WS, 'out', 'race_poster.png');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const LAUNCH_ARGS = ['--no-sandbox', '--disable-gpu', '--force-color-profile=srgb',
  '--hide-scrollbars', '--disable-dev-shm-usage', '--disable-software-rasterizer', '--no-zygote'];

function killBrowser(browser) {
  try { const cp = browser && browser.process(); if (cp && !cp.killed) cp.kill('SIGKILL'); } catch (e) { /* ignore */ }
}

async function launchPage() {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: LAUNCH_ARGS });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1624 }, deviceScaleFactor: 1 });
  // cache-buster：Playwright 对 file:// 有缓存，改 HTML 后必须加 ?t= 强制刷新
  await page.goto('file://' + HTML + '?t=' + Date.now(), { waitUntil: 'load' });
  return { browser, page };
}

(async () => {
  // 旧版会在启动时 unlinkSync 清空 FRAMES 目录（旧帧）。但逐个删 2272 帧
  // 会撞 sandbox 50/turn 阈值，触发 SAFE_DELETE_BULK_REJECTED 并整体失败。
  // 修复：当 FRAMES_DIR 通过环境变量按 slug 划分时（per-topic 目录 frames_topic_<slug>），
  // 新跑会写入新目录，不需要清理；若用户复用同一目录（FRAMES_DIR 未设、回退到
  // 默认 out/frames），仍走旧的逐文件清理以避免爆盘。生产流水线始终传 FRAMES_DIR。
  if (!process.env.FRAMES_DIR) {
    if (fs.existsSync(FRAMES)) {
      for (const fn of fs.readdirSync(FRAMES)) {
        try { fs.unlinkSync(path.join(FRAMES, fn)); } catch (e) { /* ignore */ }
      }
    } else {
      fs.mkdirSync(FRAMES, { recursive: true });
    }
  } else if (!fs.existsSync(FRAMES)) {
    fs.mkdirSync(FRAMES, { recursive: true });
  }

  let browser, page;
  try {
    ({ browser, page } = await launchPage());
    const total = await page.evaluate('window.TOTAL');
    const fps = await page.evaluate('window.FPS');
    const n = Math.round(total * fps);
    console.log(`TOTAL=${total} FPS=${fps} FRAMES=${n}`);

    for (let f = 0; f <= n; f++) {
      const el = f / fps;
      try {
        await page.evaluate(`window.renderAt(${el.toFixed(4)})`);
        await page.screenshot({ path: path.join(FRAMES, `f${String(f).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 86 });
      } catch (e) {
        // 长渲染偶发：页面/浏览器崩溃或截图超时。重启浏览器并从当前帧重试一次，避免整段失败。
        console.log(`  !! frame ${f} 失败(${String(e).slice(0, 60)}), 重启浏览器重试...`);
        killBrowser(browser);
        await new Promise(r => setTimeout(r, 800));
        ({ browser, page } = await launchPage());
        await page.evaluate(`window.renderAt(${el.toFixed(4)})`);
        await page.screenshot({ path: path.join(FRAMES, `f${String(f).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 86 });
      }
      if (f % 60 === 0) console.log(`  frame ${f}/${n}`);
    }
    // 海报：末态
    console.log('  poster evaluate...');
    await page.evaluate(`window.renderAt(${total.toFixed(4)})`);
    console.log('  poster screenshot...');
    await page.screenshot({ path: POSTER, type: 'png' });
    console.log('DONE frames ->', FRAMES);
    console.log('REACHED_EXIT');
  }  catch (e) {
    console.error('FATAL', e);
    killBrowser(browser);
    process.exit(1);
  }
  // 末帧已落盘。browser.close() 在长截图后偶发挂起并阻塞 Node 事件循环，且 process.exit 后
  // Chromium 会变成孤儿进程占用资源、拖累后续渲染启动。改为直接 SIGKILL 浏览器进程（瞬时、
  // 无挂起），再由 OS 回收；随后立即 process.exit，父进程 Python 即可继续。
  killBrowser(browser);
  process.exit(0);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
