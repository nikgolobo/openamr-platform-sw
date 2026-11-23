// Does the UI recover from a rosbridge outage WITHOUT a page reload?
const { launch } = require('/Users/macuser/openamr-test/browser/harness');
const { execFileSync } = require('child_process');
const KEY = '/Users/macuser/Documents/Codex/2026-09-28/re/work/lima-home/_config/user';
const HOST = 'macuser@192.168.64.2';
const remote = (c) => { try { return execFileSync('ssh', ['-i', KEY, '-o','BatchMode=yes','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null', HOST, c], {encoding:'utf8', timeout:30000}); } catch(e){ return 'ERR'; } };
const read = (page) => page.evaluate(() => {
  const txt = (e) => (e.textContent || '').replace(/\s+/g,' ').trim();
  const b = document.querySelector('[data-testid="manual-drive-disabled"]');
  const console_ = [...document.querySelectorAll('div,span')].map(txt).find(t => /Robot (online|offline)/i.test(t)) || null;
  return { blocked: b ? txt(b).slice(0,60) : null, console: console_ };
});
(async () => {
  const { browser, page } = await launch();
  await page.goto('http://192.168.64.2:5050/', { waitUntil: 'networkidle2', timeout: 60000 });
  await new Promise(r => setTimeout(r, 9000));
  console.log('before kill:', JSON.stringify(await read(page)));
  remote('pkill -f rosbridge_websocket');
  await new Promise(r => setTimeout(r, 6000));
  console.log('during outage:', JSON.stringify(await read(page)));
  remote('nohup bash ~/rb.sh > /tmp/rb2.log 2>&1 & sleep 6');
  for (let i = 1; i <= 6; i += 1) {
    await new Promise(r => setTimeout(r, 5000));
    console.log(`t+${i*5}s after rosbridge back:`, JSON.stringify(await read(page)));
  }
  await browser.close();
})().catch(e => { console.error('FAILED', e.message); process.exit(1); });
