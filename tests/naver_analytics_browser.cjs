'use strict';

// Isolated browser contract checks: every request is intercepted. The NAVER SDK
// is a local stub; this script never sends a pageview or opens an analytics account.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test, before, after } = require('node:test');
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (error) {
  if (!process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES) throw error;
  ({ chromium } = require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')));
}

const ROOT = path.resolve(__dirname, '..');
const BASE = 'https://kllollain-max.github.io';
const KEY = 'careerpick:naver-analytics-consent:v1';
const ID = '1e121e3d2f09900';
const SCRIPT = fs.readFileSync(path.join(ROOT, 'naver-analytics.js'), 'utf8');
const CSS = fs.readFileSync(path.join(ROOT, 'naver-analytics.css'), 'utf8');
const SDK = `window.wcs = {}; window.__testNaver = [];
  window.wcs_do = function () { window.__testNaver.push(window.wcs_add.wa); };`;
const HTML = `<!doctype html><html lang="ko"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>통계 연결 모의검증</title>
  <link rel="stylesheet" href="/careerpick/naver-analytics.css">
  </head><body><main><h1>공고 안내</h1>
  <button id="site-action" type="button">공고 보기</button><output id="site-result"></output>
  </main><script>document.getElementById('site-action').addEventListener('click', function () {
    document.getElementById('site-result').textContent = '공고 열림';
  });</script><script defer src="/careerpick/naver-analytics.js"></script></body></html>`;
let browser;

before(async () => {
  browser = await chromium.launch({
    headless: true,
    ...(process.env.CP_ANALYTICS_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.CP_ANALYTICS_CHROMIUM_EXECUTABLE } : {}),
  });
});
after(async () => { if (browser) await browser.close(); });

async function fixture(options = {}) {
  const context = await browser.newContext({ viewport: { width: options.width || 390, height: 844 } });
  const traffic = { sdk: 0, otherExternal: [] };
  const errors = [];
  context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
  if (options.storageDenied) {
    await context.addInitScript(({ key }) => {
      const get = Storage.prototype.getItem;
      const set = Storage.prototype.setItem;
      Storage.prototype.getItem = function (name) {
        if (name === key) throw new DOMException('Storage denied', 'SecurityError');
        return get.call(this, name);
      };
      Storage.prototype.setItem = function (name, value) {
        if (name === key) throw new DOMException('Storage denied', 'SecurityError');
        return set.call(this, name, value);
      };
    }, { key: KEY });
  }
  if (options.conflict) {
    await context.addInitScript(() => {
      window.wcs = {};
      window.wcs_add = { wa: 'different-site-id' };
      window.__otherAnalyticsCalls = 0;
      window.wcs_do = () => { window.__otherAnalyticsCalls += 1; };
    });
  }
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === BASE) {
      if (url.pathname === '/careerpick/naver-analytics.js') {
        return route.fulfill({ contentType: 'text/javascript', body: SCRIPT });
      }
      if (url.pathname === '/careerpick/naver-analytics.css') {
        return route.fulfill({ contentType: 'text/css', body: CSS });
      }
      return route.fulfill({ contentType: 'text/html', body: HTML });
    }
    if (url.origin === 'https://wcs.pstatic.net' && url.pathname === '/wcslog.js') {
      traffic.sdk += 1;
      if (options.sdkFailure) return route.abort('failed');
      return route.fulfill({ contentType: 'text/javascript', body: SDK });
    }
    traffic.otherExternal.push(url.origin);
    return route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  await page.goto(BASE + (options.sibling ? '/supportpick/' : '/careerpick/'));
  if (!options.sibling) await page.waitForSelector('#cp-naver-analytics');
  return { context, page, traffic, errors };
}

async function state(page, value) {
  await page.waitForFunction(expected => {
    const root = document.getElementById('cp-naver-analytics');
    return root && root.dataset.analyticsState === expected;
  }, value);
}

async function allow(page) {
  if (!(await page.locator('#cp-analytics-allow').isVisible())) {
    await page.click('#cp-analytics-settings');
  }
  await page.click('#cp-analytics-allow');
}

async function originalActionStillWorks(page) {
  await page.click('#site-action');
  assert.equal(await page.textContent('#site-result'), '공고 열림');
}

