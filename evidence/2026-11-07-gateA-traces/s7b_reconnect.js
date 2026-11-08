// S7b — connection loss and reconnect, driven from the UI.
//
// Holds the joystick, marks DRIVING in the log so the operator script can cut rosbridge mid-motion,
// keeps holding through the outage (the operator does not let go), and reports what the UI and the
// robot do when the link comes back. Whether motion resumes while the stick is still held is the
// question; this script records the answer, it does not assume one.
const fs = require('fs');
const { launch, shot } = require('./harness');

const LOG = '/Users/macuser/openamr-test/evidence/s7b_reconnect.log';
const say = (m) => { const l = `${new Date().toISOString()} ${m}`; console.log(l); fs.appendFileSync(LOG, l + '\n'); };

const state = () => {
  const t = document.body.innerText;
  const conn = (t.match(/(disconnect|reconnect|offline|connected|No connection|rosbridge)[\s\S]{0,70}/i) || [''])[0].replace(/\s+/g, ' ').trim();
  const lin = (t.match(/LINEAR VELOCITY[\s\S]{0,32}/) || [''])[0].replace(/\s+/g, ' ').trim();
  return { conn, lin };
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
    const ev = (type, y, buttons) => new PointerEvent(type, {
      bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: y,
      pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons, button: 0,
      width: 1, height: 1, pressure: 0.5,
    });
    b.dispatchEvent(ev('pointerdown', cy, 1));
    b.dispatchEvent(ev('pointermove', cy - d, 1));
    window.__joy = b; window.__c = [cx, cy];
    return 'down';
  }, dy);
}

async function joyHold(page, dy) {
  return page.evaluate((d) => {
    const b = window.__joy; if (!b) return 'gone';
    const [cx, cy] = window.__c;
    for (let i = 0; i < 3; i++) {
      b.dispatchEvent(new PointerEvent('pointermove', {
        bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: cy - d,
        pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 1, button: -1,
        width: 1, height: 1, pressure: 0.5,
      }));
    }
    return 'held';
  }, dy);
}

async function joyUp(page) {
  return page.evaluate(() => {
    const b = window.__joy; if (!b) return 'gone';
    const [cx, cy] = window.__c;
    b.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: cy,
      pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0, button: 0,
      width: 1, height: 1,
    }));
    return 'up';
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
    await new Promise((r) => setTimeout(r, 6000));
    say('precondition: ' + JSON.stringify(await page.evaluate(state)));

    say('start drive: ' + (await joyDown(page, 22)));
    for (let i = 0; i < 5; i++) { await new Promise((r) => setTimeout(r, 700)); await joyHold(page, 22 + i); }
    say('DRIVING ' + JSON.stringify(await page.evaluate(state)));
    await shot(page, 'S7b-01-driving');

    // keep holding through the outage — 30 s covers the cut, the wait and the reconnect
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      await joyHold(page, 22 + (i % 3));
      if (i === 8) {
        say('during outage: ' + JSON.stringify(await page.evaluate(state)));
        await shot(page, 'S7b-02-outage');
      }
      if (i === 22) {
        say('after reconnect attempt: ' + JSON.stringify(await page.evaluate(state)));
        await shot(page, 'S7b-03-after-reconnect');
      }
    }
    say('end of hold: ' + JSON.stringify(await page.evaluate(state)));
    say('release: ' + (await joyUp(page)));
    await new Promise((r) => setTimeout(r, 3000));
    await shot(page, 'S7b-04-released');
    say('final: ' + JSON.stringify(await page.evaluate(state)));
  } catch (e) {
    say('ERROR ' + e.message);
  } finally {
    await browser.close();
  }
})();
