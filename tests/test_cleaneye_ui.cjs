const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const home = require('../homepage-ux.js');
const records = require('../record-migration.js');

const html = fs.readFileSync(require.resolve('../index.html'), 'utf8');
const ui = fs.readFileSync(require.resolve('../homepage-ui.js'), 'utf8');
const now = new Date('2026-11-07T09:00:00+09:00');
// Synthetic fixtures are confined to tests; they are never published as jobs.
const row = (changes = {}) => ({
  id: 'cleaneye-TEST_42', type: 'j', cleaneye: true,
  source: '클린아이 잡플러스', title: '테스트 지방공공기관 채용', org: '테스트 기관',
  url: 'https://job.cleaneye.go.kr/fixture/notice?no=TEST_42',
  pub: null, start: null, due: null, dueHasTime: false,
  emp: [], edu: [], region: '', n: null, text: '', cleaneyeDetail: {},
  ...changes,
});
const feed = (posts = [], collectionStatus = 'verified') => ({
  source: 'cleaneye', updated: '2026-11-07T09:00:00+09:00', collectionStatus, posts,
});
function functionCode(name, source = html) {
  const match = source.match(new RegExp('(?:async )?function ' + name + '\\([^\\n]*'));
  assert(match, name + ' exists');
  if (match[0].trimEnd().endsWith('}')) return match[0];
  const end = source.indexOf('\n}', match.index);
  assert(end >= 0, name + ' has a function boundary');
  return source.slice(match.index, end + 2);
}

test('Cleaneye accepts only the two official HTTPS hosts without credentials or custom ports', () => {
  for (const host of ['job.cleaneye.go.kr', 'www.job.cleaneye.go.kr']) {
    const url = `https://${host}/fixture/notice?no=TEST_42`;
    assert.equal(home.cleaneyeUrl(url), url);
    assert.equal(home.parseFeed(feed([row({url})])).rows.length, 1);
  }
  for (const url of [
    'javascript:alert(1)', 'http://job.cleaneye.go.kr/fixture',
    'https://job.cleaneye.go.kr.evil.example/fixture', 'https://evil.example/fixture',
    'https://job.cleaneye.go.kr@evil.example/fixture',
    'https://user:pass@job.cleaneye.go.kr/fixture', 'https://job.cleaneye.go.kr:8443/fixture',
  ]) {
    assert.equal(home.cleaneyeUrl(url), '');
    const parsed = home.parseFeed(feed([row({url})]));
    assert.equal(parsed.rows.length, 0);
    assert(parsed.issues.includes('invalid_row'));
  }
});

test('Cleaneye preserves unknown dates and conditions without inventing employment from a title', () => {
  const raw = row({title: '정규직·공무직 채용 관련 안내', cleaneyeDetail: {'고용형태': '99'}});
  const before = JSON.stringify(raw);
  const parsed = home.parseFeed(feed([raw]));
  const p = parsed.rows[0];
  assert.equal(p.pub, null);
  assert.equal(p.start, null);
  assert.equal(p.due, null);
  assert.equal(p.dueHasTime, false);
  assert.deepEqual(p.emp, []);
  assert.deepEqual(home.employment(p), []);
  assert.equal(home.sector(p), 'public');
  assert.equal(home.deadline(p, now), null);
  assert.deepEqual(parsed.issues, []);
  assert.equal(JSON.stringify(raw), before);
});

test('opaque source IDs retain punctuation while respecting existing backup ID length limits', () => {
  for (const id of ['cleaneye-TEST:42.1', 'cleaneye-' + 'A'.repeat(119)]) {
    assert.equal(home.parseFeed(feed([row({id})])).rows[0].id, id);
    assert.doesNotThrow(() => records.validate({format: 'careerpick-backup', version: 1, data: {saved: [id]}}));
  }
  assert.equal(home.parseFeed(feed([row({id: 'cleaneye-' + 'A'.repeat(120)})])).rows.length, 0);
});

