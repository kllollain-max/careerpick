const assert=require('node:assert/strict'),fs=require('node:fs');const{chromium}=require('playwright');
const BASE=process.env.CP_TEST_BASE||'http://127.0.0.1:8000/careerpick/';
(async()=>{const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});const report=[];fs.mkdirSync('gojobs-browser-output',{recursive:true});
try{for(const width of[320,390,1440]){const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Asia/Seoul'}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
const response=await fetch(BASE+'gojobs.json?check='+Date.now());
assert(response.ok,'Public GOJOBS feed unavailable');
const feed=await response.json();
const candidates=(feed.posts||[]).filter(p=>/^gojobs-[0-9]+$/.test(p.id||'')&&p.title&&p.due&&Date.parse(p.due)>Date.now()).sort((a,b)=>Date.parse(b.due)-Date.parse(a.due));
assert(candidates.length,'No currently open GOJOBS notices in public feed; check collection freshness');
let selected=null;
for(const candidate of candidates){
  await page.goto(BASE+'?q='+encodeURIComponent(candidate.title),{waitUntil:'networkidle'});
  if(await page.locator('[data-open="'+candidate.id+'"]').first().isVisible().catch(()=>false)){selected=candidate;break;}
}
if(!selected){
  const diag=await page.evaluate((candidateIds)=>({
    search:document.querySelector('#q')?.value,
    status:document.querySelector('#cpFeedStatus')?.innerText,
    list:document.querySelector('#list')?.innerText?.slice(0,1200),
    gojobsInPosts:typeof POSTS!=='undefined'?POSTS.filter(p=>p.gojobs).map(p=>({id:p.id,title:p.title,due:p.due instanceof Date?p.due.toISOString():p.due})).slice(0,15):null,
    matchingCandidates:typeof POSTS!=='undefined'?POSTS.filter(p=>p.gojobs&&p.title&&candidateIds.includes(p.id)).map(p=>p.id):null
  }),candidates.map(c=>c.id));
  fs.writeFileSync('gojobs-browser-output/missing-'+width+'.json',JSON.stringify({width,feedUpdated:feed.updated,candidates:candidates.map(p=>({id:p.id,title:p.title,due:p.due})),diag},null,2));
  await page.screenshot({path:'gojobs-browser-output/missing-'+width+'.png',fullPage:true});
}
assert(selected,'Open GOJOBS notices not visible in public search; see gojobs-browser-output/missing-'+width+'.json');
const id=selected.id;
assert((await page.locator('#list').innerText()).includes('나라일터'));
await page.locator('[data-save="'+id+'"]').first().click();
await page.reload({waitUntil:'networkidle'});
await page.getByRole('button',{name:'저장 공고',exact:true}).click();
await page.locator('[data-save="'+id+'"][aria-pressed="true"]').first().waitFor();
await page.locator('[data-open="'+id+'"]').first().click();
await page.locator('#jvBody h1').waitFor();
assert((await page.locator('#jvBody').innerText()).includes('나라일터'));
assert(await page.locator('#jvBody a[href^="https://www.gojobs.go.kr/"]').count()>0);
await page.screenshot({path:'gojobs-browser-output/detail-'+width+'.png',fullPage:true});
await page.reload({waitUntil:'networkidle'});
await page.locator('#jvBody h1').waitFor();
assert((await page.locator('#jvBody h1').innerText()).includes(selected.title));
assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));
await page.goto(BASE+'civil-service-exams.html',{waitUntil:'networkidle'});await page.locator('#results article').first().waitFor();assert.equal(await page.locator('#results article').count(),28);await page.getByRole('link',{name:'이 시험단계 상세 보기',exact:true}).first().click();await page.locator('#results article').first().waitFor();assert.equal(await page.locator('#results article').count(),1);await page.reload({waitUntil:'networkidle'});await page.locator('#results article').first().waitFor();assert.equal(await page.locator('#results article').count(),1);assert((await page.locator('#results').innerText()).includes('원서접수'));assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));
assert.deepEqual(errors,[]);report.push({width,search:true,savedAfterReload:true,detailDirectReload:true,examDetailReload:true,officialLink:true,overflow:false,pageErrors:0});await context.close();}
fs.writeFileSync('gojobs-browser-output/report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));}finally{await browser.close();}})().catch(e=>{console.error(e.message);process.exit(1)});
