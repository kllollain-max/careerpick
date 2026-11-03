const test=require('node:test'),assert=require('node:assert/strict'),r=require('../record-migration.js');
const backup=data=>({format:'careerpick-backup',version:1,data});
test('preserves status notes and orphan ids while merging; repeated import idempotent',()=>{
 const old={saved:['a1'],apps:{a1:{st:'applied',memo:'new note'}}},incoming={saved:['a1','a999'],apps:{a1:{st:'plan',memo:'old note'},a999:{st:'doc',memo:'orphan'}}};
 const once=r.merge(old,incoming),twice=r.merge(once.data,incoming);
 assert.deepEqual(once.data,twice.data);assert.equal(once.data.apps.a1.memo,'new note');assert.equal(once.data.apps.a999.st,'doc');assert.equal(once.conflicts.length,1);
 assert.equal(once.data['careerpick-import-archive'][0].apps.a1.memo,'old note');
});
test('rejects invalid types/status/prototype input',()=>{
 for(const d of [{saved:[3]},{prefs:{region:3}},{apps:{a1:{st:'plan',ck:[null]}}},{apps:{a1:{st:'invented'}}},JSON.parse('{"__proto__":{"bad":1}}')])assert.throws(()=>r.validate(backup(d)));
});
test('storage failure rolls back every existing key',()=>{
 const m=new Map([['saved','["a1"]'],['apps','{}']]);let writes=0;
 const s={getItem:k=>m.get(k)??null,removeItem:k=>m.delete(k),setItem:(k,v)=>{if(++writes===3)throw Error('quota');m.set(k,v);}};
 assert.throws(()=>r.apply(s,backup({saved:['a2']})));assert.equal(m.get('saved'),'["a1"]');assert.equal(m.get('apps'),'{}');
});

test('invalid current records block import before any checkpoint or replacement write',()=>{
 const raw='{"a":null}',m=new Map([['apps',raw]]);let writes=0;
 const s={getItem:k=>m.get(k)??null,setItem:()=>{writes++;},removeItem:()=>assert.fail('remove')};
 assert.throws(()=>r.apply(s,backup({saved:['a']})));assert.equal(writes,0);assert.equal(m.get('apps'),raw);
});
test('persistent rollback failure is reported and exact raw originals remain in verified checkpoint',()=>{
 const raw=' ["a1"] ',m=new Map([['saved',raw],['apps','{}']]);let writes=0;
 const s={getItem:k=>m.get(k)??null,removeItem:k=>m.delete(k),setItem:(k,v)=>{if(++writes>=3)throw Error('persistent quota');m.set(k,v);}};
 assert.throws(()=>r.apply(s,backup({saved:['a2']})),/일부 복구/);assert.equal(JSON.parse(m.get('careerpick-before-import')).raw_records.saved,raw);
});