test('default and denied states send no SDK request; mobile controls fit 320px', { timeout: 15000 }, async () => {
  const f = await fixture({ width: 320 });
  try {
    assert.equal(f.traffic.sdk, 0);
    assert.equal(await f.page.getAttribute('#cp-naver-analytics', 'data-choice'), 'unset');
    assert.ok(await f.page.locator('#cp-analytics-allow').isVisible());
    assert.ok(await f.page.locator('#cp-analytics-deny').isVisible());
    assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await f.page.click('#cp-analytics-deny');
    assert.equal(await f.page.evaluate(key => localStorage.getItem(key), KEY), 'denied');
    await f.page.reload();
    await f.page.waitForSelector('#cp-naver-analytics');
    assert.equal(f.traffic.sdk, 0);
    await f.page.click('#cp-analytics-settings');
    assert.ok(await f.page.locator('#cp-analytics-allow').isVisible());
    await originalActionStillWorks(f.page);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('explicit consent sends the supplied ID once per document, including repeat initialization', { timeout: 15000 }, async () => {
  const f = await fixture();
  try {
    await allow(f.page);
    await state(f.page, 'sent');
    assert.deepEqual(await f.page.evaluate(() => window.__testNaver), [ID]);
    assert.equal(f.traffic.sdk, 1);
    await f.page.addScriptTag({ content: SCRIPT });
    await f.page.click('#cp-analytics-settings');
    await f.page.click('#cp-analytics-allow');
    assert.deepEqual(await f.page.evaluate(() => window.__testNaver), [ID]);
    assert.equal(f.traffic.sdk, 1);
    assert.equal(await f.page.locator('#cp-naver-analytics').count(), 1);
    await f.page.reload();
    await state(f.page, 'sent');
    assert.deepEqual(await f.page.evaluate(() => window.__testNaver), [ID]);
    assert.equal(f.traffic.sdk, 2, 'one SDK load on each of two documents');
    assert.deepEqual(f.traffic.otherExternal, []);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('withdrawing consent reloads into a denied document without loading the SDK again', { timeout: 15000 }, async () => {
  const f = await fixture();
  try {
    await allow(f.page);
    await state(f.page, 'sent');
    await f.page.click('#cp-analytics-settings');
    await Promise.all([
      f.page.waitForNavigation({ waitUntil: 'load' }),
      f.page.click('#cp-analytics-deny'),
    ]);
    await f.page.waitForSelector('#cp-naver-analytics');
    assert.equal(await f.page.evaluate(key => localStorage.getItem(key), KEY), 'denied');
    assert.equal(await f.page.getAttribute('#cp-naver-analytics', 'data-choice'), 'denied');
    assert.equal(f.traffic.sdk, 1);
    assert.equal(await f.page.locator('#cp-naver-analytics-sdk').count(), 0);
    await originalActionStillWorks(f.page);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('SDK failure does not break existing page actions', { timeout: 15000 }, async () => {
  const f = await fixture({ sdkFailure: true });
  try {
    await allow(f.page);
    await state(f.page, 'failed');
    assert.equal(f.traffic.sdk, 1);
    await originalActionStillWorks(f.page);
    await f.page.click('#cp-analytics-settings');
    assert.ok(await f.page.locator('#cp-analytics-deny').isVisible());
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('unavailable storage keeps the default off and explains that the choice is not persistent', { timeout: 15000 }, async () => {
  const f = await fixture({ storageDenied: true });
  try {
    assert.equal(f.traffic.sdk, 0);
    await allow(f.page);
    await state(f.page, 'sent');
    assert.deepEqual(await f.page.evaluate(() => window.__testNaver), [ID]);
    assert.match(await f.page.textContent('#cp-analytics-status'), /저장|다음|유지/);
    await f.page.reload();
    await f.page.waitForSelector('#cp-naver-analytics');
    assert.equal(await f.page.getAttribute('#cp-naver-analytics', 'data-choice'), 'unset');
    assert.equal(f.traffic.sdk, 1);
    await originalActionStillWorks(f.page);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('the sibling SupportPick path never initializes CareerPick analytics', { timeout: 15000 }, async () => {
  const f = await fixture({ sibling: true });
  try {
    assert.equal(await f.page.locator('#cp-naver-analytics').count(), 0);
    assert.equal(f.traffic.sdk, 0);
    assert.equal(await f.page.evaluate(() => typeof window.wcs_add), 'undefined');
    await originalActionStillWorks(f.page);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('an existing analytics ID is not overwritten or reported for CareerPick', { timeout: 15000 }, async () => {
  const f = await fixture({ conflict: true });
  try {
    await allow(f.page);
    await state(f.page, 'conflict');
    assert.equal(f.traffic.sdk, 0);
    assert.equal(await f.page.evaluate(() => window.wcs_add.wa), 'different-site-id');
    assert.equal(await f.page.evaluate(() => window.__otherAnalyticsCalls), 0);
    await originalActionStillWorks(f.page);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('a storage event withdraws consent in another already-open tab', { timeout: 20000 }, async () => {
  const f = await fixture();
  try {
    await allow(f.page);
    await state(f.page, 'sent');
    const second = await f.context.newPage();
    await second.goto(BASE + '/careerpick/jobs/sample.html');
    await state(second, 'sent');
    assert.equal(f.traffic.sdk, 2);
    await f.page.click('#cp-analytics-settings');
    await Promise.all([
      f.page.waitForNavigation({ waitUntil: 'load' }),
      second.waitForNavigation({ waitUntil: 'load' }),
      f.page.click('#cp-analytics-deny'),
    ]);
    await second.waitForSelector('#cp-naver-analytics');
    assert.equal(await second.getAttribute('#cp-naver-analytics', 'data-choice'), 'denied');
    assert.equal(f.traffic.sdk, 2);
    assert.equal(await second.locator('#cp-naver-analytics-sdk').count(), 0);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});
