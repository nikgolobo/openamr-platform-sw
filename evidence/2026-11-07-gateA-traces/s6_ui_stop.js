// S6 — software Stop while driving, pressed through the real UI control.
//
// Drives with the joystick (synthetic pointer events, so the real mouse stays free), presses
// "Stop (software)" in the MANUAL panel, keeps pushing for the Hold check, then presses Resume and
// checks the old held input does not restart motion. The recorder on the VM supplies the
// authoritative timings; this script supplies what the operator saw and which control was pressed.
const { launch, shot } = require('./harness');

const fs = require('fs');
const LOG = '/Users/macuser/openamr-test/evidence/s6_ui_stop.log';
const events = [];
const say = (...a) => {
  const line = `${new Date().toISOString()} ${a.join(' ')}`;
  events.push(line);
  console.log(line);
  fs.appendFileSync(LOG, line + '\n');
};

const UI = () => {
  const t = document.body.innerText;
  const lin = (t.match(/LINEAR VELOCITY[\s\S]{0,40}/) || [''])[0].replace(/\s+/g, ' ').trim();
  const banner = (t.match(/(software stop|halted|locked|Resume)[\s\S]{0,60}/i) || [''])[0]
    .replace(/\s+/g, ' ').trim();
  const buttons = [...document.querySelectorAll('button')].map((b) => ({
    text: (b.innerText || '').trim(),
    disabled: !!b.disabled,
    rect: (() => { const r = b.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; })(),
  })).filter((b) => /stop|resume|goal|dock/i.test(b.text));
  return { lin, banner, buttons };
};

async function joyDown(page, dy) {
  return page.evaluate((d) => {
    const b = [...document.querySelectorAll('button')].find((el) => {
      const r = el.getBoundingClientRect();
      return Math.abs(r.width - 63) < 6 && Math.abs(r.height - 63) < 6;
    });
    if (!b) return 'no joystick';
    const r = b.getBoundingClientRect();
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    const mk = (type, y, buttons) => new PointerEvent(type, {
      bubbles: true, cancelable: true, composed: true,
      clientX: cx, clientY: y, pointerId: 1, pointerType: 'mouse',
      isPrimary: true, buttons, button: 0, width: 1, height: 1, pressure: 0.5,
    });
    b.dispatchEvent(mk('pointerdown', cy, 1));
    b.dispatchEvent(mk('pointermove', cy - d, 1));
    window.__joy = b; window.__joyCentre = [cx, cy];
    return `joystick down at ${cx.toFixed(0)},${cy.toFixed(0)} -> up ${d}px`;
  }, dy);
}

async function joyHold(page, dy) {
  return page.evaluate((d) => {
    const b = window.__joy;
    if (!b) return 'no joystick';
    const [cx, cy] = window.__joyCentre;
    for (let i = 0; i < 4; i++) {
      b.dispatchEvent(new PointerEvent('pointermove', {
        bubbles: true, cancelable: true, composed: true,
        clientX: cx, clientY: cy - d, pointerId: 1, pointerType: 'mouse',
        isPrimary: true, buttons: 1, button: -1, width: 1, height: 1, pressure: 0.5,
      }));
    }
    return 'held';
  }, dy);
}

async function joyUp(page) {
  return page.evaluate(() => {
    const b = window.__joy;
    if (!b) return 'no joystick';
    const [cx, cy] = window.__joyCentre;
    b.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true, cancelable: true, composed: true,
      clientX: cx, clientY: cy, pointerId: 1, pointerType: 'mouse',
      isPrimary: true, buttons: 0, button: 0, width: 1, height: 1,
    }));
    return 'released';
  });
}

// Press the control by label. STOP_TARGET=manual (default) picks the Manual-panel instance
// (rect.y > 100); STOP_TARGET=statusbar picks the header instance (rect.y < 100). They are two
// different controls that share the label, so each has to be exercised and reported separately.
async function pressStop(page) {
  const target = process.env.STOP_TARGET || 'manual';
  return page.evaluate((want) => {
    const all = [...document.querySelectorAll('button')]
      .filter((b) => /^stop \(software\)$/i.test((b.textContent || '').trim()));
    if (!all.length) return { pressed: false, reason: 'no Stop (software) button in DOM' };
    const withRect = all.map((b) => ({ b, r: b.getBoundingClientRect() }));
    const pick = want === 'statusbar'
      ? withRect.find((x) => x.r.y < 100)
      : withRect.find((x) => x.r.y > 100);
    const chosen = pick || withRect[0];
    chosen.b.click();
    return {
      pressed: true,
      target: want,
      which: chosen.r.y < 100 ? 'status bar' : 'manual panel',
      rect: [Math.round(chosen.r.x), Math.round(chosen.r.y), Math.round(chosen.r.width), Math.round(chosen.r.height)],
      at: Date.now(),
    };
  }, target);
}

