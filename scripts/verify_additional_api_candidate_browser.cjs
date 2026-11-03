const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.join(__dirname, '..');
const report = JSON.parse(fs.readFileSync(path.join(root, 'additional-api-candidate-output/report.json'), 'utf8'));
const base = process.env.PREVIEW_BASE || 'http://127.0.0.1:8000';
const output = path.join(root, 'candidate-browser-validation');
fs.mkdirSync(output, {recursive: true});

(async () => {
  const browser = await chromium.launch({headless: true});
  const results = [];
  try {
    for (const width of [320, 390, 1440]) {
      const context = await browser.newContext({viewport: {width, height: 1000}, locale: 'ko-KR', timezoneId: 'Asia/Seoul'});
      await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        const Original = Date;
        window.Date = class extends Original {
          constructor(...args) { super(...(args.length ? args : ['2026-11-03T07:00:00Z'])); }
          static now() { return new Original('2026-11-03T07:00:00Z').getTime(); }
        };
      });
      for (const [kind, url, expectedRows] of [
        ['site', base + '/careerpick/civil-service-exams.html', 28],
        ['candidate', base + '/api-review/civil-service-exams.html', report.mpm_exam.records],
      ]) {
        await page.goto(url, {waitUntil: 'networkidle'});
        await page.waitForFunction(() => document.querySelectorAll('#results article').length > 0);
        assert.equal(await page.locator('#results article').count(), expectedRows);
        assert.match(await page.locator('#count').innerText(), /개 시험단계 · 저장된 일정 기준/);
        const updated = await page.locator('#updated').innerText();
        assert.match(updated, /\(한국시간\)/);
        if (kind === 'site' || report.mode === 'offline') assert.match(updated, /2026-10-26 07:39:58/);
        assert.deepEqual(await page.locator('#year option').allTextContents(), ['2026년']);
        const cards = await page.locator('#results article').allTextContents();
        const early = cards.findIndex(text => text.includes('2026-11-05 ~ 2026-11-06'));
        const later = cards.findIndex(text => text.includes('2026-11-10'));
        assert.ok(early >= 0 && later > early, 'single-digit November dates must sort before November 10');
        assert.ok(cards.some(text => text.includes('시험장소 공고: 미정')));
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
        await page.screenshot({path: path.join(output, kind + '-' + width + '.png'), fullPage: true});
        await page.locator('#type').selectOption('9급');
        assert.equal(await page.locator('#results article').count(), 5);
        await page.locator('#type').selectOption('all');
        await page.locator('#search').fill('민간경력자일괄채용시험');
        assert.equal(await page.locator('#results article').count(), 6);
        await page.locator('#state').selectOption('접수 중');
        assert.match(await page.locator('#results').innerText(), /해당 조건의 시험일정이 없습니다/);
        results.push({kind, width, records: expectedRows, normalized_date_order: true, filters: true, no_horizontal_overflow: true});
      }
      await page.goto(base + '/api-review/', {waitUntil: 'networkidle'});
      assert.equal(await page.locator('tbody tr').count(), 6);
      assert.match(await page.locator('main').innerText(), /신규 지원 가능 자동 인정 0건/);
      assert.match(await page.locator('main').innerText(), /원본 분류 불일치/);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      if (width <= 600) {
        const titleWidth = await page.locator('tbody tr').first().locator('td').nth(1).evaluate(cell => cell.getBoundingClientRect().width);
        assert.ok(titleWidth >= width - 100, 'mobile notice titles need a readable full-width column');
      }
      await page.screenshot({path: path.join(output, 'review-' + width + '.png'), fullPage: true});
      await page.getByRole('link', {name: '시험일정 화면 열기'}).click();
      await page.waitForFunction(() => document.querySelectorAll('#results article').length > 0);
      assert.equal(await page.locator('#results article').count(), report.mpm_exam.records);
      assert.deepEqual(errors, []);
      results.push({kind: 'review', width, gojobs_review_records: 6, unverified_candidates: 0, calendar_link: true, no_horizontal_overflow: true});
      await context.close();
    }
    const result = {status: 'passed', browser: 'chromium', scenarios: results, api_requests: 0, external_browser_requests_allowed: false};
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
