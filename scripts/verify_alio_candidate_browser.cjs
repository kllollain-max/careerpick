const fs = require('node:fs');
const { chromium } = require('playwright');
(async () => {
 const data=JSON.parse(fs.readFileSync('alio.json','utf8'));
 const old=new Set(JSON.parse(fs.readFileSync(process.env.ALIO_BEFORE,'utf8')).posts.map(p=>p.id));
 const added=data.posts.filter(p=>!old.has(p.id));
 if(added.length!==90 || data.posts.length!==610) throw Error('Unexpected candidate count');
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const checks=[];
 fs.mkdirSync('candidate-validation',{recursive:true});
 try {
 for(const width of [320,390,1440]){
   const page=await browser.newPage({viewport:{width,height:900}});
   const errors=[];
   page.on('pageerror',error=>errors.push(error.message));
   await page.goto('http://127.0.0.1:8000/careerpick/',{waitUntil:'networkidle'});
   await page.getByRole('searchbox',{name:'검색',exact:true}).fill(added[0].title);
   await page.waitForFunction(title=>document.body.innerText.includes(title),added[0].title);
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('List overflow '+width);
   await page.screenshot({path:'candidate-validation/list-'+width+'.png',fullPage:true});
   await page.goto('http://127.0.0.1:8000/careerpick/jobs/'+added[0].id+'.html',{waitUntil:'networkidle'});
   if(!(await page.locator('body').innerText()).includes(added[0].title))throw Error('Missing detail title');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('Detail overflow '+width);
   if(await page.locator('img').evaluateAll(imgs=>imgs.some(i=>!i.complete||i.naturalWidth===0)))throw Error('Broken image');
   if(errors.length)throw Error('Page JS error');
   await page.screenshot({path:'candidate-validation/detail-'+width+'.png',fullPage:true});
   checks.push({width,search:true,detail:true,overflow:false,brokenImages:false,pageErrors:0});
   await page.close();
 }
 fs.writeFileSync('candidate-validation/browser-report.json',JSON.stringify({rows:data.posts.length,newIds:added.length,sample:added[0].id,checks},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