async function pressResume(page) {
  return page.evaluate(() => {
    const b = [...document.querySelectorAll('button')]
      .find((el) => /^resume$/i.test((el.textContent || '').trim()));
    if (!b) return { pressed: false };
    const r = b.getBoundingClientRect();
    b.click();
    return { pressed: true, rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)], at: Date.now() };
  });
}

async function confirmDialog(page) {
  await new Promise((r) => setTimeout(r, 1500));
  return page.evaluate(() => {
    // The confirm control is labelled "Confirm resume"; a button labelled "Resume" also exists
    // behind the modal and clicking it does nothing.
    const btn = [...document.querySelectorAll('button')]
      .find((b) => /^confirm resume$/i.test((b.innerText || '').trim()));
    if (!btn) {
      const fallback = [...document.querySelectorAll('button')]
        .find((b) => /^confirm(\s|\s*release|$)/i.test((b.innerText || '').trim()));
      if (!fallback) return 'no confirm button';
      fallback.click();
      return `confirmed via "${fallback.innerText.trim()}" (fallback)`;
    }
    btn.click();
    return `confirmed via "${btn.innerText.trim()}"`;
  });
}

(async () => {
  fs.writeFileSync(LOG, '');
  const { browser, page } = await launch();
  try {
    await page.goto('http://192.168.64.2:5050', { waitUntil: 'domcontentloaded', timeout: 120000 });
    await page.waitForFunction(() => document.body && document.body.innerText.length > 200, { timeout: 120000 });
    await new Promise((r) => setTimeout(r, 12000));
    await page.evaluate(() => {
      const s = [...document.querySelectorAll('button')].find((b) => (b.innerText || '').trim() === 'Skip');
      if (s) s.click();
    });
    await new Promise((r) => setTimeout(r, 8000));

    say('precondition:', JSON.stringify(await page.evaluate(UI)));
    await shot(page, 'S6-01-before');

    say('drive:', await joyDown(page, 22));
    for (let i = 0; i < 5; i++) {
      await new Promise((r) => setTimeout(r, 900));
      await joyHold(page, 22 + i * 2);
    }
    const driving = await page.evaluate(UI);
    say('while driving:', JSON.stringify({ lin: driving.lin }));
    await shot(page, 'S6-02-driving');

    const stop = await pressStop(page);
    say('PRESSED STOP:', JSON.stringify(stop));
    const tPress = Date.now();

    // Hold: keep the same input active and keep pushing for 5 s.
    for (let i = 0; i < 6; i++) {
      await new Promise((r) => setTimeout(r, 850));
      await joyHold(page, 22 + i * 2);
    }
    const held = await page.evaluate(UI);
    say('after 5s of held input while stopped:', JSON.stringify(held));
    await shot(page, 'S6-03-held-after-stop');

    const resume = await pressResume(page);
    say('PRESSED RESUME:', JSON.stringify(resume));
    say('dialog:', await confirmDialog(page));
    await new Promise((r) => setTimeout(r, 2500));
    const afterResume = await page.evaluate(UI);
    say('after Resume, still holding:', JSON.stringify(afterResume));
    await shot(page, 'S6-04-after-resume-still-held');

    // Recovery: release the held input, then press again — only now may it move.
    say('release joystick:', await joyUp(page));
    await new Promise((r) => setTimeout(r, 1500));
    say('re-press joystick:', await joyDown(page, 22));
    for (let i = 0; i < 4; i++) {
      await new Promise((r) => setTimeout(r, 800));
      await joyHold(page, 22 + i * 3);
    }
    const fresh = await page.evaluate(UI);
    say('after neutral + new command:', JSON.stringify(fresh));
    await shot(page, 'S6-05-new-command');
    say('release joystick:', await joyUp(page));

    say('elapsed since press ms:', Date.now() - tPress);
    fs.writeFileSync('/Users/macuser/openamr-test/evidence/s6_ui_stop.json', JSON.stringify(
      { stop, resume, held, afterResume, fresh, driving, pre: 'see log' }, null, 2));
  } catch (e) {
    say('ERROR', e.message);
  } finally {
    await browser.close();
  }
})();
