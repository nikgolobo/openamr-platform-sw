// Stop pressed while the robot is actually driving: hold the stick, press Stop with the other hand,
// keep holding, release. Records the operator-visible order of events on the browser clock.
const { launch, shot } = require('./harness');

const t0 = Date.now();
const log = (...a) => console.log(`${new Date().toISOString()} [+${Date.now() - t0}ms] ${a.join(' ')}`);

const clickLabel = (page, rxSrc) => page.evaluate((src) => {
  const rx = new RegExp(src, 'i');
  const txt = (e) => (e.textContent || '').replace(/\s+/g, ' ').trim();
  const el = [...document.querySelectorAll('button,[role=button]')]
    .filter((b) => b.offsetParent !== null && rx.test(txt(b)))[0];
  if (!el) return null;
  el.click();
  return txt(el).slice(0, 40);
}, rxSrc.source);

(async () => {
  const { browser, page } = await launch();
  await page.goto('http://192.168.64.2:5050/', { waitUntil: 'networkidle2', timeout: 60000 });
  await new Promise((r) => setTimeout(r, 9000));
  log('dismiss overlay:', await clickLabel(page, /^(skip|get started)$/i));
  await new Promise((r) => setTimeout(r, 1200));

  if (await clickLabel(page, /^resume$/i)) {
    await new Promise((r) => setTimeout(r, 600));
    log('confirm resume:', await clickLabel(page, /^confirm resume$/i));
    await new Promise((r) => setTimeout(r, 2500));
  }

  const box = await page.evaluate(() => {
    const el = [...document.querySelectorAll('div')].find((e) => /h-\[82px\].*w-\[82px\]/.test(e.className || ''));
    if (!el) return null;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  });
  log('stick:', JSON.stringify(box));
  if (!box) { await browser.close(); return; }

  // Hold the stick north.
  await page.mouse.move(box.x, box.y);
  await page.mouse.down();
  await page.mouse.move(box.x, box.y - 40, { steps: 4 });
  log('holding forward');

  const mover = (async () => {
    for (let i = 0; i < 60; i += 1) {
      await page.mouse.move(box.x, box.y - 40);
      await new Promise((r) => setTimeout(r, 120));
    }
  })();

  await new Promise((r) => setTimeout(r, 1600));
  log('pressing Stop while holding, at', Date.now() - t0, 'ms');
  const pressed = await clickLabel(page, /^stop \(software\)$/);
  log('stop pressed:', pressed);
  await new Promise((r) => setTimeout(r, 2500));
  log('shot:', await shot(page, 'stop-mid-drive'));

  await page.mouse.up();
  await mover;
  log('released stick at', Date.now() - t0, 'ms');

  const s = await page.evaluate(() => {
    const b = document.querySelector('[data-testid="manual-drive-disabled"]');
    return { blocked: b ? (b.textContent || '').trim().slice(0, 60) : null };
  });
  log('after stop+release:', JSON.stringify(s));
  await browser.close();
})().catch((e) => { console.error('FAILED:', e.message); process.exit(1); });