test('structured regular and contract jobs use public sector filters without substring confusion', () => {
  const regular = home.parseFeed(feed([row({emp: ['정규직']})])).rows[0];
  const contract = home.parseFeed(feed([row({emp: ['계약직']})])).rows[0];
  assert(home.matches(regular, {sector: 'public', employment: '정규직'}));
  assert(!home.matches(contract, {sector: 'public', employment: '정규직'}));
  assert(home.matches(contract, {sector: 'public', employment: '비정규직'}));
  assert.equal(home.sector({...regular, emp: ['무기계약직']}), 'service');
});

test('Cleaneye dates keep the actual start and never turn date-only deadlines into exact cutoffs', () => {
  const p = home.parseFeed(feed([row({start: '2026-11-08', due: '2026-11-30', dueHasTime: true})])).rows[0];
  assert.equal(p.start, '2026-11-08');
  assert.equal(p.pub, null);
  assert.equal(p.dueHasTime, false);
  assert.equal(home.deadline(p, now).cls, 'upcoming');
  const invalid = home.parseFeed(feed([row({pub: 'bad', start: '2026-02-31', due: 'not a date'})]));
  assert.equal(invalid.rows[0].pub, null);
  assert.equal(invalid.rows[0].start, null);
  assert.equal(invalid.rows[0].due, null);
  for (const issue of ['invalid_pub', 'invalid_date', 'invalid_deadline']) assert(invalid.issues.includes(issue));
});

test('preserved uncertain, expired and cancelled jobs never appear as verified open jobs', () => {
  for (const receptionState of ['verification_pending', 'source_error', 'invalid_date']) {
    for (const due of [null, '2099-12-31']) {
      const state = home.deadline(row({receptionState, due}), now);
      assert.equal(state.cls, 'verify');
      assert.equal(state.big, '상태 확인');
    }
  }
  for (const receptionState of ['expired', 'cancelled']) {
    for (const due of [null, '2099-12-31']) assert.equal(home.deadline(row({receptionState, due}), now).cls, 'closed');
  }
  assert.equal(home.deadline(row({receptionState: 'verification_pending', due: '2026-11-01'}), now).cls, 'closed');
});

async function loadCase(data, original = [{id: 'a1', alio: true}, {id: 'gojobs-1', gojobs: true}]) {
  const calls = [];
  const context = vm.createContext({
    CPHome: home, POSTS: original.slice(), DATA_HEALTH: {alio: 'ok', gojobs: 'ok'},
    CP_FEED_STAMPS: {}, CP_FEED_ISSUES: {}, CP_FEED_COLLECTION: {},
    fetch: async (url, options) => {
      calls.push(url);
      assert.match(url, /^cleaneye\.json\?t=\d+$/);
      assert.equal(options.cache, 'no-store');
      if (data instanceof Error) throw data;
      return {ok: true, json: async () => data};
    },
    localStorage: {setItem() { assert.fail('loading public jobs must not write personal records'); }},
  });
  vm.runInContext(functionCode('cpReadFeed', ui), context);
  vm.runInContext(functionCode('loadCleaneye'), context);
  await vm.runInContext('loadCleaneye()', context);
  return {context, calls, original};
}

test('Cleaneye loader appends source-specific IDs once and leaves existing official records intact', async () => {
  const p = row();
  const second = row({id: 'cleaneye-TEST_43', url: 'https://job.cleaneye.go.kr/fixture/notice?no=TEST_43'});
  const {context, calls, original} = await loadCase(feed([p, p, second]));
  assert.deepEqual(Array.from(context.POSTS, p => p.id), ['a1', 'gojobs-1', p.id, second.id]);
  assert.strictEqual(context.POSTS[0], original[0]);
  assert.strictEqual(context.POSTS[1], original[1]);
  assert.equal(context.DATA_HEALTH.cleaneye, 'ok');
  assert.equal(context.CP_FEED_STAMPS.cleaneye, '2026-11-07T09:00:00+09:00');
  assert.equal(calls.length, 1);
});

