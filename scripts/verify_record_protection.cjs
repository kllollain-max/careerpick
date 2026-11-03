/* Private-record E2E: synthetic records only; downloaded backups stay in runner temp. */
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const BASE='http://127.0.0.1:8000/careerpick/',OUT='record-protection-output';fs.mkdirSync(OUT,{recursive:true});
const report={checked_at_kst:new Date().toLocaleString('sv-SE',{timeZone:'Asia/Seoul'}),environment:'isolated Chromium; synthetic local records only',actual_user_records:false,actual_old_origin_backup:false,backup_files_uploaded:false,checks:[]};
async function check(name,fn){try{await fn();report.checks.push({name,result:'pass'});console.log('PASS records '+name);}catch(e){report.checks.push({name,result:'fail',error:String(e.message).slice(0,180)});console.log('FAIL records '+name+' '+String(e.message).slice(0,180));}finally{fs.writeFileSync(OUT+'/report.json',JSON.stringify(report,null,2));}}
async function fresh(browser,{seed={},width=390,sw=false,denyReads=false}={}){
 const ctx=await browser.newContext({viewport:{width,height:900},timezoneId:'Asia/Seoul',locale:'ko-KR',serviceWorkers:sw?'allow':'block',acceptDownloads:true});ctx.setDefaultTimeout(10000);
 await ctx.addInitScript(({seed,denyReads})=>{if(!sessionStorage.getItem('record-e2e-seeded')){for(const[k,v]of Object.entries(seed))localStorage.setItem(k,v);sessionStorage.setItem('record-e2e-seeded','1');}if(denyReads){const get=Storage.prototype.getItem;Storage.prototype.getItem=function(k){if(this===localStorage&&k==='apps')throw Error('synthetic denied read');return get.call(this,k);};}},{seed,denyReads});
 await ctx.route('**/*',route=>new URL(route.request().url()).origin===new URL(BASE).origin?route.continue():route.abort());
 const p=await ctx.newPage();p.on('pageerror',e=>console.log('record pageerror '+e.message));p.setDefaultTimeout(10000);await p.goto(BASE);await p.waitForFunction(()=>!CP_DATA_LOADING);return{ctx,p};
}
async function records(p){return p.evaluate(()=>Object.fromEntries(CPRecords.keys.map(k=>[k,localStorage.getItem(k)])));}
async function download(p){const event=p.waitForEvent('download');await p.getByRole('button',{name:'개인 기록 백업(JSON)',exact:true}).click();const d=await event,file=await d.path();assert(file&&fs.statSync(file).size>0);const data=JSON.parse(fs.readFileSync(file,'utf8'));return{data,file,name:d.suggestedFilename()};}
async function importFile(p,file,{accept=true,expectedAlert=true}={}){
 let preview='',alert='',navigation=null,resolveConfirm,resolveAlert;const confirmed=new Promise(r=>resolveConfirm=r),alerted=new Promise(r=>resolveAlert=r);
 const handler=async dialog=>{if(dialog.type()==='confirm'){preview=dialog.message();accept?await dialog.accept():await dialog.dismiss();resolveConfirm();}else{alert=dialog.message();if(alert.includes('병합 완료')||alert.includes('새로고침'))navigation=p.waitForNavigation({waitUntil:'domcontentloaded',timeout:10000});await dialog.accept();resolveAlert();}};
 p.on('dialog',handler);
 try{await p.locator('#cpBackupInput').setInputFiles(file);if(expectedAlert){await Promise.race([alerted,new Promise((_,reject)=>setTimeout(()=>reject(Error('import result alert missing')),12000))]);if(navigation){await navigation;await p.waitForFunction(()=>!CP_DATA_LOADING);}}else await confirmed;
 }finally{p.off('dialog',handler);}
 return{preview,alert};
}
function upload(data,name='synthetic-backup.json'){return{name,mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))};}
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 try{
  for(const width of [360,1440])await check('create/edit/download/new-profile/import/reimport/conflict '+width,async()=>{
   const x=await fresh(browser,{width}),p=x.p;const id=await p.locator('#list [data-save]').first().getAttribute('data-save');
   await p.locator(`#list [data-save="${id}"]`).first().click();await p.waitForFunction(id=>SAVED.has(id),id);
   await p.locator(`#list [data-track="${id}"]`).first().click();await p.locator('#tMemo').fill('first synthetic memo');await p.locator('#tSave').click();await p.locator('#sheet.open').waitFor({state:'hidden'});
   await p.locator(`#list [data-track="${id}"]`).first().click();
   const memo='합성 개인 기록 🙂\n<&> 한글 줄바꿈 메모 '.repeat(40);
   await p.locator('#tMemo').fill(memo);await p.locator('#tExam').fill('2099-11-10');await p.locator('#tItv').fill('2099-11-12');await p.locator('#tCkNew').fill('합성 항목 <&>🙂');await p.locator('#tCkAdd').click();await p.locator('[data-stpick="doc"]').click();await p.locator('#tSave').click();await p.locator('#sheet.open').waitFor({state:'hidden'});
   await p.getByRole('button',{name:'알림 설정',exact:true}).click();await p.locator('[data-pref="region"][data-val="강원"]').click();await p.locator('#prefKw').fill('합성 전산,간호');await p.locator('#prefSave').click();await p.locator('#sheet.open').waitFor({state:'hidden'});
   await p.getByRole('button',{name:'전체 공고',exact:true}).click();await p.locator('#openSpec').first().click();await p.locator('#specEtc').fill('합성 자격🙂');await p.locator('[data-specone="edu"]').first().click();await p.locator('#specSave').click();await p.locator('#sheet.open').waitFor({state:'hidden'});
   await p.evaluate(()=>{localStorage.setItem('onesignal-sdk','{"token":"excluded-sdk-token"}');localStorage.setItem('ALIO_KEY','excluded-api-key');});
   const before=await records(p),d=await download(p);assert(/^careerpick-backup-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_KST\.json$/.test(d.name));assert.equal(d.data.format,'careerpick-backup');assert.equal(d.data.version,1);assert.equal(d.data.service.id,'careerpick');assert(Number.isFinite(Date.parse(d.data.exported_at)));assert.equal(d.data.data.apps[id].memo,memo);assert.equal(d.data.counts.apps,Object.keys(d.data.data.apps).length);assert.equal(d.data.counts.saved,d.data.data.saved.length);const text=JSON.stringify(d.data);assert(!text.includes('excluded-sdk-token'));assert(!text.includes('excluded-api-key'));
   const y=await fresh(browser,{width}),q=y.p,empty=await records(q);let result=await importFile(q,d.file,{accept:false,expectedAlert:false});assert(result.preview.includes('형식 버전 1'));assert(result.preview.includes('신규: 저장 1 · 지원 1'));assert(result.preview.includes('가져올 수 없는 항목 0'));assert.deepEqual(await records(q),empty);
   result=await importFile(q,d.file);assert(result.alert.includes('병합 완료'));for(const k of ['saved','apps','prefs','spec'])assert.deepEqual(JSON.parse((await records(q))[k]),JSON.parse(before[k]));
   const once=await records(q);result=await importFile(q,d.file);assert(result.preview.includes('중복: 저장 1 · 지원 1'));assert.deepEqual(await records(q),once);
   const incoming=JSON.parse(JSON.stringify(d.data));incoming.data.apps[id].memo='CONFLICT <img src=x onerror="window.unwanted=1">';incoming.data.apps[id].st='plan';incoming.exported_at='2020-01-01T00:00:00Z';result=await importFile(q,upload(incoming));assert(result.preview.includes('충돌 1'));assert.equal(await q.evaluate(id=>APPS[id].memo,id),memo);
   await q.getByRole('button',{name:'충돌·복구 사본 확인',exact:true}).click();assert((await q.locator('#cpArchiveText').innerText()).includes('CONFLICT <img'));assert.equal(await q.locator('#cpArchiveText img').count(),0);assert.equal(await q.evaluate(()=>window.unwanted),undefined);await q.getByRole('button',{name:'창 닫기',exact:true}).click();
   // A new tab must read the same independent saved/application records.
   const tab=await y.ctx.newPage();await tab.goto(BASE);await tab.waitForFunction(()=>!CP_DATA_LOADING);assert.equal(await tab.evaluate(id=>APPS[id].memo,id),memo);await tab.bringToFront();await q.bringToFront();assert.equal(await q.evaluate(id=>APPS[id].memo,id),memo);
   await x.ctx.close();await y.ctx.close();
  });
  await check('empty records export is a valid downloadable and restorable backup',async()=>{
   const x=await fresh(browser),d=await download(x.p);assert.equal(d.data.counts.saved,0);assert.equal(d.data.counts.apps,0);const y=await fresh(browser);const r=await importFile(y.p,d.file);assert(r.alert.includes('병합 완료'));assert.deepEqual(await y.p.evaluate(()=>[...SAVED]),[]);await x.ctx.close();await y.ctx.close();
  });
  await check('bad JSON, unsupported version and oversized file never mutate existing records',async()=>{
   const x=await fresh(browser,{seed:{saved:'["a999999"]',apps:'{"a999999":{"st":"plan","memo":"keep","ck":[]}}'}}),p=x.p,before=await records(p);
   for(const file of [{name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{bad')},upload({format:'careerpick-backup',version:99,data:{}}),{name:'oversized.json',mimeType:'application/json',buffer:Buffer.alloc(16*1024*1024+1,32)}]){const result=await importFile(p,file);assert(!result.alert.includes('완료'));assert.deepEqual(await records(p),before);}
   await x.ctx.close();
  });
  await check('storage access denial gives partial backup warning without fake complete restoration',async()=>{
   const x=await fresh(browser,{denyReads:true}),d=await download(x.p);assert(d.data.unavailable_keys.includes('apps'));const y=await fresh(browser),before=await records(y.p),result=await importFile(y.p,d.file);assert(result.alert.includes('부분 백업'));assert.deepEqual(await records(y.p),before);await x.ctx.close();await y.ctx.close();
  });
  await check('pending transaction stays visible after reload; explicit recovery restores exact prior data',async()=>{
   const original={saved:'["a999999"]',apps:'{"a999999":{"st":"plan","memo":"before","ck":[]}}'},raw=Object.fromEntries(['prefs','spec','saved','apps','careerpick-import-archive'].map(k=>[k,original[k]??null])),after={...raw,saved:'["a999999","a999998"]'};
   const seed={...original,saved:after.saved,'careerpick-before-import':JSON.stringify({format:'careerpick-before-import',version:1,state:'prepared',raw_records:raw,expected_after:after})};
   const x=await fresh(browser,{seed}),p=x.p;assert((await p.locator('#cpStorageNotice').innerText()).includes('미완료'));await p.reload();await p.waitForFunction(()=>!CP_DATA_LOADING);assert((await p.locator('#cpStorageNotice').innerText()).includes('미완료'));
   await p.getByRole('button',{name:'충돌·복구 사본 확인',exact:true}).click();let done,reload;const alert=new Promise(r=>done=r);const handler=async d=>{if(d.type()==='confirm')await d.accept();else{assert(d.message().includes('원상복구'));reload=p.waitForNavigation({waitUntil:'domcontentloaded',timeout:10000});await d.accept();done();}};p.on('dialog',handler);await p.getByRole('button',{name:'최근 가져오기 전으로 복구',exact:true}).click();await alert;await reload;p.off('dialog',handler);await p.waitForFunction(()=>!CP_DATA_LOADING);assert.deepEqual(await records(p),raw);await x.ctx.close();
  });
  await check('spec write denial preserves editor input and does not report saved',async()=>{
   const x=await fresh(browser),p=x.p;await p.locator('#openSpec').first().click();await p.locator('#specEtc').fill('unsaved synthetic license');await p.evaluate(()=>{const put=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k==='spec')throw Error('synthetic quota');return put.call(this,k,v);};});await p.locator('#specSave').click();await p.locator('#cpStorageNotice').waitFor({state:'visible'});assert(await p.locator('#specEtc').isVisible());assert.equal(await p.locator('#specEtc').inputValue(),'unsaved synthetic license');assert.equal(await p.evaluate(()=>localStorage.getItem('spec')),null);await x.ctx.close();
  });
  await check('two preference editors detect conflict and preserve the second unsaved input',async()=>{
   const x=await fresh(browser),p=x.p,q=await x.ctx.newPage();await q.goto(BASE);await q.waitForFunction(()=>!CP_DATA_LOADING);await p.getByRole('button',{name:'알림 설정',exact:true}).click();await q.getByRole('button',{name:'알림 설정',exact:true}).click();await p.locator('#prefKw').fill('first synthetic preference');await q.locator('#prefKw').fill('second unsaved preference');await p.locator('#prefSave').click();await p.locator('#sheet.open').waitFor({state:'hidden'});await q.waitForFunction(()=>PREFS.kw==='first synthetic preference');await q.locator('#prefSave').click();await q.locator('#cpStorageNotice').waitFor({state:'visible'});assert.equal(await q.locator('#prefKw').inputValue(),'second unsaved preference');assert.equal(await q.evaluate(()=>JSON.parse(localStorage.getItem('prefs')).kw),'first synthetic preference');await x.ctx.close();
  });
  await check('partial browser import write failure rolls back exact originals and retry is idempotent',async()=>{
   const x=await fresh(browser,{seed:{saved:' ["old-unlinked"] ',apps:'{"old-unlinked":{"st":"plan","memo":"old","ck":[]}}'}}),p=x.p,before=await records(p);
   await p.evaluate(()=>{const put=Storage.prototype.setItem;let once=false;Storage.prototype.setItem=function(k,v){if(k==='apps'&&!once){once=true;throw Error('synthetic mid-apply quota');}return put.call(this,k,v);};});
   const file=upload({format:'careerpick-backup',version:1,data:{saved:['new-unlinked'],apps:{'new-unlinked':{st:'applied',memo:'new',ck:[]}}}});let r=await importFile(p,file);assert(r.alert.includes('복구했습니다'));assert.deepEqual(await records(p),before);r=await importFile(p,file);assert(r.alert.includes('병합 완료'));const after=await records(p);await importFile(p,file);assert.deepEqual(await records(p),after);await x.ctx.close();
  });
  await check('legacy old-origin format is compatible, with unlinked IDs retained; actual migration unverified',async()=>{
   const legacy={format:'careerpick-backup',version:1,data:{saved:['a123456','legacy-unlinked'],apps:{a123456:{st:'applied',memo:'old-format 합성',ck:[{t:'제출',ph:'pre',d:1}],exam:'2099-12-01'}},prefs:{emp:['정규직'],edu:[],region:['강원'],cat:[],kw:''}}};const x=await fresh(browser);const r=await importFile(x.p,upload(legacy,'synthetic-old-origin.json'));assert(r.preview.includes('미제공 (과거 백업)'));assert(r.alert.includes('병합 완료'));assert.equal(await x.p.evaluate(()=>APPS.a123456.memo),'old-format 합성');assert(await x.p.evaluate(()=>SAVED.has('legacy-unlinked')));await x.ctx.close();
  });
  await check('site/service-worker update and cached offline reload preserve personal records',async()=>{
   const workerFile=path.resolve('dist/sw.js'),original=fs.readFileSync(workerFile,'utf8');let x;
   try{
    x=await fresh(browser,{sw:true,seed:{saved:'["a999999"]',apps:'{"a999999":{"st":"plan","memo":"SW-preserved","ck":[]}}'}});const p=x.p;await p.evaluate(()=>navigator.serviceWorker.ready);await p.waitForFunction(()=>!!navigator.serviceWorker.controller);const before=await records(p);
    fs.writeFileSync(workerFile,original+'\nself.addEventListener("message",e=>{if(e.data==="CP_RECORDS_AUDIT")e.source.postMessage("CP_RECORDS_AUDIT_V2");});\n');const mtime=new Date(Date.now()+3000);fs.utimesSync(workerFile,mtime,mtime);
    await p.evaluate(async()=>{navigator.serviceWorker.addEventListener('message',e=>{if(e.data==='CP_RECORDS_AUDIT_V2')window.__recordsWorkerV2=true;});const r=await navigator.serviceWorker.getRegistration();await r.update();});
    await p.waitForFunction(async()=>{navigator.serviceWorker.controller?.postMessage('CP_RECORDS_AUDIT');return window.__recordsWorkerV2===true;});
    console.log('SW audit online reload');await p.reload({waitUntil:'domcontentloaded'});await p.waitForFunction(()=>!CP_DATA_LOADING,null,{timeout:30000});assert.deepEqual(await records(p),before);console.log('SW audit offline reload');await x.ctx.setOffline(true);await p.reload({waitUntil:'domcontentloaded'});assert.deepEqual(await records(p),before);await p.waitForFunction(()=>!CP_DATA_LOADING,null,{timeout:30000}).catch(async e=>{console.log('offline diagnostics '+JSON.stringify(await p.evaluate(()=>({ready:document.readyState,loading:typeof CP_DATA_LOADING==='undefined'?'undefined':CP_DATA_LOADING,health:typeof DATA_HEALTH==='undefined'?null:DATA_HEALTH,home:typeof CPHome,records:typeof CPRecords,scripts:[...document.scripts].filter(s=>s.src).map(s=>s.src)}))));throw e;});assert.deepEqual(await records(p),before);
   }finally{fs.writeFileSync(workerFile,original);if(x)await x.ctx.close();}
  });
  if(report.checks.some(x=>x.result==='fail'))process.exitCode=1;
  console.log(JSON.stringify({record_scenarios:report.checks.length,passed:report.checks.filter(x=>x.result==='pass').length,actual_user_records:false,actual_old_origin_backup:false,backup_files_uploaded:false}));
 }finally{fs.writeFileSync(OUT+'/report.json',JSON.stringify(report,null,2));if(process.env.GITHUB_STEP_SUMMARY)fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,'```json\n'+JSON.stringify(report,null,2)+'\n```\n');await browser.close();}
})().catch(e=>{console.error(String(e.message));process.exit(1)});
