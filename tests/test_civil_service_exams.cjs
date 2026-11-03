const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'civil-service-exams.html'), 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function harness(search = "") {
  const ids = ['search', 'state', 'type', 'sort', 'count', 'results', 'updated', 'year'];
  const elements = Object.fromEntries(ids.map(id => [id, {
    value: ({state: 'all', type: 'all', sort: 'exam', year: '2026'})[id] || '',
    textContent: '', innerHTML: '', addEventListener() {},
  }]));
  const requests = [];
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : ['2026-11-03T04:00:00Z'])); }
    static now() { return new Date('2026-11-03T04:00:00Z').getTime(); }
  }
  const context = vm.createContext({
    Intl, Date: Clock, URLSearchParams, location: {search},
    document: {
      querySelector: selector => elements[selector.slice(1)],
      getElementById: id => elements[id],
    },
    fetch: url => {
      // Leave bootstrapping pending; every tested year request is controlled.
      if (url.endsWith('/years.json')) return new Promise(() => {});
      return new Promise((resolve, reject) => requests.push({url, resolve, reject}));
    },
  });
  vm.runInContext(source + `
    globalThis.api = {range, status, scheduleText, retrievedAt, manifestYears, render, loadYear,
      setRecords: value => { records = value; }, setYears: value => { availableYears = value; }};
  `, context);
  return {api: context.api, elements, requests};
}

function row(title, exam = '2026-11-10', apply = '2026-07-27~2026-07-31') {
  return {'시험명': title, '시험단계구분': '면접시험', '선발예정인원': '10',
    '시험일': exam, '원서접수기간': apply, '시험장소공고일': null, '합격자발표일': '2026-12-11'};
}

test('single-digit saved dates are normalized and sorted before later November exams', () => {
  const {api, elements} = harness();
  assert.deepEqual(Array.from(api.range('2026-11-5~2026-11-6')), ['2026-11-05', '2026-11-06']);
  api.setRecords([row('11월 10일 시험'), row('11월 5일 시험', '2026-11-5~2026-11-6')]);
  api.render();
  assert.ok(elements.results.innerHTML.indexOf('11월 5일 시험') < elements.results.innerHTML.indexOf('11월 10일 시험'));
  assert.match(elements.results.innerHTML, /2026-11-05 ~ 2026-11-06/);
});

test('invalid dates, reversed ranges and partial matches never create an application status', () => {
  const {api} = harness();
  for (const value of ['2026-02-30', '2026-02-29', '2026-13-1', '2026-11-6~2026-11-5',
    '2026-11-01~미정', '2026-11-01garbage', '2026-11-01~2026-11-04~2026-11-05']) {
    assert.deepEqual(Array.from(api.range(value)), ['', ''], value);
    assert.equal(api.status(row('일정', '2026-11-10', value)), '일정 확인 필요');
    assert.equal(api.scheduleText(value), '공고 확인 필요');
  }
  assert.deepEqual(Array.from(api.range('2024-2-29')), ['2024-02-29', '2024-02-29']);
});

test('blank schedules are explicit and application closure is separate from future exam dates', () => {
  const {api, elements} = harness();
  for (const value of [null, undefined, '', '  ', '-', '미정']) assert.equal(api.scheduleText(value), '미정');
  const futureExam = row('11월 예정 시험', '2026-11-5~2026-11-6');
  assert.equal(api.status(futureExam), '접수 마감');
  assert.equal(api.status(row('접수중', '2026-12-11', '2026-11-1~2026-11-4')), '접수 중');
  api.setRecords([futureExam]); api.render();
  assert.match(elements.results.innerHTML, /시험장소 공고: 미정/);
  assert.match(elements.count.textContent, /시험단계 · 저장된 일정 기준/);
  assert.match(html, /접수 마감은 원서접수가 끝났다는 뜻으로 시험 종료와는 다릅니다/);
});

