const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const WS = process.env.WORKSPACE;
const HTML = path.join(WS, 'out', 'race.html');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
(async () => {
  const b = await chromium.launch({ executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--force-color-profile=srgb', '--hide-scrollbars', '--disable-dev-shm-usage'] });
  const p = await b.newPage({ viewport: { width: 1080, height: 1624 } });
  await p.goto('file://' + HTML + '?t=' + Date.now());
  const total = await p.evaluate('window.TOTAL');
  await p.evaluate(`window.renderAt(${total})`);
  const cn = await p.evaluate(`(()=>{const r=document.querySelector('.cn');return r?{name:r.querySelector('.name').textContent.trim(),bg:r.querySelector('.bar').style.background,left:r.querySelector('.bar').style.left,width:r.querySelector('.bar').style.width}:null;})()`);
  const title = await p.evaluate(`document.getElementById('ttl').textContent`);
  const rows = await p.evaluate(`[...document.querySelectorAll('.row')].map(r=>({n:r.querySelector('.name').textContent.trim(),v:r.querySelector('.val').textContent}))`);
  console.log(JSON.stringify({ total, title, cn, rows }, null, 2));
  await b.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
