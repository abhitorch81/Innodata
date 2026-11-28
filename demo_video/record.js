const { chromium } = require('playwright-core');
const fs = require('fs');
const dur = JSON.parse(fs.readFileSync('durations.json'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const exe = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1255/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
  const browser = await chromium.launch({ executablePath: exe, headless: false, args: ['--use-gl=angle', '--window-size=1280,760'] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage(); const t0 = Date.now();
  fs.rmSync('frames',{recursive:true,force:true}); fs.mkdirSync('frames'); const frames=[]; let n=0;
  const cdp = await ctx.newCDPSession(page);
  cdp.on('Page.screencastFrame', async (f) => { const name=`frames/f${String(n++).padStart(6,'0')}.jpg`; fs.writeFileSync(name, Buffer.from(f.data,'base64')); frames.push([name, f.metadata.timestamp]); cdp.send('Page.screencastFrameAck',{sessionId:f.sessionId}).catch(()=>{}); });
  await cdp.send('Page.startScreencast',{format:'jpeg',quality:85,maxWidth:1280,maxHeight:720,everyNthFrame:1});
  page.on('pageerror', (e) => console.log('PAGEERR', e.message));
  await page.goto('http://localhost:8765/'); await sleep(3500);
  const ev = (f) => page.evaluate(f);
  const waitGrade = async () => { await sleep(800); for (let i = 0; i < 60; i++) { const t = await ev(() => document.querySelector('#gres')?.innerText || ''); if (t && !t.startsWith('running')) return; await sleep(500); } };
  const scenes = [
    async () => { await sleep(1000); await ev(() => TaskFactoryApp.flyTo('atlas', 4)); },
    async () => { await ev(() => TaskFactoryApp.flyTo('atlas', 6)); await sleep(9000); await ev(() => { const c = TaskFactoryApp.camera; TaskFactoryApp.controls.autoRotate = true; TaskFactoryApp.controls.autoRotateSpeed = 3; }); },
    async () => { await ev(() => { TaskFactoryApp.controls.autoRotate = false; TaskFactoryApp.selectTask('click/duration-01', { fly: true }); }); },
    async () => { await ev(() => { TaskFactoryApp.flyTo('pipeline', 1); document.querySelector('#b-tour').click(); }); },
    async () => { await ev(() => { document.querySelector('[data-tab=grader]').click(); document.querySelector('[data-c=reference]').click(); }); await waitGrade(); },
    async () => { await ev(() => { document.querySelector('#abl').selectedIndex = 1; document.querySelector('[data-c=ablate]').click(); }); await waitGrade(); },
    async () => { await ev(() => document.querySelector('[data-c=tamper]').click()); await waitGrade(); },
    async () => { await ev(() => { TaskFactoryApp.selectTask('click/relations-03', { fly: false }); TaskFactoryApp.flyTo('variation', 3); }); await sleep(2500); await ev(() => { TaskFactoryApp.controls.autoRotate = true; TaskFactoryApp.controls.autoRotateSpeed = 4; }); },
    async () => { await ev(() => { TaskFactoryApp.controls.autoRotate = false; document.querySelector('[data-tab=lab]').click(); TaskFactoryApp.flyTo('atlas', 3); }); await sleep(8000); await ev(() => document.querySelector('[data-tab=play]').click()); await ev(() => document.querySelectorAll('#tab-play .ix')[3].click()); },
  ];
  const starts = [];
  for (let i = 0; i < scenes.length; i++) {
    starts.push((Date.now() - t0) / 1000); console.log('scene', i, starts[i]);
    await Promise.all([scenes[i](), sleep(dur[i] * 1000 + 700)]);
  }
  await sleep(1500); await cdp.send('Page.stopScreencast'); fs.writeFileSync('starts.json', JSON.stringify(starts)); fs.writeFileSync('frames.json', JSON.stringify(frames));
  await ctx.close(); await browser.close();
})();
