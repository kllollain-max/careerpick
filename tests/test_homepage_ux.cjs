const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const home = require('../homepage-ux.js');
const now = new Date('2026-10-29T12:00:00Z');
test('date-only deadline remains uncertain for the entire KST deadline day',()=>{
  const p={due:'2026-10-29T23:59:00+09:00',dueHasTime:false};
  assert.equal(home.deadline(p,now).cls,'verify');
  assert.equal(home.deadline(p,new Date('2026-10-29T14:59:59Z')).cls,'verify');
  assert.equal(home.deadline(p,new Date('2026-10-29T15:00:00Z')).cls,'closed');
});
test('exact deadline expires at equality',()=>assert.equal(home.deadline({due:now,dueHasTime:true},now).cls,'closed'));
test('invalid and missing dates never imply an open recruitment',()=>{
  for(const due of [null,'','bad date']) assert.equal(home.deadline({due},now),null);
});
test('future deadline uses Korean calendar days',()=>assert.equal(home.deadline({due:'2026-10-30T00:00:00+09:00'},now).big,'D-1'));
test('future start date is upcoming',()=>assert.equal(home.deadline({due:'2026-11-09',startDate:'2026-10-30'},now).cls,'upcoming'));
test('date-only start uses KST calendar, not UTC midnight',()=>assert.notEqual(home.deadline({due:'2026-11-09',startDate:'2026-10-29'},new Date('2026-10-28T16:00:00Z')).cls,'upcoming'));
test('explicit future start time is respected',()=>assert.equal(home.deadline({due:'2026-11-09',start:'2026-10-29T23:00:00+09:00'},now).cls,'upcoming'));
test('civil service employment takes precedence over public source',()=>assert.equal(home.sector({type:'j',alio:true,title:'공무직 채용'}),'service'));
test('public sector requires an explicit source classification',()=>{
  assert.equal(home.sector({type:'j',alio:true}),'public');
  assert.equal(home.sector({type:'j',org:'서울 기관',title:'일반 채용'}),'other');
});
test('unknown enterprise group is not advertised as a large company',()=>assert.equal(home.sector({type:'j',enterprise:true,group:'기타'}),'other'));
test('known enterprise group is categorized separately',()=>assert.equal(home.sector({type:'j',enterprise:true,group:'삼성'}),'enterprise'));
test('career is based on structured fields, never a preference mention',()=>{
  assert.deepEqual(home.career({career:'신입+경력',desc:'여성 경력단절 우대'}),['신입','경력']);
  assert.deepEqual(home.career({title:'경력 우대',text:'신입 가능'}),[]);
});
test('nonregular never matches regular by substring',()=>assert.deepEqual(home.employment({emp:['비정규직']}),['비정규직']));
test('employment normalizes existing contracts',()=>assert.deepEqual(home.employment({emp:['계약직','무기계약직','인턴','경력']}),['비정규직','무기계약직','인턴']));
test('sector employment and career are intersected',()=>{
  const p={type:'j',alio:true,emp:['정규직'],career:'경력'};
  assert(home.matches(p,{sector:'public',employment:'정규직',career:'경력'}));
  assert(!home.matches(p,{sector:'public',employment:'인턴',career:'경력'}));
  assert(!home.matches(p,{sector:'service'}));
});
test('empty enterprise feed yields no invented jobs',()=>assert.equal([].map(home.enterprise).length,0));
test('malformed enterprise links are excluded',()=>assert.equal(home.enterprise({id:'x',company:'A',title:'B',url:'javascript:alert(1)'}),null));
test('enterprise adapter retains source identity and unknown metadata',()=>{
  const p=home.enterprise({id:'saramin:1',company:'삼성',group:'삼성',title:'채용',url:'https://www.saramin.co.kr/jobs/1',deadline:'2099-12-31T18:00:00+09:00',status:'verified'});
  assert.equal(p.id,'saramin:1');assert.equal(p.due.getUTCFullYear(),2099);assert.deepEqual(p.emp,[]);
});
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
test('all inline scripts parse independently',()=>{
  for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) if(match[1].trim()) new vm.Script(match[1]);
});
test('retains canonical PWA core hooks and policy links',()=>{
  for(const text of ['https://kllollain-max.github.io/','manifest.webmanifest','sw.js','push-config.js','id="careerDashboard"','id="cpMobilePush"','id="cpBackupInput"','privacy.html','id="sheet"','id="jobview"']) assert(html.includes(text),text);
});
test('cards precede optional dashboard and exploration',()=>{
  assert(html.indexOf('id="list"')<html.indexOf('id="careerDashboard"'));
  assert(html.indexOf('id="cpSectors"')<html.indexOf('id="q"'));
});
test('search additions do not inject non-job content into all jobs',()=>assert(html.includes('CP_BLOG_SEARCH.filter(p => p.type === "j" && !p.due')));
test('existing storage names are preserved',()=>{
  for(const key of ['saved','apps','prefs','spec']) assert(new RegExp('(?:getItem|setItem)\\("'+key+'"').test(html),key);
});
test('shared organization homepages do not collapse distinct official notices',()=>{
  const one={id:'a1',alio:true,url:'https://job.alio.go.kr/recruitview.do?idx=1',src:'https://company.example/'};
  const two={...one,id:'a2',url:'https://job.alio.go.kr/recruitview.do?idx=2'};
  assert.notEqual(home.identity(one),home.identity(two));
  assert.equal(home.noticeKey({alioUrl:one.url}),'1');
  assert.equal(home.noticeKey({org:'same company',due:'same day'}),'');
});
test('malformed feed schema fails rather than claiming an empty healthy feed',()=>{
  for(const data of [null,{}, {posts:{}}])assert.throws(()=>home.parseFeed(data));
  assert.deepEqual(home.parseFeed({posts:[]}).rows,[]);
});
test('bad rows are isolated; malformed deadlines never become open',()=>{
  const parsed=home.parseFeed({posts:[null,{id:'x',title:'valid',pub:'bad',due:'bad',emp:{}}]});
  assert.equal(parsed.rows.length,1);assert.equal(parsed.rows[0].due,null);
  assert(parsed.issues.includes('invalid_row'));assert(parsed.issues.includes('invalid_deadline'));
  assert(parsed.issues.includes('invalid_metadata'));assert.deepEqual(parsed.rows[0].emp,[]);
});
test('date-only inputs cannot acquire an exact cutoff even with a bad flag',()=>{
  const parsed=home.parseFeed({posts:[{id:'x',title:'valid',pub:'2026-10-20',due:'2026-10-29',dueHasTime:true}]});
  assert.equal(parsed.rows[0].dueHasTime,false);
  assert.equal(home.deadline(parsed.rows[0],now).cls,'verify');
  assert.equal(home.deadline({due:'2026-10-29',dueHasTime:true},now).cls,'verify');
  assert.equal(home.deadline({due:'2026-02-31'},now),null);
});
test('healthy and legitimately empty sources need no banner',()=>{
  assert.deepEqual(home.healthNotices({posts:'ok',enterprise:'empty'},{posts:now},{},now),[]);
});
test('source failures staleness and corrupt rows have distinct visible notices',()=>{
  const n=home.healthNotices({posts:'error',alio:'ok',monitor:'ok'},{alio:'2026-10-20',monitor:now},{monitor:['invalid_row']},now);
  assert.equal(n.length,3);assert(n.some(x=>x.includes('잡알리오')&&x.includes('48시간')));
});
test('invalid and future update stamps do not imply freshness',()=>{
  for(const stamp of ['bad','2026-11-01'])assert.equal(home.healthNotices({alio:'ok'},{alio:stamp},{},now).length,1);
});
test('sector employment career Cartesian combinations intersect all constraints',()=>{
  const p={type:'j',alio:true,emp:['정규직'],career:'신입+경력'};
  let count=0;
  for(const sector of ['', 'public','service','enterprise','other'])
    for(const employment of ['', '정규직','무기계약직','비정규직','인턴'])
      for(const career of ['', '신입','경력']){
        assert.equal(home.matches(p,{sector,employment,career}),['','public'].includes(sector)&&['','정규직'].includes(employment));count++;
      }
  assert.equal(count,75);
});
test('all official work regions reach filtering, without inventing nationwide coverage',()=>{
  const result=home.detailFields({id:'a306304',alio:true},{recrutPblntSn:'306304',workRgnNmLst:'인천,충남,전북',recrutSeNm:'신입+경력',pbancBgngYmd:'20261026'});
  assert.equal(result.region,'인천,충남,전북');assert.equal(result.startDate,'2026-10-26');
  assert.deepEqual(home.detailFields({id:'a1',alio:true},{recrutPblntSn:'2',workRgnNmLst:'서울'}),{});
});