test('first collection pending, a verified empty feed and failed collection have different states', async () => {
  const pending = await loadCase({...feed([], 'not_collected'), updated: null});
  assert.equal(pending.context.DATA_HEALTH.cleaneye, 'not_collected');
  assert.equal(pending.context.POSTS.length, 2);
  assert(home.healthNotices({cleaneye: 'not_collected'}, {}, {}, now)[0].includes('아직 수집'));
  const empty = await loadCase(feed([]));
  assert.equal(empty.context.DATA_HEALTH.cleaneye, 'empty');
  for (const input of [new Error('offline'), null, {}, feed([row()], 'not_collected'), feed([row()], 'pending')]) {
    const failed = await loadCase(input);
    assert.equal(failed.context.DATA_HEALTH.cleaneye, 'error');
    assert.equal(failed.context.POSTS.length, 2);
  }
});

test('invalid source rows are excluded and cannot be reported as a healthy empty feed', async () => {
  for (const changes of [
    {id: 'a1'}, {id: 'cleaneye-<bad>'}, {type: 'm'}, {url: 'https://evil.example/job'},
  ]) {
    const {context} = await loadCase(feed([row(changes)]));
    assert.equal(context.DATA_HEALTH.cleaneye, 'error');
    assert.deepEqual(Array.from(context.POSTS, p => p.id), ['a1', 'gojobs-1']);
  }
});

test('similar titles from ALIO, Gojobs and Cleaneye remain separate without verified identity evidence', () => {
  const p = row({title: '동일한 채용 제목'});
  const input = [
    {...p, id: 'a1', cleaneye: undefined, alio: true, url: 'https://job.alio.go.kr/recruitview.do?idx=1'},
    {...p, id: 'gojobs-1', cleaneye: undefined, gojobs: true, url: 'https://www.gojobs.go.kr/apmView.do?empmnsn=1'},
    p,
  ];
  const before = JSON.stringify(input);
  assert.deepEqual(home.unifyNotices(input).rows.map(p => p.id), ['a1', 'gojobs-1', p.id]);
  assert.equal(home.unifyNotices(input).removed, 0);
  assert.equal(JSON.stringify(input), before);
});

test('existing saved/application backup format accepts Cleaneye IDs without changing prior records', () => {
  const saved = ['a1', 'gojobs-1', 'cleaneye-TEST_42'];
  const apps = {a1: {st: 'applied', memo: '기존 메모'}, 'cleaneye-TEST_42': {st: 'plan', memo: '새 메모'}};
  const data = {saved, apps};
  assert.deepEqual(records.validate({format: 'careerpick-backup', version: 1, data}), data);
  const context = vm.createContext({SAVED: new Set(saved), APPS: apps, p: row()});
  for (const name of ['cpSavedId', 'cpApplicationId']) vm.runInContext(functionCode(name), context);
  assert.equal(vm.runInContext('cpSavedId(p)', context), row().id);
  assert.equal(vm.runInContext('cpApplicationId(p)', context), row().id);
  assert.deepEqual(Array.from(context.SAVED), saved);
  assert.equal(apps.a1.memo, '기존 메모');
});

test('personalized conditions use Cleaneye structured fields and exclude explicit closed status', () => {
  const context = vm.createContext({CPHome: home, ALIO_DETAIL: null, CP_REGION_ALIASES: {강원: ['강원', '춘천']}});
  for (const name of ['cpWorkRegionMatch', 'cpConditionMatches']) vm.runInContext(functionCode(name), context);
  context.p = home.parseFeed(feed([row({emp: ['정규직'], edu: ['학력무관'], region: '강원 춘천', text: '시설관리 직무', due: '2099-12-31'})])).rows[0];
  context.prefs = {emp: ['정규직'], edu: ['학력무관'], region: ['강원'], cat: [], kw: '시설관리'};
  assert(vm.runInContext('cpConditionMatches(p,prefs)', context));
  context.p.emp = [];
  assert(!vm.runInContext('cpConditionMatches(p,prefs)', context));
  context.p.emp = ['정규직']; context.p.receptionState = 'cancelled';
  assert(!vm.runInContext('cpConditionMatches(p,prefs)', context));
});

