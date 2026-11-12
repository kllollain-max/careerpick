const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('index.html', 'utf8');
const feedNames = ['posts','alio','gojobs','cleaneye','monitor'];

test('independent feeds start before first awaited merge', () => {
  const start = html.indexOf('async function load(){');
  assert.ok(start >= 0);
  const body = html.slice(start, html.indexOf('const DISCLOSURE', start));
  for (const key of feedNames) {
    assert.match(body, new RegExp('Promise\\.allSettled\\(\\[cpReadFeed\\("'+key+'\\.json","'+key+'"\\)\\]\\)'));
    assert.match(html, new RegExp('await cpReadyFeed\\("'+key+'\\.json","'+key+'"\\)'));
  }
  assert.ok(body.indexOf('cpFeedBatch = Object.fromEntries') < body.indexOf('await cpReadyFeed("posts.json"'));
});

test('settled feed helper preserves success and throws failures', async () => {
  const start = html.indexOf('let cpFeedBatch = null;');
  const end = html.indexOf('async function load(){', start);
  assert.ok(start >= 0 && end > start);
  const sandbox = { cpReadFeed: async () => ['fallback'] };
  vm.createContext(sandbox);
  vm.runInContext(html.slice(start,end) + '\nthis.setBatch = value => { cpFeedBatch = value; }; this.ready = cpReadyFeed;', sandbox);
  sandbox.setBatch({
    posts: Promise.resolve({status:'fulfilled',value:[1,2]}),
    alio: Promise.resolve({status:'rejected',reason:new Error('offline')})
  });
  assert.deepEqual(Array.from(await sandbox.ready('posts.json','posts')), [1,2]);
  await assert.rejects(sandbox.ready('alio.json','alio'), /offline/);
  sandbox.setBatch(null);
  assert.deepEqual(Array.from(await sandbox.ready('other.json','other')), ['fallback']);
});

test('existing capped card rendering and font fallback remain', () => {
  assert.ok(html.includes('rows.slice(0,cpVisibleLimit)'));
  assert.ok(html.includes('<noscript><link href="https://fonts.googleapis.com'));
});

test('all inline JavaScript blocks parse without syntax errors', () => {
  const scripts = [...html.matchAll(/<script(?:\\s[^>]*)?>([\\s\\S]*?)<\\/script>/gi)];
  let checked = 0;
  for (const match of scripts) {
    if (!match[1].trim()) continue;
    assert.doesNotThrow(() => new vm.Script(match[1]), 'inline script '+(++checked));
  }
  assert.ok(checked >= 2, 'expected inline scripts');
});

test('critical navigation and user data entry points remain present', () => {
  for (const key of ['renderTabs()', 'renderFilters()', 'savedAlert()', 'function renderTrack(', 'function load(', 'function render(']) {
    assert.ok(html.includes(key), 'missing '+key);
  }
});
