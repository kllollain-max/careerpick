const { chromium } = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
(async () => {
  const html = fs.readFileSync('index.html', 'utf8');
  const isSupport = html.includes('<title>지원금픽');
  const expected = isSupport ? '/careerpick/' : '/supportpick/';
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 850 } });
      await page.route('**/*', route => {
        if (route.request().isNavigationRequest() && route.request().url().includes('github.io')) return route.abort();
        return route.continue();
      });
      await page.goto('file://' + process.cwd() + '/index.html', { waitUntil: 'domcontentloaded' });
      const banner = page.locator('a.cross-site-banner');
      assert.equal(await banner.count(), 1);
      assert.equal(await banner.isVisible(), true);
      const href = await banner.getAttribute('href');
      assert.ok(href.includes(expected));
      assert.ok(href.includes('utm_campaign=cross_site_banner'));
      assert.equal(await banner.getAttribute('target'), '_blank');
      const rect = await banner.boundingBox();
      assert.ok(rect && rect.width > 0 && rect.x >= -1 && rect.x + rect.width <= width + 1, 'Banner overflows viewport');
      await page.screenshot({ path: 'banner-' + width + '.png', fullPage: false });
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
