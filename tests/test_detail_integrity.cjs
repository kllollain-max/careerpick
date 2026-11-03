const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8');const ctx=vm.createContext({});
vm.runInContext(html.slice(html.indexOf('function cpRecruitCount('),html.indexOf('function jobViewHTML(')),ctx);
for(const [raw,want]of [[null,'미기재 · 공식 공고 확인'],['','미기재 · 공식 공고 확인'],[0,'0명'],['약간명','약간명'],['○명','○명'],['미정','미정'],['직무 A 2명 / 직무 B 3명','직무 A 2명 / 직무 B 3명'],[12,'12명']])test('headcount preserves '+JSON.stringify(raw),()=>assert.equal(ctx.cpRecruitCount(raw),want));
test('conflicting source values are both disclosed',()=>{const w=ctx.cpDetailWarnings({id:'a1',alio:true,n:2},{recrutPblntSn:'1',recrutNope:3});assert.match(w[0],/목록 2명 \/ 상세 3명/);});
test('wrong notice detail is quarantined',()=>assert.match(ctx.cpDetailWarnings({id:'a1',alio:true},{recrutPblntSn:'2'})[0],/공고번호/));
test('missing values do not invent conflict',()=>assert.equal(ctx.cpDetailWarnings({id:'a1',n:null},{recrutNope:'약간명'}).length,0));
test('publication start never becomes reception start',()=>assert(!html.includes('`${ymdText(det.pbancBgngYmd)} ~ ${endTxt}`')));
test('sharing retains Pages repository path',()=>assert(html.includes('https://kllollain-max.github.io/careerpick/?src=share#job=')));