test('offline service worker always returns a Response for an uncached resource',async()=>{
  const handlers={};let promise;
  const context={self:{addEventListener:(name,fn)=>handlers[name]=fn},URL,Response,location:{origin:'https://kllollain-max.github.io'},caches:{match:async()=>undefined,open:async()=>({match:async()=>undefined})},fetch:async()=>{throw Error('offline');}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../sw.js'),'utf8'),context);
  handlers.fetch({request:{url:'https://kllollain-max.github.io/alio.json?t=1',method:'GET'},respondWith:p=>promise=p});
  const missing=await promise;assert.equal(missing.status,503);assert.match(await missing.text(),/오프라인/);
  context.caches.open=async()=>({match:async()=>new Response('cached')});
  handlers.fetch({request:{url:'https://kllollain-max.github.io/alio.json?t=2',method:'GET'},respondWith:p=>promise=p});
  assert.equal(await (await promise).text(),'cached');
});

test('unverified institution history never enters active homepage feed',()=>{
  const base={id:'m1',title:'채용',monitor:true,pub:'2026-03-16',due:null};
  assert.equal(home.parseFeed({posts:[base]}).rows.length,0);
  assert.equal(home.parseFeed({posts:[{...base,due:'2099-12-31',verificationStatus:'verification_pending'}]}).rows.length,0);
  assert.equal(home.parseFeed({posts:[{...base,due:'2099-12-31',verificationStatus:'verified'}]}).rows.length,1);
});
test('work24 adapter rejects missing dates, invalid links and unverified records',()=>{
  const row={id:'A',title:'채용',company:'기업',url:'https://www.work24.go.kr/job',deadline:'2099-12-31',status:'verified'};
  assert.equal(home.work24(row).id,'work24:A');
  assert.equal(home.work24({...row,status:'pending'}),null);
  assert.equal(home.work24({...row,deadline:null}),null);
  assert.equal(home.work24({...row,url:'https://evil.example/job'}),null);
  assert.equal(home.enterprise({...row,status:'확인 필요'}),null);
});

// Execute the shipped loader with local fixture responses; no provider requests.
async function work24PolicyCase(policy, receipt, data){
  const source=fs.readFileSync(require.resolve('../homepage-ui.js'),'utf8');
  const start=source.indexOf('async function cpLoadWork24(){');
  const code=source.slice(start,source.indexOf('\nfunction cpRenderHomeFilters',start));
  const existing=[{id:'alio-fixture',alio:true},{id:'institution-fixture',monitor:true}];
  const calls=[];
  const context={DATA_HEALTH:{alio:'ok',monitor:'ok'},CP_FEED_STAMPS:{alio:new Date().toISOString(),monitor:new Date().toISOString()},POSTS:existing.slice(),CPHome:home,
    fetch:async(url,options)=>{
      const path=url.split('?')[0];calls.push(path);
      assert(!/^https?:/.test(url),'no provider request');
      assert.equal(options.cache,'no-store');
      const value={'work24-policy.json':policy,'work24-status.json':receipt,'work24.json':data}[path];
      return{ok:value!==undefined,json:async()=>{if(value instanceof Error)throw value;return value;}};
    }};
  await vm.runInNewContext(code+'\ncpLoadWork24()',context);
  assert.deepEqual(context.POSTS.slice(0,2),existing,'ALIO and institution rows preserved');
  assert.equal(context.DATA_HEALTH.alio,'ok');assert.equal(context.DATA_HEALTH.monitor,'ok');
  return{context,calls,notices:home.healthNotices(context.DATA_HEALTH,context.CP_FEED_STAMPS,{},new Date())};
}
function work24PolicyFixture(){
  const stamp=new Date().toISOString();
  return{receipt:{state:'ok',api_ok:true,last_success_at:stamp,snapshot_updated_at:'fixture',counts:{stored:1}},
    data:{updated_at:'fixture',count:1,posts:[{id:'fixture',company:'기업',title:'공고',status:'verified',deadline:'2099-12-31',url:'https://www.work24.go.kr/job'}]}};
}
test('Work24 policy false without receipt is approval waiting without source requests',async()=>{
  const r=await work24PolicyCase({approved:false});
  assert.equal(r.context.DATA_HEALTH.work24,'awaiting_approval');
  assert.deepEqual(r.calls,['work24-policy.json']);assert.equal(r.context.POSTS.length,2);
  assert.deepEqual(r.notices,['고용24 채용정보는 현재 API 이용 승인 대기 중입니다.']);
});
test('Work24 policy false takes precedence over an old successful receipt and feed',async()=>{
  const f=work24PolicyFixture();const r=await work24PolicyCase({approved:false},f.receipt,f.data);
  assert.equal(r.context.DATA_HEALTH.work24,'awaiting_approval');
  assert.deepEqual(r.calls,['work24-policy.json']);assert.equal(r.context.POSTS.length,2);
});
test('Work24 policy true without receipt remains a collection error',async()=>{
  const r=await work24PolicyCase({approved:true});
  assert.equal(r.context.DATA_HEALTH.work24,'error');assert.equal(r.context.POSTS.length,2);
  assert.deepEqual(r.calls,['work24-policy.json','work24-status.json']);
  assert.deepEqual(r.notices,['고용24 채용정보를 불러오지 못했습니다.']);
});
test('Work24 policy true retains validated successful feed behavior',async()=>{
  const f=work24PolicyFixture();const r=await work24PolicyCase({approved:true},f.receipt,f.data);
  assert.equal(r.context.DATA_HEALTH.work24,'ok');assert.equal(r.context.POSTS.length,3);
  assert.equal(r.context.POSTS[2].id,'work24:fixture');assert.deepEqual(r.notices,[]);
});
test('Work24 policy true rejects corrupt stale or inconsistent receipts and feeds',async()=>{
  const f=work24PolicyFixture();
  for(const [receipt,data] of [[new Error('invalid json'),f.data],[{},f.data],
    [{...f.receipt,api_ok:false},f.data],[{...f.receipt,last_success_at:'2000-01-01'},f.data],
    [{...f.receipt,counts:{stored:2}},f.data],[f.receipt,{...f.data,count:2}],
    [f.receipt,{...f.data,updated_at:'other'}]]){
    const r=await work24PolicyCase({approved:true},receipt,data);
    assert.equal(r.context.DATA_HEALTH.work24,'error');assert.equal(r.context.POSTS.length,2);
  }
});
test('Work24 policy missing damaged or nonboolean is a configuration error',async()=>{
  for(const policy of [undefined,new Error('invalid json'),null,[],{}, {approved:'false'},{approved:0}]){
    const r=await work24PolicyCase(policy);
    assert.equal(r.context.DATA_HEALTH.work24,'config_error');assert.equal(r.context.POSTS.length,2);
    assert.deepEqual(r.calls,['work24-policy.json']);
    assert.deepEqual(r.notices,['고용24 채용정보 설정을 확인하지 못했습니다.']);
  }
});

const noticeFixture=JSON.parse(fs.readFileSync(require.resolve('./fixtures/notice-display-20261030.json'),'utf8'));
const displayNow=new Date('2026-10-30T09:00:00Z');
function displayRows(){return home.parseFeed(noticeFixture,'posts',displayNow).rows;}
test('notice display: two reviewed pairs collapse without mutating raw IDs or history',()=>{
  const input=displayRows(),before=JSON.stringify(input),r=home.unifyNotices(input);
  assert.equal(r.before,4);assert.equal(r.after,2);assert.equal(r.crossSourceRemoved,2);assert.deepEqual(r.pending,[]);
  assert.equal(JSON.stringify(input),before);
  for(const p of r.rows){
    assert(p.alio);assert.equal(p.sourceIds.length,2);assert.equal(p.sourceRecords.length,2);
    assert.equal(p.sourceRecords[0].id,p.id);assert(p.sourceRecords[1].last_checked_at);
    for(const raw of p.sourceRecords)assert(p.officialSources.some(s=>s.url===raw.url));
    assert.equal(p.sourceRecords[1].first_seen_at,input.find(x=>x.id===p.sourceIds[1]).first_seen_at);
    assert.equal(p.start,'2026-10-26');
  }
  assert.deepEqual(home.unifyNotices(r.rows).rows,r.rows);
});
test('notice display: similarities or changed rounds/jobs/counts/links/dates never prove identity',()=>{
  for(const change of [{id:'a999999'},{title:'다른 회차 채용 공고'},{n:'8'},
    {due:new Date('2026-11-03T23:59:00+09:00')},{url:'https://wrong.example/?idx=305872'}]){
    const rows=displayRows().filter(p=>['a305872','m7110dd3748cabc2b'].includes(p.id));
    Object.assign(rows[0],change);assert.equal(home.unifyNotices(rows).after,2);
  }
  const rows=displayRows().filter(p=>['a305872','m7110dd3748cabc2b'].includes(p.id));
  rows[1].officialNoticeNumber='2026-99';const r=home.unifyNotices(rows);
  assert.equal(r.after,2);assert.equal(r.pending.length,1);assert(r.rows.every(p=>p.identityVerification==='verification_pending'));
  assert.equal(home.unifyNotices([{id:'x',title:'같음',org:'기관',due:'2026-11-02',url:'https://example.com/1'},
    {id:'y',title:'같음',org:'기관',due:'2026-11-02',url:'https://example.com/2'}]).after,2);
});
test('notice display: real six institution notices are four expired and two open without false warning',()=>{
  const data={posts:noticeFixture.posts.filter(p=>p.monitor)},p=home.parseFeed(data,'posts',displayNow);
  assert.equal(p.rows.length,2);assert.deepEqual(p.states,{expired:4,verified_open:2});assert.deepEqual(p.issues,[]);
  assert.deepEqual(home.healthNotices({monitor:'ok'},{monitor:displayNow},{monitor:p.issues},displayNow),[]);
  const closed=home.parseFeed(data,'posts',new Date('2026-11-03T00:00:00+09:00'));
  assert.equal(closed.rows.length,0);assert.equal(closed.states.expired,6);assert.deepEqual(closed.issues,[]);
});
test('notice display: five reception states produce distinct warnings',()=>{
  const base={id:'test',title:'채용',monitor:true,verificationStatus:'verified',pub:'2026-10-20',start:'2026-10-26',due:'2026-11-02'};
  for(const [changes,expected] of [[{},'verified_open'],[{verificationStatus:'verified_open'},'verified_open'],
    [{due:'2026-10-27',start:'2026-10-01'},'expired'],[{due:null},'verification_pending'],
    [{due:'2026-02-31'},'invalid_date'],[{due:'not-a-date'},'invalid_date'],[{due:'11/02/2026'},'invalid_date'],[{verificationStatus:'invalid_date'},'invalid_date'],
    [{sourceFetchOk:false},'source_error'],[{verificationStatus:'source_error'},'source_error'],
    [{verificationStatus:'cancelled'},'cancelled'],[{start:'2026-11-01'},'upcoming']]){
    const p={...base,...changes};assert.equal(home.receptionState(p,displayNow),expected);
    const parsed=home.parseFeed({posts:[p]},'posts',displayNow);assert.equal(parsed.rows.length,expected==='verified_open'?1:0);
    const notes=home.healthNotices({monitor:'ok'},{monitor:displayNow},{monitor:parsed.issues},displayNow);
    assert.equal(notes.some(n=>n.includes('접수기간 미확인')),expected==='verification_pending');
    if(expected==='invalid_date')assert(notes.some(n=>n.includes('날짜 형식')));
    if(expected==='source_error')assert(notes.some(n=>n.includes('원문 확인')));
  }
});
test('notice display: reception date is not overwritten by ALIO publication date',()=>{
  const p=home.unifyNotices(displayRows()).rows.find(p=>p.id==='a305872');
  assert.equal(home.detailFields(p,{recrutPblntSn:'305872',pbancBgngYmd:'20261012'}).startDate,'2026-10-26');
});
test('notice display: old saved and application IDs remain readable without storage migration',()=>{
  const saved=new Set(['m7110dd3748cabc2b']),apps={m7110dd3748cabc2b:{st:'plan',memo:'preserve'}};
  const c=vm.createContext({SAVED:saved,APPS:apps});
  for(const name of ['cpSavedId','cpApplicationId'])vm.runInContext(html.match(new RegExp('function '+name+'\\(p\\)\\{[^\\n]+'))[0],c);
  c.p=home.unifyNotices(displayRows()).rows.find(p=>p.id==='a305872');
  assert.equal(vm.runInContext('cpSavedId(p)',c),'m7110dd3748cabc2b');assert.equal(vm.runInContext('cpApplicationId(p)',c),'m7110dd3748cabc2b');
  assert.deepEqual([...saved],['m7110dd3748cabc2b']);assert.equal(apps.m7110dd3748cabc2b.memo,'preserve');
  assert(html.includes('x.sourceIds?.includes(id)'));
});
test('notice display: unified cards retain and escape both official source links',()=>{
  const c=vm.createContext({esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')});
  vm.runInContext(html.match(/function cpMergedSourceLinks\(p,\s*exclude=""\)\{[\s\S]*?\n\}/)[0],c);
  c.p=home.unifyNotices(displayRows()).rows[0];const links=vm.runInContext('cpMergedSourceLinks(p)',c);
  for(const s of c.p.officialSources)assert(links.includes(s.url));assert(links.includes('rel="noopener noreferrer"'));
  c.p={officialSources:[{url:'https://example.com/?a="<',label:'<script>'}]};assert(!vm.runInContext('cpMergedSourceLinks(p)',c).includes('<script>'));
});
