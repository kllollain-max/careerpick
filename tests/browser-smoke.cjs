const { chromium } = require('playwright');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(process.env.CP_SITE_ROOT || process.cwd());
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
    const feedDiagnostics = {failed:[],pageErrors:[],feedResponses:[]};
    page.on('requestfailed', req => feedDiagnostics.failed.push({url:req.url(),failure:req.failure()?.errorText}));
    page.on('pageerror', err => feedDiagnostics.pageErrors.push(String(err).slice(0,250)));
    page.on('response', resp => {if(/\\.json(?:\\?|$)/.test(resp.url())) feedDiagnostics.feedResponses.push({url:resp.url(),status:resp.status()});});
    await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:30000});
    assert.equal(await page.title(),'커리어픽 · 마감순 채용공고 모음');
    await page.locator('#q').waitFor({state:'visible',timeout:10000});
    await page.locator('#tabs').waitFor({state:'attached',timeout:10000});
    await page.waitForFunction(() => document.querySelectorAll('#tabs .tab').length > 0, null, {timeout:30000});
    await page.waitForFunction(() => {
      const summary = document.querySelector('#summary');
      return summary && /검색 결과|글 |새 글|조건|공고/.test(summary.textContent||'');
    },null,{timeout:30000});
    if (process.env.CP_REQUIRE_JOB_RESULTS === '1') {
      // Initial 0 is a legitimate loading state on main; wait for feeds to settle.
      await page.waitForFunction(() => {
        const summary = document.querySelector('#summary')?.textContent || '';
        const match = summary.match(/검색 결과\\s*([\\d,]+)건/);
        return match && Number(match[1].replace(/,/g,'')) > 0;
      }, null, {timeout:30000}).catch(err => {
        console.error('Baseline feed diagnostics:',JSON.stringify({root,summary:'no nonzero jobs',...feedDiagnostics}));
        throw err;
      });
    }
    const first = await page.locator('#list > li').count();
    assert.ok(first > 0,'homepage should show cards or an empty-state message');
    // Verify real interactive search, not just initial markup.
    await page.locator('#q').fill('zzzz-careerpick-no-matches-9999');
    await page.waitForFunction(() => /검색 결과\\s*0건|조건에 맞는 글이 없습니다/.test(document.querySelector('#summary')?.textContent || '') || document.querySelector('#list .empty'), null, {timeout:10000});
    assert.ok(await page.locator('#list .empty').count() > 0, 'search should show no-results state');
    await page.locator('#q').fill('');
    await page.waitForFunction(() => document.querySelectorAll('#list > li').length > 1, null, {timeout:10000});
    // Reload must not erase a user's saved job IDs or application records.
    await page.evaluate(() => {
      localStorage.setItem('saved', JSON.stringify(['cp-perf-sentinel-saved']));
      localStorage.setItem('apps', JSON.stringify({'cp-perf-sentinel-application':{st:'plan',org:'CI TEST'}}));
      localStorage.setItem('cp-perf-sentinel-unrelated', 'preserve-me');
    });
    await page.reload({waitUntil:'domcontentloaded',timeout:30000});
    await page.waitForFunction(() => document.querySelectorAll('#tabs .tab').length > 0, null, {timeout:30000});
    const persisted = await page.evaluate(() => ({
      saved: JSON.parse(localStorage.getItem('saved') || '[]'),
      apps: JSON.parse(localStorage.getItem('apps') || '{}'),
      unrelated: localStorage.getItem('cp-perf-sentinel-unrelated')
    }));
    assert.ok(persisted.saved.includes('cp-perf-sentinel-saved'), 'saved job ID must persist');
    assert.equal(persisted.unrelated, 'preserve-me', 'unrelated local storage must persist');
    assert.equal(persisted.apps['cp-perf-sentinel-application']?.st, 'plan', 'application record must persist');
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
