const { chromium } = require('playwright');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = process.cwd();
const mime = {'.html':'text/html','.js':'application/javascript','.json':'application/json','.css':'text/css','.png':'image/png','.svg':'image/svg+xml','.webmanifest':'application/manifest+json'};
const server = http.createServer((req,res) => {
  const pathname = decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const file = path.resolve(root,'.'+(pathname === '/' ? '/index.html' : pathname));
  if (!(file === root || file.startsWith(root+path.sep))) {res.writeHead(403);res.end();return;}
  fs.readFile(file,(err,data)=>{
    if(err){res.writeHead(404);res.end('not found');return;}
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});
    res.end(data);
  });
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2});
    const origin = 'http://127.0.0.1:'+server.address().port;
    await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:30000});
    assert.equal(await page.title(),'커리어픽 · 마감순 채용공고 모음');
    await page.locator('#q').waitFor({state:'visible',timeout:10000});
    await page.locator('#tabs').waitFor({state:'attached',timeout:10000});
    await page.waitForFunction(() => document.querySelectorAll('#tabs .tab').length > 0, null, {timeout:30000});
    await page.waitForFunction(() => {
      const summary = document.querySelector('#summary');
      return summary && /검색 결과|글 |새 글|조건|공고/.test(summary.textContent||'');
    },null,{timeout:30000});
    const first = await page.locator('#list > li').count();
    assert.ok(first > 0,'homepage should show cards or an empty-state message');
    const perf = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0];
      const paint = performance.getEntriesByType('paint');
      const fcp = paint.find(p => p.name === 'first-contentful-paint');
      return {domContentLoadedMs:nav ? Math.round(nav.domContentLoadedEventEnd) : null,
        loadEventMs:nav ? Math.round(nav.loadEventEnd) : null,
        fcpMs:fcp ? Math.round(fcp.startTime) : null};
    });
    console.log(JSON.stringify({title:await page.title(),initialListItems:first,summary:(await page.locator('#summary').innerText()).slice(0,140),localBrowserMetrics:perf}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.close());
