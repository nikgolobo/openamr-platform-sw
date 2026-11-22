// Fault handling: the robot is being driven from the UI, then rosbridge dies mid-command.
// What must NOT happen: the UI keeps publishing, or the command resumes on reconnect.
const { launch, shot } = require('./harness');
const { execFileSync } = require('child_process');

const KEY = '/Users/macuser/Documents/Codex/2026-09-28/re/work/lima-home/_config/user';
const HOST = 'macuser@192.168.64.2';
const t0 = Date.now();
const log = (...a) => console.log(`${new Date().toISOString()} [+${Date.now() - t0}ms] ${a.join(' ')}`);

const remote = (cmd) => {
  try {
    return execFileSync('ssh', ['-i', KEY, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no',
      '-o', 'UserKnownHostsFile=/dev/null', HOST, cmd], { encoding: 'utf8', timeout: 30000 });
  } catch (e) { return `ERR ${e.message}`; }
};

const click = (page, src) => page.evaluate((s) => {
  const rx = new RegExp(s, 'i');
  const t = (e) => (e.textContent || '').replace(/\s+/g, ' ').trim();
  const el = [...document.querySelectorAll('button,[role=button]')]
    .filter((b) => b.offsetParent !== null && rx.test(t(b)))[0];
  if (!el) return null;
  el.click();
  return t(el).slice(0, 40);
}, src.source);

(async () => {
  const { browser, page } = await launch();
  await page.goto('http://192.168.64.2:5050/', { waitUntil: 'networkidle2', timeout: 60000 });
  await new Promise((r) => setTimeout(r, 9000));

  log('overlay:', await click(page, /^(skip|get started)$/i));
  await new Promise((r) => setTimeout(r, 1200));
  if (await click(page, /^resume$/i)) {
    await new Promise((r) => setTimeout(r, 600));
    log('confirm:', await click(page, /^confirm resume$/i));
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

  await page.mouse.move(box.x, box.y);
  await page.mouse.down();
  await page.mouse.move(box.x, box.y - 40, { steps: 4 });
  log('holding forward');

  const mover = (async () => {
    for (let i = 0; i < 80; i += 1) {
      await page.mouse.move(box.x, box.y - 40);
      await new Promise((r) => setTimeout(r, 120));
    }
  })();

  await new Promise((r) => setTimeout(r, 3000));
  log('killing rosbridge NOW, while the stick is held');
  log(remote('pkill -f rosbridge_websocket; echo killed').trim());

  // Keep holding through the outage: a UI that caches the last command will keep publishing.
  await new Promise((r) => setTimeout(r, 5000));
  const during = await page.evaluate(() => {
    const b = document.querySelector('[data-testid="manual-drive-disabled"]');
    const conn = [...document.querySelectorAll('*')]
      .map((e) => (e.textContent || '').trim())
      .find((t) => /disconnected|reconnect|connection/i.test(t) && t.length < 60);
    return { blocked: b ? b.textContent.trim().slice(0, 60) : null, connHint: conn || null };
  });
  log('during outage:', JSON.stringify(during));
  log('shot:', await shot(page, 'fault-rosbridge-down'));

  await page.mouse.up();
  await mover;
  log('stick released during/after outage');

  // Bring rosbridge back and see whether the released stick produces anything on reconnect.
  log('restarting rosbridge');
  remote('cd ~/openamrobot-ui && (nohup ros2 launch openamr_ui_bringup ui.launch.py start_battery_monitor:=true > /tmp/ui_restart.log 2>&1 &) ; sleep 1; echo restarted');
  await new Promise((r) => setTimeout(r, 20000));

  const after = await page.evaluate(() => {
    const b = document.querySelector('[data-testid="manual-drive-disabled"]');
    return { blocked: b ? b.textContent.trim().slice(0, 60) : null };
  });
  log('after reconnect:', JSON.stringify(after));
  log('shot:', await shot(page, 'fault-after-reconnect'));
  await browser.close();
})().catch((e) => { console.error('FAILED:', e.message); process.exit(1); });
