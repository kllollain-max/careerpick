/* Verify the collected candidate in disposable browser storage. No live writes. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const root = process.env.CLEANEYE_PREVIEW_ROOT || process.cwd();
const base = process.env.CP_TEST_BASE || 'http://127.0.0.1:8000/careerpick/';
const output = 'cleaneye-browser-validation';
const read = name => JSON.parse(fs.readFileSync(path.join(root, name), 'utf8'));
const feed = read('cleaneye.json');
const home = require(path.join(root, 'homepage-ux.js'));
assert.equal(feed.collectionStatus, 'verified', 'A verified API candidate is required');
assert(feed.posts.length > 0, 'A nonempty API candidate is required');
const now = new Date();
const today = new Date(+now + 9 * 3600000).toISOString().slice(0, 10);
const visible = p => home.deadline(p, now)?.cls !== 'closed';
const sample = feed.posts.find(p => p.due && p.due.slice(0, 10) >= today && visible(p)) || feed.posts.find(visible) || feed.posts[0];
const expectedURL = new URL(sample.url).href;
const previous = read('alio.json').posts[0];
assert(previous && sample.id !== previous.id);
const oldApplication = {st:'plan', ck:[], exam:'', itv:'', memo:'기존 지원 기록 보존 확인', title:previous.title, org:previous.org, url:previous.url, due:previous.due, upd:1};

(async () => {
  const options = {headless:true, args:['--no-sandbox']};
  if (process.env.CHROME_PATH) options.executablePath = process.env.CHROME_PATH;
  const browser = await chromium.launch(options);
  const report = [];
  fs.mkdirSync(output, {recursive:true});
  try {
    for (const width of [320, 390, 1440]) {
      const context = await browser.newContext({viewport:{width, height:900}, timezoneId:'Asia/Seoul', serviceWorkers:'block'});
      await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
      await context.addInitScript(({id, application}) => {
        if (sessionStorage.getItem('cpCleaneyeSeeded')) return;
        localStorage.setItem('saved', JSON.stringify([id]));
        localStorage.setItem('apps', JSON.stringify({[id]:application}));
        sessionStorage.setItem('cpCleaneyeSeeded', '1');
      }, {id:previous.id, application:oldApplication});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base + '?q=' + encodeURIComponent(sample.title), {waitUntil:'networkidle'});
      if (!visible(sample)) {
        const closed = page.locator('[data-status="closed"]');
        if (!await closed.isVisible()) await page.locator('#toggle').click();
        await closed.click();
      }
      await page.locator('#list [data-open="' + sample.id + '"]').first().waitFor();
      assert((await page.locator('#list').innerText()).includes('클린아이 잡플러스'));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({path:path.join(output, 'list-' + width + '.png'), fullPage:true});
      await page.locator('#list [data-save="' + sample.id + '"]').first().click();
      await page.reload({waitUntil:'networkidle'});
      await page.getByRole('button', {name:'저장 공고', exact:true}).click();
      await page.locator('[data-save="' + sample.id + '"][aria-pressed="true"]').first().waitFor();
      const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('saved')));
      assert(saved.includes(previous.id) && saved.includes(sample.id));
      await page.locator('#list [data-open="' + sample.id + '"]').first().click();
      await page.locator('#jvBody h1').waitFor();
      assert.equal((await page.locator('#jvBody h1').innerText()).trim(), sample.title.trim());
      const detail = await page.locator('#jvBody').innerText();
      assert(detail.includes('클린아이 잡플러스'));
      const links = await page.locator('#jvBody a[href]').evaluateAll(nodes => nodes.map(node => node.href));
      assert(links.includes(expectedURL), 'Detail must link to the exact official notice');
      for (const employment of sample.emp || []) assert(detail.includes(employment));
      await page.screenshot({path:path.join(output, 'detail-' + width + '.png'), fullPage:true});
      await page.reload({waitUntil:'networkidle'});
      await page.locator('#jvBody h1').waitFor();
      assert.equal((await page.locator('#jvBody h1').innerText()).trim(), sample.title.trim());
      const applicationButton = page.locator('#jvBody').getByRole('button', {name:'📋 지원기록', exact:true});
      assert.equal(await applicationButton.getAttribute('data-track'), sample.id);
      await applicationButton.click();
      await page.locator('#tMemo').fill('클린아이 지원 기록 검증');
      await page.locator('#tSave').click();
      await page.reload({waitUntil:'networkidle'});
      await page.locator('#jvBody h1').waitFor();
      const applications = await page.evaluate(() => JSON.parse(localStorage.getItem('apps')));
      assert.deepEqual(applications[previous.id], oldApplication);
      assert.equal(applications[sample.id].memo, '클린아이 지원 기록 검증');
      assert.equal(applications[sample.id].title, sample.title);
      assert.equal(applications[sample.id].url, expectedURL);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.deepEqual(errors, []);
      report.push({width, notice:sample.id, sourceBadge:true, officialLink:true, search:true, savedAfterReload:true, detailDirectReload:true, applicationAfterReload:true, previousSavedAndApplicationPreserved:true, horizontalOverflow:false, pageErrors:0});
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });

