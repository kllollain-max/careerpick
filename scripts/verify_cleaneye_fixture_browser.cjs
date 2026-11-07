/* Synthetic browser fixtures are routed in memory, never written to public data. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const repo=path.join(process.env.CLEANEYE_PREVIEW_ROOT || path.resolve(__dirname,'..'),'dist');
const out=path.resolve('cleaneye-fixture-validation');
const {chromium}=require('playwright');
fs.mkdirSync(out,{recursive:true});
const token='클린아이연동검증';
const base={type:'j',cleaneye:true,source:'클린아이 잡플러스',cat:'지방공공기관 채용',org:'테스트 지방공공기관',
  pub:null,start:'2026-11-01',due:'2099-12-31T23:59:59+09:00',dueHasTime:false,region:'강원 춘천',
  emp:['정규직'],edu:['학력무관'],n:'약 2명',text:'시설관리 직무',receptionState:'verified_open',
  cleaneyeDetail:{'고용형태':'정규직','학력':'무관','채용인원':'약 2명','지원 자격':'공식 원문 자격 안내를 확인하세요.','기타 안내':'&lt;img src=x onerror=alert(1)&gt;'}};
const fixtures=[
  {...base,id:'cleaneye-TEST_UI_1',title:token+' 정규직',url:'https://job.cleaneye.go.kr/fixture/notice?no=TEST_UI_1'},
  {...base,id:'cleaneye-TEST_UI_2',title:token+' 계약직',url:'https://www.job.cleaneye.go.kr/fixture/notice?no=TEST_UI_2',emp:['계약직'],cleaneyeDetail:{'고용형태':'계약직'}},
  {...base,id:'cleaneye-TEST_UI_3',title:token+' 일정 확인',url:'https://job.cleaneye.go.kr/fixture/notice?no=TEST_UI_3',emp:[],n:null,start:null,due:null,receptionState:'verification_pending',cleaneyeDetail:{'공고상태':'확인 필요'}},
];
const types={'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png','.webp':'image/webp','.webmanifest':'application/manifest+json'};
const server=http.createServer((req,res)=>{
  const pathname=new URL(req.url,'http://127.0.0.1').pathname;
  const relative=decodeURIComponent(pathname.replace(/^\/careerpick\//,''));
  let file=path.resolve(repo,relative||'index.html');
  if(!file.startsWith(repo+path.sep)){res.writeHead(404).end();return;}
  if(fs.existsSync(file)&&fs.statSync(file).isDirectory())file=path.join(file,'index.html');
  if(!fs.existsSync(file)){res.writeHead(404).end();return;}
  res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');
  res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const baseURL=`http://127.0.0.1:${server.address().port}/careerpick/`;
  const browser=await chromium.launch({...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {}),headless:true,args:['--no-sandbox']});
  const reports=[];
  try{
    for(const width of [320,390,1440]){
      const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Asia/Seoul',serviceWorkers:'block'});
      const page=await context.newPage();const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      let testFeed={source:'cleaneye',updated:new Date().toISOString(),collectionStatus:'verified',posts:fixtures};
      await context.route('**/*',route=>{
        const url=new URL(route.request().url());
        if(url.origin!==new URL(baseURL).origin)return route.abort();
        if(url.pathname.endsWith('/cleaneye.json'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(testFeed)});
        return route.continue();
      });
      await context.addInitScript(()=>{
        if(localStorage.getItem('cleaneye_test_seeded'))return;
        localStorage.setItem('saved',JSON.stringify(['gojobs-306282']));
        localStorage.setItem('apps',JSON.stringify({prior_record:{st:'plan',memo:'이전 메모 보존'}}));
        localStorage.setItem('prefs',JSON.stringify({emp:['정규직'],edu:[],region:['강원'],cat:[],kw:'클린아이연동검증'}));
        localStorage.setItem('cleaneye_test_seeded','1');
      });
      await page.goto(baseURL+'?q='+encodeURIComponent(token),{waitUntil:'networkidle'});
      await page.locator('#list [data-open="cleaneye-TEST_UI_1"]').first().waitFor();
      assert.equal(await page.locator('#list .card').count(),3);
      assert((await page.locator('#list').innerText()).includes('상태 확인'));
      assert(!(await page.locator('#list').innerText()).includes('약 2명명'));
      await page.locator('[data-sector="public"]').click();
      assert.equal(await page.locator('#list .card').count(),3);
      if(width<=700)await page.locator('#toggle').click();
      await page.locator('#cpEmployment').selectOption('정규직');
      assert.equal(await page.locator('#list .card').count(),1);
      assert(await page.locator('#list [data-open="cleaneye-TEST_UI_1"]').count()>0);
      await page.locator('#cpEmployment').selectOption('비정규직');
      assert.equal(await page.locator('#list .card').count(),1);
      assert(await page.locator('#list [data-open="cleaneye-TEST_UI_2"]').count()>0);
      await page.locator('#cpEmployment').selectOption('');
      if(width<=700)await page.locator('#cpFilterDone').click();
      await page.locator('#list [data-save="cleaneye-TEST_UI_1"]').click();
      await page.reload({waitUntil:'networkidle'});
      await page.locator('#list [data-save="cleaneye-TEST_UI_1"][aria-pressed="true"]').waitFor();
      const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('saved')));
      assert(saved.includes('gojobs-306282'));assert(saved.includes('cleaneye-TEST_UI_1'));
      await page.locator('[data-dash="saved"]:visible').first().click();
      await page.locator('#list [data-open="cleaneye-TEST_UI_1"]').first().waitFor();
      await page.locator('#list [data-open="cleaneye-TEST_UI_1"]').first().click();
      await page.locator('#jvBody h1').waitFor();
      assert((await page.locator('#jvBody').innerText()).includes('클린아이 잡플러스'));
      assert((await page.locator('#jvBody').innerText()).includes('공식 원문 자격 안내'));
      assert(await page.locator('#jvBody a[href="https://job.cleaneye.go.kr/fixture/notice?no=TEST_UI_1"]').count()>0);
      assert.equal(await page.locator('#jvBody img').count(),0);
      assert.equal(await page.locator('#jvBody a[href^="org-"]').count(),0);
      assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));
      await page.screenshot({path:path.join(out,`detail-${width}.png`),fullPage:true});
      await page.reload({waitUntil:'networkidle'});
      await page.locator('#jvBody h1').waitFor();
      assert((await page.locator('#jvBody h1').innerText()).includes(token));
      await page.locator('#jvBack').click();
      await page.locator('[data-dash="mine"]:visible').first().click();
      await page.locator('#list [data-open="cleaneye-TEST_UI_1"]').first().waitFor();
      assert.equal(await page.locator('#list [data-open="cleaneye-TEST_UI_2"]').count(),0);
      assert.equal(await page.locator('#list [data-open="cleaneye-TEST_UI_3"]').count(),0);
      assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('apps')).prior_record),{st:'plan',memo:'이전 메모 보존'});
      await page.screenshot({path:path.join(out,`matched-${width}.png`),fullPage:true});
      testFeed={source:'cleaneye',updated:null,collectionStatus:'not_collected',posts:[]};
      await page.goto(baseURL+'?q='+encodeURIComponent(token),{waitUntil:'networkidle'});
      await page.waitForFunction(()=>DATA_HEALTH.cleaneye!=='pending' && document.querySelector('#cpFeedStatus')?.textContent.includes('클린아이 잡플러스 첫 수집 전'));
      assert.equal(await page.evaluate(()=>DATA_HEALTH.cleaneye),'not_collected');
      assert((await page.locator('#cpFeedStatus').textContent()).includes('클린아이 잡플러스 첫 수집 전'));
      assert.deepEqual(errors,[]);
      reports.push({width,sourceLabel:true,publicSector:true,regularContractFilters:true,unknownDateSafe:true,rawCountPreserved:true,savedAfterReload:true,previousSavedPreserved:true,previousApplicationPreserved:true,detailHashReload:true,officialLink:true,detailHtmlEscaped:true,personalizedConditions:true,noPhantomOrgPage:true,notCollectedDistinct:true,overflow:false,pageErrors:errors.length});
      console.log(JSON.stringify({fixtureViewport:width,passed:true}));
      await context.close();
    }
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({fixtureOnly:true,liveApiCalled:false,results:reports},null,2));
    console.log(JSON.stringify({fixtureOnly:true,liveApiCalled:false,results:reports}));
  }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
