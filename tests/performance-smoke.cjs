// Run locally: node tests/performance-smoke.cjs
// No GitHub Actions, dependencies or network access required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const required = [
  ['search', 'haystack(p).includes(q)'],
  ['filter', 'CPHome.matches(p,state)'],
  ['region', 'cpRegionMatches(p, state.region)'],
  ['pagination', 'rows.slice(0,cpVisibleLimit)'],
  ['saved state', 'localStorage.setItem("saved"'],
  ['offscreen optimization', 'content-visibility:auto'],
  ['indexed ALIO merge', 'blogByNoticeKey.get(key)'],
];
for (const [name, token] of required) {
  assert.ok(html.includes(token), 'Missing ' + name);
  console.log('PASS: ' + name);
}
const rows = Array.from({length:955}, (_,i)=>({id:i, key: 'key-'+(i%410)}));
const index = new Map();
for(const row of rows) if(row.key && !index.has(row.key)) index.set(row.key,row);
for(const key of ['key-0','key-100','key-409','missing',null]){
  const before = key && rows.find(row=>row.key===key);
  const after = key && index.get(key);
  assert.deepEqual(after,before);
}
console.log('PASS: 955-row synthetic ALIO lookup equivalence');
console.log('Static checks only; browser behavior and speed are NOT verified.');
