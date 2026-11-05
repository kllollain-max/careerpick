const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const project = process.argv[2];
  assert(['careerpick', 'supportpick'].includes(project));
  const root = path.resolve('dist');
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      const prefix = '/' + project + '/';
      if (!url.pathname.startsWith(prefix)) { res.writeHead(404).end(); return; }
      let relative = decodeURIComponent(url.pathname.slice(prefix.length));
      if (!relative || relative.endsWith('/')) relative += 'index.html';
      const filename = path.resolve(root, relative);
      if (!filename.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
      const data = await fs.readFile(filename);
      const ext = path.extname(filename);
      const mime = {'.html':'text/html; charset=utf-8', '.css':'text/css', '.js':'application/javascript', '.png':'image/png', '.svg':'image/svg+xml'};
      res.writeHead(200, {'Content-Type':mime[ext] || 'application/octet-stream'}).end(data);
    } catch { res.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({headless:true});
  const results = [];
  try {
    const pages = project === 'careerpick' ? ['guides/after-application-checklist.html', 'privacy.html'] : ['benefits/149200000026/', 'privacy.html'];
    await fs.mkdir('mobile-evidence', {recursive:true});
    for (const width of [320,390,1440]) {
      const context = await browser.newContext({viewport:{width,height:900},serviceWorkers:'block'});
      await context.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
      for (const entry of pages) {
        const page = await context.newPage();
        const response = await page.goto(origin + '/' + project + '/' + entry, {waitUntil:'networkidle'});
        assert.equal(response.status(),200);
        await page.locator('h1').waitFor({state:'visible'});
        if (entry.includes('after-application')) {
          assert.equal(await page.locator('#deadline-plan').count(),1);
          await page.locator('summary').first().click();
          assert(await page.locator('details').first().getAttribute('open') !== null);
        }
        if (entry.includes('149200000026')) {
          assert(await page.getByText('카드 발급 전에 훈련과정을 어떻게 비교해 두면 좋을까요?', {exact:true}).count() > 0);
        }
        const dimensions = await page.evaluate(() => ({width:innerWidth, content:document.documentElement.scrollWidth}));
        assert(dimensions.content <= dimensions.width + 1, JSON.stringify({entry,...dimensions}));
        await page.screenshot({path:'mobile-evidence/' + width + '-' + entry.replace(/[^a-z0-9]/gi,'_') + '.png',fullPage:true});
        results.push({entry,width,http:200,overflow:0});
        await page.close();
      }
      await context.close();
    }
    await fs.writeFile('mobile-evidence/results.json',JSON.stringify({project,environment:'Linux Chromium; viewport emulation, not real Android',results},null,2));
    console.log(JSON.stringify({passed:results.length,failed:0}));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error);process.exitCode=1;});