function memory(seed={}){const m=new Map(Object.entries(seed));return{m,getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};}
function exact(storage){return Object.fromEntries(r.keys.map(k=>[k,storage.getItem(k)]));}
test('preview reports counts/new/duplicate/conflict and performs no writes',()=>{
 const s=memory({saved:'["a1"]',apps:'{"a1":{"st":"applied","memo":"current"}}',prefs:'{"region":["강원"]}'}),before=exact(s);
 const p=r.preview(s,{...backup({saved:['a1','a2'],apps:{a1:{st:'plan',memo:'older'},a2:{st:'plan',ck:[{t:'준비🙂',d:1,ph:'pre'}]}},prefs:{region:['서울']}}),exported_at:'2020-01-01T00:00:00Z'});
 assert.equal(p.savedAdded,1);assert.equal(p.appsAdded,1);assert.equal(p.duplicates.saved,1);assert.equal(p.conflicts,2);assert.equal(p.counts.checklist_items,1);assert.deepEqual(exact(s),before);
});
test('unsupported versions/service/keys and partial backups fail before any writes',()=>{
 for(const b of [{...backup({}),version:2},{...backup({}),service:{id:'other'}},backup({onesignal:{token:'private'}}),{...backup({}),recovery_required:true},{...backup({}),invalid_keys:['apps']}]){
  const s=memory({saved:'["old"]'}),before=exact(s);assert.throws(()=>r.apply(s,b));assert.deepEqual(exact(s),before);assert.equal(s.getItem('careerpick-before-import'),null);
 }
});
test('preview becomes stale after another tab writes, so apply cannot overwrite it',()=>{
 const s=memory({saved:'["old"]'}),b=backup({saved:['new']}),p=r.preview(s,b);s.setItem('saved','["other-tab"]');
 assert.throws(()=>r.apply(s,b,{expectedOriginals:p.originals}),/다른 탭/);assert.equal(s.getItem('saved'),'["other-tab"]');
});
test('different source same unprefixed ID is quarantined and original is not combined',()=>{
 const old={apps:{same:{source:'monitor',st:'applied',memo:'current'}}},incoming={apps:{same:{source:'blog',st:'plan',memo:'incoming',exam:'2099-12-01'}}};
 const result=r.merge(old,incoming);assert.deepEqual(result.data.apps.same,old.apps.same);assert.equal(result.conflicts.length,1);assert.equal(result.data['careerpick-import-archive'][0].apps.same.memo,'incoming');
 assert.throws(()=>r.validate(backup({apps:{a123:{source:'gojobs',st:'plan'}}})),/출처/);
});
test('same backup with different property order is idempotent and settings conflicts remain archived',()=>{
 const a={saved:['a1'],apps:{a1:{st:'plan',memo:'메모'}},spec:{edu:'대졸'}},s=memory();r.apply(s,backup(a));const first=exact(s);
 r.apply(s,backup({spec:{edu:'대졸'},apps:{a1:{memo:'메모',st:'plan'}},saved:['a1']}));assert.deepEqual(exact(s),first);
 const changed=r.apply(s,backup({prefs:{kw:'first'},spec:{edu:'고졸'}}));assert.equal(changed.data.spec.edu,'대졸');assert(changed.conflicts.includes('spec'));
});
test('silent failed write and final readback mismatch are never reported successful',()=>{
 for(const mode of ['noop','readback']){
  const s=memory({saved:' ["old"] ',apps:'{}'}),before=exact(s),put=s.setItem,get=s.getItem;let faulted=false;
  s.setItem=(k,v)=>{if(k==='saved'&&v!==' ["old"] '&&!faulted){faulted=true;if(mode==='noop')return;put(k,v);s.getItem=name=>{if(name==='saved'){s.getItem=get;return '["wrong"]';}return get(name);};return;}put(k,v);};
  assert.throws(()=>r.apply(s,backup({saved:['new']})),/복구/);assert.deepEqual(exact(s),before);
 }
});
test('failure storing completion receipt rolls back all active keys',()=>{
 const s=memory({saved:' ["old"] ',apps:'{}'}),before=exact(s),put=s.setItem;
 s.setItem=(k,v)=>{if(k==='careerpick-before-import'&&JSON.parse(v).state==='complete')throw Error('receipt failure');put(k,v);};
 assert.throws(()=>r.apply(s,backup({saved:['new']})),/복구/);assert.deepEqual(exact(s),before);assert.equal(r.recoveryStatus(s).pending,false);
});
test('pending import blocks edits and recovery refuses unrelated later changes',async()=>{
 const store=require('../record-store.js'),s=memory({saved:'["old"]'}),originals=exact(s),after={...originals,saved:'["old","new"]'};
 s.setItem('careerpick-before-import',JSON.stringify({format:'careerpick-before-import',version:1,state:'prepared',raw_records:originals,expected_after:after}));s.setItem('saved',after.saved);
 assert(r.recoveryStatus(s).pending);await assert.rejects(store.mutate(s,'saved',[],store.saved,v=>[...v,'another']));
 s.setItem('saved','["unrelated-later"]');assert.throws(()=>r.recover(s),/다른 변경/);assert.equal(s.getItem('saved'),'["unrelated-later"]');
 s.setItem('saved',after.saved);r.recover(s);assert.deepEqual(exact(s),originals);assert.equal(r.recoveryStatus(s).pending,false);
});
test('real process exit after partial write leaves durable hold and can restore exact originals',()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cp-import-crash-')),file=path.join(dir,'storage.json'),seed={saved:' ["old"] ',prefs:'{"region":["강원"]}',apps:'{}'};fs.writeFileSync(file,JSON.stringify(seed));
 const code=`const fs=require('fs'),r=require(process.argv[1]),file=process.argv[2];let data=JSON.parse(fs.readFileSync(file)),writes=0;const s={getItem:k=>data[k]??null,setItem:(k,v)=>{data[k]=v;fs.writeFileSync(file,JSON.stringify(data));if(++writes===3)process.exit(73);},removeItem:k=>{delete data[k];fs.writeFileSync(file,JSON.stringify(data));}};r.apply(s,{format:'careerpick-backup',version:1,data:{saved:['new'],prefs:{region:['서울']},apps:{a1:{st:'plan'}}}});`;
 const child=spawnSync(process.execPath,['-e',code,require.resolve('../record-migration.js'),file],{timeout:10000});assert.equal(child.status,73);
 const data=JSON.parse(fs.readFileSync(file)),s=memory(data);assert(r.recoveryStatus(s).pending);r.recover(s);for(const [k,v]of Object.entries(seed))assert.equal(s.getItem(k),v);
 r.apply(s,backup({saved:['new']}));assert.deepEqual(JSON.parse(s.getItem('saved')),['old','new']);
});
