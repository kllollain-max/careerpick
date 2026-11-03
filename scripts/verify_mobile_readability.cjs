/* Isolated Chromium profiles; all push operations use a synthetic SDK, never a provider. */
const fs=require('node:fs'),assert=require('node:assert/strict'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright');
const BASE=process.env.CP_AUDIT_BASE||'http://127.0.0.1:8000/careerpick/';
const LIVE='https://kllollain-max.github.io/careerpick/';
const OUT='mobile-readability-output';fs.mkdirSync(OUT,{recursive:true});
const rows=[
 {id:'a900001',org:'춘천지역공공의료인공지능연구개발지원기관',title:'2026년도 전산직 정규직 및 연구직 전문계약직 공개채용 — 응시자격과 제출서류를 반드시 확인하세요',region:'강원, 서울, 경기',emp:['정규직']},
 {id:'a900002',org:'서울시험기관',title:'간호직 채용 (모집인원·일정 미기재)',region:'서울',emp:['인턴'],n:null,due:null},
 {id:'a900003',org:'과거기관',title:'마감된 사무직 공고',region:'경기',emp:['정규직'],due:'2020-01-01T23:59:00+09:00'}
].map(p=>({type:'j',alio:true,cat:'공공기관 공식 공고',url:'https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx='+p.id.slice(1),pub:'2026-11-01T00:00:00+09:00',due:'2099-12-31T23:59:00+09:00',edu:['학력무관'],n:'2',...p}));
const feed={updated:new Date().toISOString(),posts:rows};
const report={checked_at_kst:new Date().toLocaleString('sv-SE',{timeZone:'Asia/Seoul'}),browser:'Chromium desktop, isolated contexts; mobile viewport simulation',actual_devices:false,push_delivery:false,public:[],candidate:[]};
const sdk=`(()=>{const sub={optedIn:false,id:null,token:null,addEventListener(){},async optIn(){window.fakeOptIns=(window.fakeOptIns||0)+1;await new Promise(r=>setTimeout(r,120));Object.defineProperty(Notification,'permission',{configurable:true,get:()=> 'granted'});sub.optedIn=true;sub.id='synthetic-subscription';sub.token='synthetic-token';},async optOut(){window.fakeOptOuts=(window.fakeOptOuts||0)+1;sub.optedIn=false;sub.id=null;sub.token=null;}};const api={init:async()=>{},User:{PushSubscription:sub,addTags:async()=>{},getTags:async()=>({}),removeTags:async()=>{}}};window.OneSignal=api;for(const callback of window.OneSignalDeferred||[])callback(api);window.OneSignalDeferred={push:callback=>callback(api)};})();`;
async function context(browser,{width=390,fixtures=true,seed={},deny=false,sdkFailFirst=false,slow=false,failFeeds=false}={}){
 const ctx=await browser.newContext({viewport:{width,height:900},locale:'ko-KR',timezoneId:'Asia/Seoul',serviceWorkers:'block'});ctx.setDefaultTimeout(7000);
 let sdkLoads=0;
 await ctx.addInitScript(({seed,deny})=>{
  if(!sessionStorage.getItem('cp-audit-seeded')){for(const [k,v]of Object.entries(seed))localStorage.setItem(k,v);sessionStorage.setItem('cp-audit-seeded','1');}
  if(deny){const put=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(['saved','apps','prefs'].includes(k))throw new DOMException('synthetic quota','QuotaExceededError');return put.call(this,k,v);};}
 },{seed,deny});
 await ctx.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.hostname==='cdn.onesignal.com'){sdkLoads++;if(sdkFailFirst&&sdkLoads===1)return route.abort();return route.fulfill({contentType:'application/javascript',body:sdk});}
  const origin=new URL(fixtures?BASE:LIVE).origin;
  if(u.origin!==origin && u.origin!=='http://127.0.0.1:8001')return route.abort();
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
async function check(name,fn,bucket='candidate'){try{await fn();report[bucket].push({name,result:'pass'});console.log('PASS '+bucket+' '+name);}catch(e){report[bucket].push({name,result:'fail',error:String(e.message).slice(0,320)});console.log('FAIL '+bucket+' '+name+' '+String(e.message).slice(0,320));}finally{fs.writeFileSync(OUT+'/report.json',JSON.stringify(report,null,2));}}

