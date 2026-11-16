// Exact employer-origin PDF byte digest for SeoulMetro Environment 2026-17 only.
// Called by the existing fail-closed official receipt verifier; never publishes.
// Read-only Chromium resolves the employer board's JS access challenge and signed
// attachment href. Reject any different notice, host, attachment or non-PDF.
const { chromium } = require('playwright');
const fs=require('fs'),crypto=require('crypto');
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const context=await browser.newContext({acceptDownloads:true,locale:'ko-KR'});
    const page=await context.newPage();
    const notice='https://cleanmetro.co.kr/bbs/board.php?bo_table=recruit&wr_id=430';
    await page.goto(notice,{waitUntil:'domcontentloaded',timeout:50000});
    await page.waitForFunction(()=>document.body.innerText.includes('2026-17'),null,{timeout:25000});
    const actual=new URL(page.url());
    if(actual.hostname!=='cleanmetro.co.kr'||actual.pathname!=='/bbs/board.php'||actual.searchParams.get('bo_table')!=='recruit'||actual.searchParams.get('wr_id')!=='430'||[...actual.searchParams.keys()].some(k=>!['bo_table','wr_id','page'].includes(k)))throw Error('EMPLOYER_NOTICE_REDIRECT '+JSON.stringify({host:actual.hostname,path:actual.pathname,board:actual.searchParams.get('bo_table'),id:actual.searchParams.get('wr_id'),keys:[...actual.searchParams.keys()]}));
    const found=await page.locator('a[href]').evaluateAll(els=>els.map(a=>({url:a.href,label:a.innerText})).filter(x=>{
      try{const u=new URL(x.url);return u.protocol==='https:'&&u.hostname==='cleanmetro.co.kr'&&u.pathname==='/bbs/download.php'&&u.searchParams.get('bo_table')==='recruit'&&u.searchParams.get('wr_id')==='430'&&u.searchParams.get('no')==='11'}catch{return false}
    }));
    if(found.length!==1||!found[0].label.includes('2026-17')||!found[0].label.includes('.pdf'))throw Error('EXACT_ATTACHMENT_MISMATCH');
    const [download]=await Promise.all([page.waitForEvent('download',{timeout:45000}),page.locator('a[href*="download.php"][href*="no=11"]').first().click()]);
    const p=await download.path();
    if(!p)throw Error('PDF_DOWNLOAD_MISSING');
    const raw=fs.readFileSync(p);
    if(!raw.subarray(0,5).equals(Buffer.from('%PDF-'))||raw.length<10000||raw.length>10000000)throw Error('PDF_MAGIC_OR_SIZE');
    // Send only the exact raw SHA-256 to stdout; review/semantic approval remains separate.
    process.stdout.write(crypto.createHash('sha256').update(raw).digest('hex')+'\n');
  } finally {await browser.close()}
})().catch(e=>{process.stderr.write('EXACT_PDF_VERIFICATION_FAILED: '+String(e)+'\n');process.exitCode=1});
