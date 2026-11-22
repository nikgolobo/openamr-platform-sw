// Verify the operator path on a live UI: Resume, drive, Stop, locked-drive refusal, Resume again.
// Everything is timestamped on the browser clock; the ROS-side hops are captured in parallel by
// ui_path_verify.py on the guest. Screenshots at each step.
const fs = require('fs');
const { launch, shot } = require('./harness');

const OUT = 'ui50pair';
const t0 = Date.now();
const log = (...a) => console.log(`${new Date().toISOString()} ${a.join(' ')}`);
const ms = () => Date.now() - t0;

const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

async function state(page) {
  return page.evaluate(() => {
    const txt = (e) => (e.textContent || '').replace(/\s+/g, ' ').trim();
    const btns = [...document.querySelectorAll('button,[role=button]')]
      .filter((b) => b.offsetParent !== null)
      .map((b) => ({ text: txt(b).slice(0, 40), disabled: !!b.disabled, y: Math.round(b.getBoundingClientRect().y) }));
    const disabled = document.querySelector('[data-testid="manual-drive-disabled"]');
    return {
      buttons: btns,
      manualDriveBlocked: disabled ? txt(disabled).slice(0, 80) : null,
    };
  });
}

async function clickLabel(page, rx) {
  return page.evaluate((rxSrc) => {
    const rx = new RegExp(rxSrc, 'i');
    const txt = (e) => (e.textContent || '').replace(/\s+/g, ' ').trim();
    const el = [...document.querySelectorAll('button,[role=button]')]
      .filter((b) => b.offsetParent !== null && rx.test(txt(b)))[0];
    if (!el) return null;
    el.click();
    return txt(el).slice(0, 40);
  }, rx.source);
}

async function joystickBox(page) {
  return page.evaluate(() => {
    // The stick base is the 96 px square inside the manual-drive card; its class carries the
    // tailwind size utilities and nothing semantic, so match on those.
    const el = [...document.querySelectorAll('div')]
      .find((e) => /h-\[82px\].*w-\[82px\]/.test(e.className || ''));
    if (!el) return null;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), w: Math.round(r.width) };
  });
}

async function drag(page, box, dy, holdMs) {
  await page.mouse.move(box.x, box.y);
  await page.mouse.down();
  await page.mouse.move(box.x, box.y + dy, { steps: 5 });
  const started = Date.now();
  while (Date.now() - started < holdMs) {
    await page.mouse.move(box.x, box.y + dy);
    await new Promise((r) => setTimeout(r, 120));
  }
  await page.mouse.up();
  return Date.now() - started;
}

(async () => {
  const { browser, page } = await launch();
  await page.goto('http://192.168.64.2:5050/', { waitUntil: 'networkidle2', timeout: 60000 });
  await new Promise((r) => setTimeout(r, 9000));
  log("shot:", await shot(page, "00-loaded"));

  // The first-run wizard renders a fixed full-screen overlay above everything, so every click on a
  // control underneath is swallowed. Dismiss it before touching any control.
  const skipped = await clickLabel(page, /^(skip|get started)$/i);
  if (skipped) {
    log('[0] dismissed overlay via:', skipped);
    await new Promise((r) => setTimeout(r, 1200));
    const still = await page.evaluate(() => {
      const el = document.querySelector('div.fixed.inset-0.z-\\[300\\]');
      return el ? (el.textContent || '').trim().slice(0, 40) : null;
    });
    log('[0] overlay after dismiss:', still);
  }

  let s = await state(page);
  log('[0] buttons:', JSON.stringify(s.buttons.map((b) => b.text)));
  log('[0] manual drive blocked:', s.manualDriveBlocked);

  // 1. If the UI is showing a stop, release it through the Resume control.
  const hasResume = s.buttons.some((b) => /^resume$/i.test(b.text));
  if (hasResume) {
    // The gate can refuse the first release; an operator would press again. Measure how many
    // presses it actually takes and how long the block lasts, because that is the readiness number.
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      const t = Date.now();
      log(`[1] Resume press ${attempt}`);
      await clickLabel(page, /^resume$/i);
      await new Promise((r) => setTimeout(r, 600));
      const confirmed = await clickLabel(page, /^confirm resume$/i);
      log(`[1] confirm dialog button: ${confirmed}`);
      let cleared = false;
      const deadline = Date.now() + 20000;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1000));
        s = await state(page);
        if (!s.manualDriveBlocked) { cleared = true; break; }
      }
      log(`[1] press ${attempt}: cleared=${cleared} after ${Date.now() - t} ms; blocked=${s.manualDriveBlocked}`);
      if (cleared) break;
    }
    log("shot:", await shot(page, "01-after-resume"));
  }

  // 2. Drive with the stick and measure how long it was held.
  const box = await joystickBox(page);
  log('[2] joystick box:', JSON.stringify(box));
  if (box) {
    const held = await drag(page, box, -45, 3000);
    log(`[2] drag released after ${held} ms`);
    await new Promise((r) => setTimeout(r, 1200));
    log("shot:", await shot(page, "02-after-drive"));
  }

  // 3. Stop through the UI.
  const stopTexts = (await state(page)).buttons.filter((b) => /stop/i.test(b.text)).map((b) => b.text);
  log('[3] stop controls present:', JSON.stringify(stopTexts));
  const pressed = await clickLabel(page, /^stop \(software\)$/);
  log('[3] pressed:', pressed, 'at', ms());
  await new Promise((r) => setTimeout(r, 2000));
  s = await state(page);
  log('[3] after Stop: blocked=', s.manualDriveBlocked, 'resumeVisible=', s.buttons.some((b) => /^resume$/i.test(b.text)));
  log("shot:", await shot(page, "03-after-stop"));

  // 4. Try to drive while stopped: the stick must refuse and say why.
  if (box) {
    const held2 = await drag(page, box, -45, 2000);
    log(`[4] drag while stopped released after ${held2} ms`);
    await new Promise((r) => setTimeout(r, 800));
    s = await state(page);
    log('[4] blocked reason:', s.manualDriveBlocked);
    log("shot:", await shot(page, "04-drive-while-stopped"));
  }

  // 5. Resume and confirm no motion starts on its own.
  log('[5] clicking Resume');
  await clickLabel(page, /^resume$/i);
  await new Promise((r) => setTimeout(r, 600));
  log('[5] confirm:', await clickLabel(page, /^confirm resume$/i));
  await new Promise((r) => setTimeout(r, 3000));
  s = await state(page);
  log('[5] after Resume: blocked=', s.manualDriveBlocked);
  log("shot:", await shot(page, "05-resume-2"));
  log('[5] done at', ms(), 'ms');

  await browser.close();
})().catch((e) => {
  console.error('FAILED:', e.message);
  process.exit(1);
});