function renderingContext(p) {
  const context = vm.createContext({
    CPHome: home, p, SAVED: new Set(), APPS: {}, ALIO_DETAIL: null,
    CP_FEED_STAMPS: {cleaneye: '2026-11-07T09:00:00+09:00'}, UPDATED: 'BLOG-ONLY-STAMP',
    JV_SUMMARY: [['recrutNope', '모집 인원'], ['workRgnNmLst', '근무 지역']], JV_SKIP: new Set(), JV_SECTIONS: [],
    dday: p => home.deadline(p, now), dueLong: () => '12.31',
    md: d => { assert(d instanceof Date, 'unknown dates must not be formatted'); return '12.31'; },
    isNew: () => false, regionLabel: p => p.region, isInternalJob: p => p.type === 'j',
    jobHref: p => '#job=' + p.id, jobAnchorAttrs: p => ` data-open="${p.id}"`,
    specOf: () => null, specPill: () => '', preferenceBadge: () => '',
    cpVerifiedRecruitLinks: () => null, cpMergedSourceLinks: () => '', standaloneJobLink: () => '',
    specBoxHTML: () => '', ckBoxHTML: () => '', cpApplicationGuide: () => '',
    document: {createElement: () => ({
      value: '',
      set innerHTML(value) { this.value = value.replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&amp;', '&'); },
    })},
  });
  for (const name of ['esc', 'plainText', 'cpSavedId', 'cpApplicationId', 'cleanTitle', 'cpRecruitCount', 'cpDetailWarnings', 'cpJobLinks', 'officialLink', 'jobCard', 'rowCard', 'jobViewHTML', 'sortKey']) {
    vm.runInContext(functionCode(name), context);
  }
  return context;
}

test('cards and details show Cleaneye origin, official links and short Korean field labels', () => {
  const p = home.parseFeed(feed([row({cleaneyeDetail: {
    '고용형태': '정규직', '학력': '무관', '모집 인원': '4', '지원 자격': '원문 자격 확인',
    '기타 안내': '&lt;img src=x onerror=alert(1)&gt;',
  }})])).rows[0];
  const context = renderingContext(p);
  const card = vm.runInContext('jobCard(p,new Date())', context);
  const compact = vm.runInContext('rowCard(p,new Date())', context);
  const detail = vm.runInContext('jobViewHTML(p,p.cleaneyeDetail)', context);
  for (const output of [card, compact, detail]) assert(output.includes('클린아이 잡플러스'));
  assert(card.includes(p.url)); assert(detail.includes(p.url));
  assert(detail.includes('<dt>학력</dt><dd>무관</dd>'));
  assert(detail.includes('<h3>지원 자격</h3>'));
  assert(detail.includes('2026-11-07T09:00:00+09:00'));
  assert(!detail.includes('BLOG-ONLY-STAMP'));
  assert(!detail.includes('채용 이력·다음 공고'));
  assert(!detail.includes('<img'));
  assert(!detail.includes('1970'));
});

test('uncertain and cancelled cards with no dates render and sort safely', () => {
  for (const receptionState of ['verification_pending', 'cancelled']) {
    const p = home.parseFeed(feed([row({receptionState})])).rows[0];
    const context = renderingContext(p);
    const card = vm.runInContext('jobCard(p,new Date())', context);
    const compact = vm.runInContext('rowCard(p,new Date())', context);
    const expected = receptionState === 'cancelled' ? '취소' : '상태 확인';
    assert(card.includes(expected)); assert(compact.includes(expected));
    assert.doesNotThrow(() => vm.runInContext('sortKey(p,new Date())', context));
  }
});

test('card counts preserve mixed official text without duplicating the people unit', () => {
  for (const n of ['약 2명', '2명(예비 3명)', 4]) {
    const context = renderingContext(home.parseFeed(feed([row({n})])).rows[0]);
    for (const functionName of ['jobCard', 'rowCard']) {
      const rendered = vm.runInContext(functionName + '(p,new Date())', context);
      assert(rendered.includes(typeof n === 'number' ? '4명' : n));
      assert(!rendered.includes('명명'));
      assert(!rendered.includes('3명)명'));
    }
  }
});
