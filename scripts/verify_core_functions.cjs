/* Isolated Chromium profiles; all push operations use a synthetic SDK, never a provider. */
const fs=require('node:fs'),assert=require('node:assert/strict'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright');
const BASE=process.env.CP_AUDIT_BASE||'http://127.0.0.1:8000/careerpick/';
const LIVE='https://kllollain-max.github.io/careerpick/';
const OUT='core-audit-output';fs.mkdirSync(OUT,{recursive:true});
const rows=[
 {id:'a900001',org:'춘천연구원',title:'춘천연구원 전산직 정규직 채용',region:'강원',emp:['정규직']},
 {id:'a900002',org:'서울시험기관',title:'서울시험기관 간호직 인턴 채용',region:'서울',emp:['인턴']},
 {id:'a900003',org:'과거기관',title:'마감된 사무직 공고',region:'경기',emp:['정규직'],due:'2020-01-01T23:59:00+09:00'}
].map(p=>({type:'j',alio:true,cat:'공공기관 공식 공고',url:'https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx='+p.id.slice(1),pub:'2026-11-01T00:00:00+09:00',due:'2099-12-31T23:59:00+09:00',edu:['학력무관'],n:'2',...p}));
const feed={updated:new Date().toISOString(),posts:rows};
const report={checked_at_kst:new Date().toLocaleString('sv-SE',{timeZone:'Asia/Seoul'}),browser:'Chromium desktop, isolated contexts; mobile viewport simulation',actual_devices:false,push_delivery:false,public:[],candidate:[]};
const sdk=`(()=>{const sub={optedIn:false,id:null,token:null,addEventListener(){},async optIn(){window.fakeOptIns=(window.fakeOptIns||0)+1;await new Promise(r=>setTimeout(r,120));sub.optedIn=true;sub.id='synthetic-subscription';sub.token='synthetic-token';},async optOut(){window.fakeOptOuts=(window.fakeOptOuts||0)+1;sub.optedIn=false;sub.id=null;sub.token=null;}};const api={init:async()=>{},User:{PushSubscription:sub,addTags:async()=>{},getTags:async()=>({}),removeTags:async()=>{}}};window.OneSignal=api;for(const callback of window.OneSignalDeferred||[])callback(api);window.OneSignalDeferred={push:callback=>callback(api)};})();`;
async function context(browser,{width=390,fixtures=true,seed={},deny=false,sdkFailFirst=false,slow=false,failFeeds=false}={}){
 const ctx=await browser.newContext({viewport:{width,height:900},locale:'ko-KR',timezoneId:'Asia/Seoul',serviceWorkers:'block'});
 let sdkLoads=0;
 await ctx.addInitScript(({seed,deny})=>{
  if(!sessionStorage.getItem('cp-audit-seeded')){for(const [k,v]of Object.entries(seed))localStorage.setItem(k,v);sessionStorage.setItem('cp-audit-seeded','1');}
  if(deny){const put=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(['saved','apps','prefs'].includes(k))throw new DOMException('synthetic quota','QuotaExceededError');return put.call(this,k,v);};}
 },{seed,deny});
 await ctx.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.hostname==='cdn.onesignal.com'){sdkLoads++;if(sdkFailFirst&&sdkLoads===1)return route.abort();return route.fulfill({contentType:'application/javascript',body:sdk});}
  const origin=new URL(fixtures?BASE:LIVE).origin;
  if(u.origin!==origin)return route.abort();
  if(!fixtures)return route.continue();
  const file=u.pathname.split('/').pop();
  if(slow&&file==='alio.json')await new Promise(r=>setTimeout(r,650));
  if(failFeeds&&['posts.json','alio.json','monitor.json','gojobs.json','enterprise_jobs.json'].includes(file))return route.fulfill({status:503,body:'synthetic failure'});
  const data={'posts.json':{updated:feed.updated,posts:[]},'alio.json':feed,'gojobs.json':{updated:feed.updated,posts:[]},'monitor.json':{updated:feed.updated,posts:[]},'enterprise_jobs.json':{updated_at:feed.updated,jobs:[]},'work24-policy.json':{approved:false},'alio-detail.json':{},'qnet.json':{rows:[]},'operations-status.json':{}};
  if(file in data)return route.fulfill({contentType:'application/json',body:JSON.stringify(data[file])});
  return route.continue();
 });
 return {ctx,sdkLoads:()=>sdkLoads};
}
async function ready(page,url=BASE){await page.goto(url,{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>document.querySelector('#cpSectors')?.textContent.match(/전체공고[1-9]/));await page.locator('#list [data-save]').first().waitFor();}
async function check(name,fn,bucket='candidate'){try{await fn();report[bucket].push({name,result:'pass'});}catch(e){report[bucket].push({name,result:'fail',error:String(e.message).slice(0,320)});if(bucket==='candidate')throw e;}finally{fs.writeFileSync(OUT+'/report.json',JSON.stringify(report,null,2));}}
async function searchAndBack(page){
 const q=page.getByRole('searchbox',{name:'검색',exact:true});
 for(const word of ['춘천연구원','전산직','정규직 채용']){await q.fill(word);assert.equal(await page.locator('#list .job').count(),1);}
 await q.fill('   춘천연구원   ');assert.equal(await page.locator('#list .job').count(),1);
 await q.fill('<>&@!없는검색');assert((await page.locator('#list').innerText()).includes('조건에 맞는'));
 await q.fill('');
 await q.dispatchEvent('compositionstart');await q.fill('춘천');
 assert.equal(await page.evaluate(()=>state.q),'');await q.dispatchEvent('compositionend');assert.equal(await page.evaluate(()=>state.q),'춘천');
 await q.fill('서울');await q.fill('춘천');assert.equal(await page.locator('#list .job').count(),1);
 await page.locator('#cpOrder').selectOption('new');await page.locator('#toggle').click();await page.locator('#cpRegion').selectOption('강원');await page.locator('#cpEmployment').selectOption('정규직');await page.locator('#status [data-status="open"]').click();
 if(await page.locator('#cpFilterDone').isVisible())await page.locator('#cpFilterDone').click();
 assert.equal(await page.locator('#list .job').count(),1);assert((await page.locator('#summary').innerText()).includes('1건'));
 await page.locator('#list [data-open="a900001"]').first().click();await page.locator('#jobview').waitFor({state:'visible'});
 await page.goBack();await page.locator('#jobview').waitFor({state:'hidden'});
 assert.deepEqual(await page.evaluate(()=>[state.q,state.region,state.employment,state.status,state.sort]),['춘천','강원','정규직','open','new']);
 await page.locator('#toggle').click();await page.locator('#cpFilterReset').click();if(await page.locator('#cpFilterDone').isVisible())await page.locator('#cpFilterDone').click();
 assert.equal(await q.inputValue(),'');assert.equal(await page.locator('#list .job').count(),2);
}
async function savedAndApps(page){
 await page.locator('#list [data-save="a900001"]').click();await page.waitForFunction(()=>JSON.parse(localStorage.getItem('saved')).includes('a900001'));
 await page.locator('#list [data-open="a900001"]').first().click();assert.equal(await page.locator('#jvBody [data-save="a900001"]').getAttribute('aria-pressed'),'true');
 await page.locator('#jvBody [data-save="a900001"]').click();await page.waitForFunction(()=>!JSON.parse(localStorage.getItem('saved')).includes('a900001'));
 await page.locator('#jvBody [data-save="a900001"]').click();
 await page.locator('#jvBody [data-track="a900001"]').click();await page.locator('#tMemo').waitFor();
 const memo='  메모\n<&>🙂 긴 기록 '.repeat(35);await page.locator('#tMemo').fill(memo);
 await page.locator('#tExam').fill('2099-11-10');await page.locator('#tItv').fill('2099-11-12');await page.locator('#tCkNew').fill('시험 체크');await page.locator('#tCkAdd').click();
 await page.locator('#tSave').click();await page.waitForFunction(()=>!!JSON.parse(localStorage.getItem('apps'))?.a900001);
 assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('apps')).a900001.memo),memo);
 await page.locator('#jvBack').click();await page.locator('#jobview').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'내 지원',exact:true}).click();assert((await page.locator('#list').innerText()).includes('시험 체크')||(await page.evaluate(()=>JSON.stringify(APPS))).includes('시험 체크'));
 await page.reload();await page.waitForFunction(()=>document.querySelector('#cpSectors')?.textContent.match(/전체공고[1-9]/));
 await page.getByRole('button',{name:'내 지원',exact:true}).click();await page.locator('#list button[data-track="a900001"]').last().click();
 assert.equal(await page.locator('#tMemo').inputValue(),memo);assert.equal(await page.locator('#tExam').inputValue(),'2099-11-10');
 await page.locator('[data-stpick="applied"]').click();await page.locator('#tSave').click();await page.locator('#sheet.open').waitFor({state:'hidden'});
 assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('apps')).a900001.st),'applied');
 await page.getByRole('button',{name:'저장 공고',exact:true}).click();await page.locator('#list [data-save="a900001"]').click();
 assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('apps')).a900001.memo),memo);
}
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 try{
  // The current public site is exercised with a completely new profile; no personal storage or real push.
  const live=await context(browser,{fixtures:false});const lp=await live.ctx.newPage();const liveErrors=[];lp.on('pageerror',e=>liveErrors.push(e.message));
  await check('current public search, modal, refresh and saved state',async()=>{
   await ready(lp,LIVE);const id=await lp.locator('#list [data-save]').first().getAttribute('data-save');
   await lp.locator(`#list [data-save="${id}"]`).first().click();await lp.reload();await ready(lp,LIVE);
   await lp.getByRole('button',{name:'저장 공고',exact:true}).click();assert.equal(await lp.locator(`#list [data-save="${id}"]`).first().getAttribute('aria-pressed'),'true');
   await lp.locator('#list [data-open]').first().click();await lp.locator('#jobview').waitFor({state:'visible'});await lp.goBack();await lp.locator('#jobview').waitFor({state:'hidden'});
   assert.deepEqual(liveErrors,[]);
  },'public');
  await check('public storage-denied save must not show successful saved state (baseline)',async()=>{
   await lp.getByRole('button',{name:'전체 공고',exact:true}).click();
   const id=await lp.locator('#list [data-save][aria-pressed="false"]').first().getAttribute('data-save');
   await lp.evaluate(()=>{const put=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k==='saved')throw Error('synthetic quota');return put.call(this,k,v);};});
   await lp.locator(`#list [data-save="${id}"]`).first().click();assert.equal(await lp.locator(`#list [data-save="${id}"]`).first().getAttribute('aria-pressed'),'false');
  },'public');await live.ctx.close();
  for(const width of [320,360,390,430,1440]){
   const x=await context(browser,{width});const page=await x.ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await check('search, IME, filters, history '+width,async()=>{await ready(page);await searchAndBack(page);});
   await check('saved, application status, memo, checklist, dates, reload '+width,async()=>{await savedAndApps(page);assert.deepEqual(errors,[]);});
   await check('layout and accessible controls '+width,async()=>{assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));await page.screenshot({path:`${OUT}/viewport-${width}.png`});});
   await x.ctx.close();
  }
  await check('quota failure preserves saved and application state and editor text',async()=>{
   const x=await context(browser,{deny:true,seed:{saved:'["a900002"]',apps:'{"a900002":{"st":"plan","memo":"old"}}'}}),p=await x.ctx.newPage();await ready(p);
   await p.locator('#list [data-save="a900001"]').click();await p.locator('#cpStorageNotice').waitFor({state:'visible'});assert.equal(await p.locator('#list [data-save="a900001"]').getAttribute('aria-pressed'),'false');
   await p.locator('#list [data-track="a900001"]').click();await p.locator('#tMemo').fill('unsaved text');await p.locator('#tSave').click();await p.locator('#cpStorageNotice').waitFor({state:'visible'});assert(await p.locator('#tMemo').isVisible());assert.equal(await p.locator('#tMemo').inputValue(),'unsaved text');assert.equal(await p.evaluate(()=>localStorage.getItem('apps')),'{"a900002":{"st":"plan","memo":"old"}}');await x.ctx.close();
  });
  await check('corrupt buckets remain byte-identical and do not crash homepage',async()=>{
   const seed={saved:'[broken',apps:'{"broken":null}',prefs:'{"emp":null}'},x=await context(browser,{seed}),p=await x.ctx.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));await ready(p);
   await p.locator('#list [data-save="a900001"]').click();await p.locator('#cpStorageNotice').waitFor({state:'visible'});assert.deepEqual(await p.evaluate(()=>Object.fromEntries(['saved','apps','prefs'].map(k=>[k,localStorage.getItem(k)]))),seed);assert.deepEqual(errors,[]);await x.ctx.close();
  });
  await check('unlinked and expired saved records remain visible; application memo survives removal from feed',async()=>{
   const x=await context(browser,{seed:{saved:'["missing-id","a900003"]',apps:'{"missing-id":{"st":"plan","title":"旧記録","memo":"preserved","ck":[]}}'}}),p=await x.ctx.newPage();await ready(p);await p.getByRole('button',{name:'저장 공고',exact:true}).click();assert((await p.locator('#list').innerText()).includes('missing-id'));assert((await p.locator('#list').innerText()).includes('마감된 사무직'));await p.getByRole('button',{name:'내 지원',exact:true}).click();assert((await p.locator('#list').innerText()).includes('preserved'));await x.ctx.close();
  });
  await check('two tabs sync and stale editor cannot overwrite newer notes; unrelated IDs merge',async()=>{
   const x=await context(browser),p=await x.ctx.newPage(),p2=await x.ctx.newPage();await ready(p);await ready(p2);
   await p.locator('#list [data-save="a900001"]').click();await p2.waitForFunction(()=>SAVED.has('a900001'));assert.equal(await p2.locator('#list [data-save="a900001"]').getAttribute('aria-pressed'),'true');
   await p.locator('#list [data-track="a900001"]').click();await p2.locator('#list [data-track="a900001"]').click();await p.locator('#tMemo').fill('first');await p.locator('#tSave').click();await p2.waitForFunction(()=>APPS.a900001?.memo==='first');await p2.locator('#tMemo').fill('stale second');await p2.locator('#tSave').click();await p2.locator('#cpStorageNotice').waitFor({state:'visible'});assert.equal(await p2.evaluate(()=>JSON.parse(localStorage.getItem('apps')).a900001.memo),'first');assert(await p2.locator('#tMemo').isVisible());await x.ctx.close();
  });
  await check('loading is separate from no results and failure exposes retry',async()=>{
   const x=await context(browser,{slow:true}),p=await x.ctx.newPage();await p.goto(BASE,{waitUntil:'domcontentloaded'});assert((await p.locator('#summary').innerText()).includes('불러오는'));await p.waitForFunction(()=>!CP_DATA_LOADING);await x.ctx.close();
   const y=await context(browser,{failFeeds:true}),q=await y.ctx.newPage();await q.goto(BASE);await q.locator('#cpRetryFeeds').waitFor();assert((await q.locator('#list').innerText()).includes('검색 결과 없음과 다릅니다'));await y.ctx.close();
  });
  await check('SDK reload retry, registration truth, duplicate opt-in, opt-out and clipboard fallback (synthetic)',async()=>{
   const x=await context(browser,{sdkFailFirst:true}),p=await x.ctx.newPage();await ready(p);await p.getByRole('button',{name:'알림 설정',exact:true}).click();await p.waitForFunction(()=>document.querySelector('#cpPushMessage')?.textContent.includes('실패'));
   await p.locator('#cpPushSubscribe').click();await p.waitForFunction(()=>cpPushSdkReady);await p.waitForFunction(()=>!cpPushAction);assert(x.sdkLoads()>=2);assert.equal(await p.evaluate(()=>fakeOptIns),1);assert(await p.locator('#cpPushUnsubscribe').isVisible());
   await p.evaluate(()=>{OneSignal.User.PushSubscription.token=null;cpRenderPushButtons();});assert(await p.locator('#cpPushSubscribe').isVisible());
   await p.evaluate(()=>{OneSignal.User.PushSubscription.optedIn=false;OneSignal.User.PushSubscription.id=null;});
   await p.locator('#cpPushSubscribe').evaluate(el=>{el.click();el.click();});await p.waitForFunction(()=>!cpPushAction);assert.equal(await p.evaluate(()=>fakeOptIns),2);
   await p.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('synthetic clipboard denial')}}});});await p.locator('#cpPushCopyId').click();await p.getByRole('textbox',{name:'직접 복사할 구독 ID'}).waitFor();
   await p.locator('#cpPushUnsubscribe').click();await p.waitForFunction(()=>!cpPushAction);assert.equal(await p.evaluate(()=>fakeOptOuts),1);assert(await p.locator('#cpPushSubscribe').isVisible());await x.ctx.close();
  });
  console.log(JSON.stringify({public:report.public,candidate_passed:report.candidate.length,actual_devices:false,actual_push:false}));
 }finally{fs.writeFileSync(OUT+'/report.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(String(e.message));process.exit(1)});
