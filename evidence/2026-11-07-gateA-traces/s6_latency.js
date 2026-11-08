// S6 latency isolation — measure press -> lock on ONE clock, and see what the engage call queues behind.
//
// The earlier numbers (0.313 s manual, 2.425 s status bar) mixed two clocks and two runs. Here the
// browser itself timestamps every rosbridge frame with the Mac's clock: the press, the
// /safety/stop_lock_engage request and its reply, the four CancelGoal calls and their replies, and the
// incoming /safety/stop_lock publish that the UI acts on. No clock offset, no cross-machine maths.
//
// Presses both controls in one session so the comparison is like-for-like.
const fs = require('fs');
const { launch, shot } = require('./harness');

const LOG = '/Users/macuser/openamr-test/evidence/s6_latency.log';
const say = (m) => { const l = `${new Date().toISOString()} ${m}`; console.log(l); fs.appendFileSync(LOG, l + '\n'); };

const frames = [];   // { t, dir, op, id, service, ok, data }

function wire(page) {
  // Must be the TARGET session (page.createCDPSession() does not surface websocket frames), and
  // Network.enable has to happen before the page opens its socket.
  return page.target().createCDPSession().then(async (client) => {
    await client.send('Network.enable');
    const push = (dir) => (ev) => {
      let d;
      try { d = JSON.parse(ev.response.payloadData); } catch (e) { return; }
      frames.push({
        t: Date.now(), dir, op: d.op,
        id: d.id, service: d.service,
        ok: d.result === 'success' ? true : (d.result || undefined),
        data: d.op === 'publish' ? d.topic : undefined,
        value: d.msg && typeof d.msg.data !== 'undefined' ? d.msg.data : undefined,
      });
    };
    client.on('Network.webSocketFrameSent', push('out'));
    client.on('Network.webSocketFrameReceived', push('in'));
    return client;
  });
}

async function pressStop(page, which) {
  return page.evaluate((want) => {
    const all = [...document.querySelectorAll('button')]
      .filter((b) => /^stop \(software\)$/i.test((b.textContent || '').trim()));
    const withRect = all.map((b) => ({ b, r: b.getBoundingClientRect() }));
    const el = want === 'statusbar' ? withRect.find((x) => x.r.y < 100) : withRect.find((x) => x.r.y > 100);
    if (!el) return null;
    el.b.click();
    return { which: want, rect: [Math.round(el.r.x), Math.round(el.r.y)], at: Date.now() };
  }, which);
}

async function pressResume(page) {
  const at = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((el) => /^resume$/i.test((el.textContent || '').trim()));
    if (!b) return null;
    b.click(); return Date.now();
  });
  await new Promise((r) => setTimeout(r, 1200));
  await page.evaluate(() => {
    const c = [...document.querySelectorAll('button')].find((b) => /^confirm resume$/i.test((b.innerText || '').trim()));
    if (c) c.click();
  });
  return at;
}

async function drive(page, seconds) {
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((el) => {
      const r = el.getBoundingClientRect();
      return Math.abs(r.width - 63) < 6 && Math.abs(r.height - 63) < 6;
    });
    if (!b) return;
    const r = b.getBoundingClientRect();
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    const ev = (type, y, buttons) => new PointerEvent(type, {
      bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: y,
      pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons, button: 0, width: 1, height: 1, pressure: 0.5,
    });
    b.dispatchEvent(ev('pointerdown', cy, 1));
    b.dispatchEvent(ev('pointermove', cy - 22, 1));
    window.__joy = b; window.__c = [cx, cy];
  });
  for (let i = 0; i < seconds * 2; i++) {
    await new Promise((r) => setTimeout(r, 400));
    await page.evaluate((d) => {
      const b = window.__joy; if (!b) return;
      const [cx, cy] = window.__c;
      b.dispatchEvent(new PointerEvent('pointermove', {
        bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: cy - d,
        pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 1, button: -1,
        width: 1, height: 1, pressure: 0.5,
      }));
    }, 22 + (i % 3));
  }
}

async function stopDriving(page) {
  await page.evaluate(() => {
    const b = window.__joy; if (!b) return;
    const [cx, cy] = window.__c;
    b.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: cy,
      pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0, button: 0, width: 1, height: 1,
    }));
  });
}

function analyse(press, label) {
  const after = frames.filter((f) => f.t >= press.at - 50 && f.t <= press.at + 6000);
  const engage = after.find((f) => f.op === 'call_service' && /stop_lock_engage/.test(f.service || ''));
  const engageResp = engage && frames.find((f) => f.op === 'service_response' && f.id === engage.id);
  const cancels = after.filter((f) => f.op === 'call_service' && /cancel_goal/.test(f.service || ''));
  const cancelResps = cancels.map((c) => frames.find((f) => f.op === 'service_response' && f.id === c.id));
  const lockMsg = after.find((f) => f.op === 'publish' && f.dir === 'in' && /stop_lock$/.test(f.data || '') && f.value === true);
  const out = {
    label,
    press_at: press.at,
    engage_sent_ms: engage ? engage.t - press.at : null,
    engage_reply_ms: engageResp ? engageResp.t - press.at : null,
    cancel_calls: cancels.map((c) => ({ service: c.service, sent_ms: c.t - press.at })),
    cancel_replies_ms: cancelResps.map((c) => (c ? c.t - press.at : null)),
    lock_msg_ms: lockMsg ? lockMsg.t - press.at : null,
  };
  say(label + ': ' + JSON.stringify(out));
  return out;
}

(async () => {
  fs.writeFileSync(LOG, '');
  const { browser, page } = await launch();
  const results = [];
  try {
    await wire(page);
    await page.goto('http://192.168.64.2:5050', { waitUntil: 'domcontentloaded', timeout: 120000 });
    await page.waitForFunction(() => document.body && document.body.innerText.length > 200, { timeout: 120000 });
    await new Promise((r) => setTimeout(r, 12000));
    await page.evaluate(() => {
      const s = [...document.querySelectorAll('button')].find((b) => (b.innerText || '').trim() === 'Skip');
      if (s) s.click();
    });
    await new Promise((r) => setTimeout(r, 6000));

    // make sure we start unlocked
    const locked = await page.evaluate(() => /Stopped \(software\)/i.test(document.body.innerText));
    say('started locked: ' + locked);
    if (locked) { await pressResume(page); await new Promise((r) => setTimeout(r, 2500)); }

    for (const which of ['manual', 'statusbar']) {
      await drive(page, 3);
      const p = await pressStop(page, which);
      say(`${which} pressed at ${p.at} rect ${p.rect}`);
      await new Promise((r) => setTimeout(r, 3500));  // let the replies land before analysing
      say('frames captured so far: ' + frames.length);
      const res = analyse(p, which + '-press');
      results.push(res);
      await shot(page, `S6L-${which}-stopped`);
      await new Promise((r) => setTimeout(r, 2500));
      await stopDriving(page);
      await pressResume(page);
      await new Promise((r) => setTimeout(r, 3500));
    }

    fs.writeFileSync('/Users/macuser/openamr-test/evidence/s6_latency.json', JSON.stringify(results, null, 2));
    say('done');
  } catch (e) {
    say('ERROR ' + e.message);
  } finally {
    await browser.close();
  }
})();