(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const result={checked_at_kst:report.checked_at_kst,environment:'Linux Chromium isolated contexts; viewport and root font 200% simulation',physical_devices:false,checks:[]};
 const save=()=>fs.writeFileSync(OUT+'/report.json',JSON.stringify(result,null,2));
 try{
 for(const width of [320,360,390,430,1440])for(const theme of ['light','dark'])for(const zoom of [1,2]){
  const x=await context(browser,{width}),p=await x.ctx.newPage();
  await ready(p);await p.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
  if(zoom===2)await p.addStyleTag({content:'html{font-size:200% !important}'});
  const label=`${width}-${theme}-${zoom}x`;
  try{
   assert.equal(await p.locator('.cp-restore-notice').count(),0);
   assert.equal(await p.getByText('커리어픽 복원 안내',{exact:true}).count(),0);
   assert(await p.locator('#list').innerText().then(t=>t.includes('접수중')&&t.includes('일정 미확인')));
   assert.equal(await p.locator('#list a button').count(),0);
   const geom=await p.evaluate(()=>({w:innerWidth,scroll:document.documentElement.scrollWidth,font:parseFloat(getComputedStyle(document.querySelector('.title')).fontSize)}));
   assert(geom.scroll<=geom.w+1,`horizontal overflow ${JSON.stringify(geom)}`);assert(geom.font>=19*zoom);
   for(const btn of await p.locator('#list .job .actions>*').all()){const box=await btn.boundingBox();assert(box.height>=44);}
   // Compare actual foreground/background pairs in both themes; text is at least 14px.
   const contrast=await p.evaluate(()=>{
    const rgb=c=>c.match(/[\d.]+/g).slice(0,3).map(Number),lum=a=>a.map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((v,n,i)=>v+n*[.2126,.7152,.0722][i],0);
    return ['.title','.org','.cp-card-conditions','.due','.tag','#cpSectors button[aria-pressed=true]'].map(sel=>{const e=document.querySelector(sel),s=getComputedStyle(e);let a=e,b;while(a){b=getComputedStyle(a).backgroundColor;if(!b.endsWith(', 0)')&&b!=='transparent')break;a=a.parentElement;}const l=[lum(rgb(s.color)),lum(rgb(b))].sort((a,b)=>b-a);return {sel,ratio:(l[0]+.05)/(l[1]+.05)};});
   });
   for(const c of contrast)assert(c.ratio>=4.5,`${c.sel} contrast ${c.ratio}`);
   if(width===390&&zoom===1){
    await p.screenshot({path:`${OUT}/after-${label}.png`,fullPage:true});
    await p.locator('#toggle').click();await p.screenshot({path:`${OUT}/filter-${theme}.png`});await p.locator('#cpFilterDone').click();
    await p.locator('#list [data-open="a900001"]').first().click();await p.locator('#jobview').waitFor({state:'visible'});
    assert.equal(await p.locator('.jv-title').innerText(),rows[0].title);
    await p.screenshot({path:`${OUT}/detail-${theme}.png`,fullPage:true});await p.goBack();
   }
   if(width===320&&zoom===2)await p.screenshot({path:`${OUT}/after-${label}.png`,fullPage:true});
   result.checks.push({label,status:'pass',contrast});
  }catch(e){result.checks.push({label,status:'fail',error:e.message});await p.screenshot({path:`${OUT}/failure-${label}.png`,fullPage:true});}
  await x.ctx.close();save();
 }
 // Same synthetic posts, settings, dimensions and theme against the pre-change commit.
 for(const theme of ['light','dark']){
  const x=await context(browser,{width:390}),p=await x.ctx.newPage();await ready(p,'http://127.0.0.1:8001/careerpick/');await p.evaluate(t=>document.documentElement.dataset.theme=t,theme);await p.screenshot({path:`${OUT}/before-390-${theme}-1x.png`,fullPage:true});await x.ctx.close();
 }
 if(result.checks.some(x=>x.status==='fail'))process.exitCode=1;
 console.log(JSON.stringify(result));
 }finally{save();await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
