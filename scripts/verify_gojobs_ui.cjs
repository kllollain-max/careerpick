const assert=require('node:assert/strict'),fs=require('node:fs');const{chromium}=require('playwright');
const BASE=process.env.CP_TEST_BASE||'http://127.0.0.1:8000/careerpick/';
(async()=>{const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});const report=[];fs.mkdirSync('gojobs-browser-output',{recursive:true});
try{for(const width of[320,390,1440]){const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Asia/Seoul'}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(BASE+'?q='+encodeURIComponent('제주특별자치도의회 시간선택제임기제공무원(농업축산분야)'),{waitUntil:'networkidle'});await page.locator('[data-open="gojobs-306282"]').first().waitFor();assert((await page.locator('#list').innerText()).includes('나라일터'));
await page.locator('[data-save="gojobs-306282"]').click();await page.reload({waitUntil:'networkidle'});await page.getByRole('button',{name:'저장 공고',exact:true}).click();await page.locator('[data-save="gojobs-306282"][aria-pressed="true"]').waitFor();
await page.locator('[data-open="gojobs-306282"]').first().click();await page.locator('#jvBody h1').waitFor();assert((await page.locator('#jvBody').innerText()).includes('2026-10-30'));
assert(await page.locator('#jvBody a[href="https://www.gojobs.go.kr/apmView.do?empmnsn=306282"]').count()>0);
assert((await page.locator('#jvBody').innerText()).includes('나라일터'));
await page.screenshot({path:'gojobs-browser-output/detail-'+width+'.png',fullPage:true});
await page.reload({waitUntil:'networkidle'});await page.locator('#jvBody h1').waitFor();assert((await page.locator('#jvBody h1').innerText()).includes('농업축산'));
assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));assert.deepEqual(errors,[]);report.push({width,search:true,savedAfterReload:true,detailDirectReload:true,officialLink:true,overflow:false,pageErrors:0});await context.close();}
fs.writeFileSync('gojobs-browser-output/report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));}finally{await browser.close();}})().catch(e=>{console.error(e.message);process.exit(1)});
