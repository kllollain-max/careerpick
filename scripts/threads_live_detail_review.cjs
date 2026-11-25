// Read-only evidence from the deployed detail dialog; never an approval.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const NOTICE = 'a307271';
const URL = 'https://kllollain-max.github.io/careerpick/#job=a307271';
const SOURCE = 'https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=307271';
const sha = data => createHash('sha256').update(data).digest('hex');
const norm = s => String(s || '').replace(/\s/g, '');
function eligible(manifest, now = new Date()) {
  return manifest?.notice_id === NOTICE && manifest.automatic_approval === false
    && manifest.approved_for_queue === false && manifest.meta_posted === false
    && now < new Date('2026-11-30T16:00:00+09:00')
    && Array.isArray(manifest.documents)
    && manifest.documents.some(d => d.name === 'notice.pdf'
      && d.status === 'raw_bytes_captured_for_review'
      && /^[a-f0-9]{64}$/.test(d.sha256 || ''));
}
function inspect(snapshot) {
  const rows = snapshot.rows || [];
  const text = norm(snapshot.text);
  const title = norm(snapshot.title);
  const section = label => (snapshot.sections || []).some(s => s.title === label && norm(s.text).length > 10);
  const checks = {
    correct_location: snapshot.url === URL,
    visible_dialog: snapshot.visible === true,
    expected_title: title.includes('철원화천지사') && title.includes('청소원') && title.includes('공개경쟁'),
    employer: norm(snapshot.org).includes('한국농어촌공사'),
    exact_source: (snapshot.links || []).includes(SOURCE),
    loaded_detail: !text.includes('상세내용을불러오는중') && section('지원 자격') && section('전형 절차·방법'),
    unit_count: rows.some(r => norm(r.label) === '모집인원' && norm(r.value) === '1명'),
    employment: rows.some(r => /고용형태/.test(norm(r.label)) && /무기계약직|공무직/.test(r.value)),
    cutoff_visible: /(?:11월30일|11[./-]30|20261130).*?16(?::00|시)/.test(text),
    no_identity_warning: !/공고번호가달라|모집인원:목록/.test(text),
    no_page_error: (snapshot.page_errors || []).length === 0
  };
  return { checks, status: Object.values(checks).every(Boolean) ? 'captured_for_semantic_review' : 'hold_ui_check' };
}
async function capture() {
  const out = 'threads-live-detail-review';
  const manifestPath = 'threads-official-raw-review/manifest.json';
  if (!fs.existsSync(manifestPath)) return;
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (!eligible(manifest)) return;
  fs.mkdirSync(out, {recursive:true});
  const report = {notice_id:NOTICE, requested_url:URL, automatic_approval:false,
    approved_for_queue:false, meta_posted:false, semantic_review:'required',
    status:'hold_ui_check', files:[], checked_at:null};
  const save = (name, data) => {
    fs.writeFileSync(path.join(out,name), data);
    report.files.push({name, size_bytes:data.length, sha256:sha(data)});
  };
  let browser;
  try {
    const {chromium} = require('playwright');
    browser = await chromium.launch({headless:true, executablePath:'/usr/bin/google-chrome',
      args:['--no-sandbox'], env:{PATH:process.env.PATH, HOME:process.env.HOME, LANG:'C.UTF-8'}});
    const page = await browser.newPage({viewport:{width:390,height:844}, deviceScaleFactor:1});
    const page_errors = [];
    page.on('pageerror', e => page_errors.push(String(e.message).slice(0,200)));
    await page.route('**/*', route => {
      const request = route.request();
      return ['GET','HEAD'].includes(request.method()) && new URLParser(request.url()).origin === 'https://kllollain-max.github.io'
        ? route.continue() : route.abort();
    });
    const response = await page.goto(URL,{waitUntil:'domcontentloaded',timeout:20000});
    report.http_status = response?.status() || null;
    if (!response?.ok()) throw Error('PUBLIC_DETAIL_HTTP_NOT_OK');
    const dialog = page.locator('#jobview');
    await dialog.waitFor({state:'visible',timeout:20000});
    await page.waitForFunction(() => {
      const body = document.querySelector('#jvBody');
      return body && !body.innerText.includes('상세 내용을 불러오는 중')
        && [...body.querySelectorAll('.jv-sec h3')].some(x => x.innerText === '지원 자격');
    },{},{timeout:20000}).catch(e => {report.detail_wait_error = String(e.message).slice(0,200);});
    const snapshot = await dialog.evaluate(el => ({
      url:location.href, visible:!el.hidden && !!el.getBoundingClientRect().height,
      title:el.querySelector('.jv-title')?.innerText || '',
      org:el.querySelector('.jv-org')?.innerText || '',
      text:el.innerText,
      rows:[...el.querySelectorAll('.jv-grid dt')].map(dt=>({label:dt.innerText,value:dt.nextElementSibling?.innerText || ''})),
      sections:[...el.querySelectorAll('.jv-sec')].map(s=>({title:s.querySelector('h3')?.innerText || '',text:s.innerText})),
      links:[...el.querySelectorAll('a[href]')].map(a=>a.href)
    }));
    snapshot.page_errors = page_errors;
    Object.assign(report,inspect(snapshot));
    save('rendered-detail.json', Buffer.from(JSON.stringify(snapshot,null,2)+'\n'));
    save('detail-top.png', await page.screenshot({animations:'disabled',timeout:8000}));
    const sections = dialog.locator('.jv-sec').filter({has:page.getByRole('heading',{name:'지원 자격',exact:true})});
    if (await sections.count() === 1) {
      save('detail-eligibility.png', await sections.screenshot({animations:'disabled',timeout:8000}));
    }
    if (report.status === 'captured_for_semantic_review' && !report.files.some(f=>f.name==='detail-eligibility.png')) {
      report.status='hold_ui_check';
      report.error='MISSING_ELIGIBILITY_SCREENSHOT';
    }
  } catch (e) {
    report.status='hold_ui_check'; report.error=String(e.message).slice(0,300);
  } finally {
    if (browser) await browser.close().catch(()=>{});
    report.checked_at=new Date().toISOString();
    fs.writeFileSync(path.join(out,'manifest.json'), JSON.stringify(report,null,2)+'\n');
    console.log('Public UI evidence:',report.status,'; approved: 0; posted: 0');
  }
}
// Avoid shadowing the standard URL constructor with the pinned target.
const URLParser = globalThis.URL;
module.exports = {eligible, inspect};
if (require.main === module) capture().catch(e=>{console.error(e.message);process.exitCode=1;});