test('search and type/application filters remain independent', () => {
  const {api, elements} = harness();
  api.setRecords([row('9급 공개경쟁시험'), row('7급 공개경쟁시험')]);
  elements.type.value = '9급'; api.render();
  assert.match(elements.results.innerHTML, /9급 공개경쟁시험/);
  assert.doesNotMatch(elements.results.innerHTML, /7급 공개경쟁시험/);
  elements.type.value = 'all'; elements.search.value = '7급'; api.render();
  assert.match(elements.results.innerHTML, /7급 공개경쟁시험/);
  elements.state.value = '접수 중'; api.render();
  assert.equal(elements.results.innerHTML, '해당 조건의 시험일정이 없습니다.');
});

test('retrieval timestamp uses its original instant in Korea without claiming a fresh fetch', () => {
  const {api} = harness();
  assert.equal(api.retrievedAt('2026-10-25T22:39:58.281891+00:00'), '2026-10-26 07:39:58 (한국시간)');
  assert.equal(api.retrievedAt('2026-10-26T07:39:58+09:00'), '2026-10-26 07:39:58 (한국시간)');
  for (const value of [null, '', '2026-10-25', '2026-10-25T22:39:58', '2026-02-30T00:00:00Z'])
    assert.equal(api.retrievedAt(value), '미확인');
});

test('manifest requires matching year/path pairs and does not invent available years', () => {
  const {api} = harness();
  const values = api.manifestYears({years: [null,
    {year: 2025, path: 'data/civil-service/2026.json'},
    {year: 2026, path: 'https://example.invalid/2026.json'},
    {year: 2026, path: 'data/civil-service/2026.json'},
    {year: 2026, path: 'data/civil-service/2026.json'}]});
  assert.equal(values.length, 1);
  assert.equal(values[0].year, 2026);
});

test('older year responses and older failures cannot overwrite the selected year', async () => {
  for (const oldFails of [false, true]) {
    const {api, elements, requests} = harness();
    api.setYears([{year: 2025, path: 'data/civil-service/2025.json'}, {year: 2026, path: 'data/civil-service/2026.json'}]);
    elements.year.value = '2025'; const old = api.loadYear('2025');
    elements.year.value = '2026'; const current = api.loadYear('2026');
    requests[1].resolve({ok: true, json: async () => ({records: [row('선택한 연도')], retrieved_at: '2026-10-25T22:39:58+00:00'})});
    await current;
    const rendered = elements.results.innerHTML, stamp = elements.updated.textContent;
    if (oldFails) requests[0].reject(new Error('old request failed'));
    else requests[0].resolve({ok: true, json: async () => ({records: [row('이전 연도')], retrieved_at: '2025-01-01T00:00:00Z'})});
    await old;
    assert.equal(elements.results.innerHTML, rendered);
    assert.equal(elements.updated.textContent, stamp);
    assert.match(stamp, /선택 연도: 2026년.*2026-10-26 07:39:58/);
  }
});

test('a failed selected-year request clears stale counts and retrieval time', async () => {
  const {api, elements, requests} = harness();
  api.setYears([{year: 2026, path: 'data/civil-service/2026.json'}]);
  elements.updated.textContent = 'old timestamp'; elements.count.textContent = 'old count';
  const pending = api.loadYear('2026');
  requests[0].resolve({ok: false}); await pending;
  assert.equal(elements.updated.textContent, '');
  assert.equal(elements.count.textContent, '');
  assert.match(elements.results.textContent, /불러오지 못했습니다/);
});


test('shared detail URL selects stable name and stage while retaining dates', () => {
  const key='9급 공개경쟁시험|면접시험';
  const {api,elements}=harness('?year=2026&exam='+encodeURIComponent(key));
  api.setRecords([row('9급 공개경쟁시험'),row('7급 공개경쟁시험')]);
  api.render();
  assert.match(elements.results.innerHTML,/9급 공개경쟁시험/);
  assert.doesNotMatch(elements.results.innerHTML,/7급 공개경쟁시험/);
  assert.match(elements.results.innerHTML,/원서접수/);
  assert.match(elements.results.innerHTML,/시행기관: 인사혁신처/);
  assert.match(elements.results.innerHTML,/전체 시험일정/);
});
