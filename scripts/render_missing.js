const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// 只补渲染缺失的帧（用于渲染进程被打断后续渲，避免全量重跑）。
// 用法：node render_missing.js <WS> <fromFrame> <toFrame>
const WS = process.env.WORKSPACE || (process.argv[2] ? path.resolve(process.argv[2]) : process.cwd());
const FROM = parseInt(process.argv[3] || '0', 10);
const TO = parseInt(process.argv[4] || '48', 10);
const HTML = path.join(WS, 'out', 'race.html');
const FRAMES = path.join(WS, 'out', 'frames');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';

(async () => {
  if (!fs.existsSync(FRAMES)) fs.mkdirSync(FRAMES, { recursive: true });
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--force-color-profile=srgb',
           '--hide-scrollbars', '--disable-dev-shm-usage']
  });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1624 }, deviceScaleFactor: 1 });
  await page.goto('file://' + HTML + '?t=' + Date.now());
  const fps = await page.evaluate('window.FPS');
  for (let f = FROM; f <= TO; f++) {
    const el = f / fps;
    await page.evaluate(`window.renderAt(${el.toFixed(4)})`);
    await page.screenshot({ path: path.join(FRAMES, `f${String(f).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 86 });
    if (f % 20 === 0) console.log(`  frame ${f}`);
  }
  await browser.close();
  console.log(`DONE missing frames ${FROM}..${TO}`);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
