const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8');const records=require('../record-migration.js');
function readPrefs(raw){
 const memory=new Map([['prefs',raw]]);const notices=[];
 const block=html.slice(html.indexOf('let PREFS ='),html.indexOf('// ── 내 스펙으로'));
 const ctx={CPRecords:records,localStorage:{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v)},document:{createElement:()=>({setAttribute(){},set textContent(x){notices.push(x)}}),querySelector:()=>({prepend(){}})}};
 vm.createContext(ctx);vm.runInContext(block+';this.result={PREFS,CP_PREFS_READ_ERROR,savePrefs};',ctx);
 return {memory,notices,result:ctx.result};
}
test('malformed preference cannot crash list or overwrite source',()=>{
 const raw=JSON.stringify({region:'강원',emp:['정규직'],kw:'가상'});const x=readPrefs(raw);
 assert.equal(x.result.CP_PREFS_READ_ERROR,true);assert.ok(Array.isArray(x.result.PREFS.region));
 assert.equal(x.result.savePrefs(),false);assert.equal(x.memory.get('prefs'),raw);assert.equal(x.notices.length,1);
});
test('valid preference keeps region, employment and text',()=>{
 const raw=JSON.stringify({region:['강원'],emp:['정규직'],kw:'가상'});const x=readPrefs(raw);
 assert.equal(x.result.CP_PREFS_READ_ERROR,false);assert.equal(x.result.PREFS.region[0],'강원');assert.equal(x.memory.get('prefs'),raw);assert.equal(x.notices.length,0);
});
test('invalid JSON stays available for recovery',()=>{
 const x=readPrefs('{broken');assert.equal(x.memory.get('prefs'),'{broken');assert.equal(x.result.savePrefs(),false);
});
