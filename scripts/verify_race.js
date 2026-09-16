const { chromium } = require('playwright');
const path = require('path');

// 渲染前自检：采样多个时间点，检查排名/数值/NaN，确保 race.html 正确。
const WS = process.env.WORKSPACE || (process.argv[2] ? path.resolve(process.argv[2]) : process.cwd());
const HTML = path.join(WS, 'out', 'race.html');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--force-color-profile=srgb', '--hide-scrollbars', '--disable-dev-shm-usage']
  });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1624 }, deviceScaleFactor: 1 });
  const errs = [];
  page.on('pageerror', e => errs.push('PAGEERR ' + e));
  page.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text); });
  await page.goto('file://' + HTML + '?t=' + Date.now());
  const TOTAL = await page.evaluate('window.TOTAL');
  const FPS = await page.evaluate('window.FPS');
  console.log('TOTAL=', TOTAL, 'FPS=', FPS);

  const INTRO = 0.7, SPAN = TOTAL - INTRO - 1.5;
  const pts = [0, INTRO, INTRO + SPAN*0.2, INTRO + SPAN*0.4, INTRO + SPAN*0.6, INTRO + SPAN*0.8, TOTAL];
  for (const el of pts) {
    const info = await page.evaluate((el) => {
      window.renderAt(el);
      const rows = [...document.querySelectorAll('.row')];
      const sorted = rows.map(r => ({
        n: r.querySelector('.name').textContent,
        left: parseFloat(r.querySelector('.bar').style.left),
        w: parseFloat(r.querySelector('.bar').style.width),
        v: r.querySelector('.val').textContent,
        t: parseFloat(r.style.top)
      })).sort((a,b)=>a.t-b.t);
      return {
        year: document.getElementById('yearNum').textContent,
        n: rows.length,
        lead: sorted[0], last: sorted[sorted.length-1],
        anyNaN: rows.some(r => isNaN(parseFloat(r.querySelector('.bar').style.width)) || isNaN(parseFloat(r.style.top)))
      };
    }, el);
    console.log(`el=${el.toFixed(2)} year=${info.year} n=${info.n} NaN=${info.anyNaN} | LEAD=${info.lead.n} ${info.lead.v} (L=${info.lead.left.toFixed(0)} W=${info.lead.w.toFixed(0)}) | LAST=${info.last.n} ${info.last.v}`);
  }
  console.log('ERRORS:', errs.length ? errs : 'none');
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
