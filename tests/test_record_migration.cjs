const test=require('node:test'),assert=require('node:assert/strict'),r=require('../record-migration.js');
const backup=data=>({format:'careerpick-backup',version:1,data});
test('preserves status notes and orphan ids while merging; repeated import idempotent',()=>{
 const old={saved:['a1'],apps:{a1:{st:'applied',memo:'new note'}}},incoming={saved:['a1','a999'],apps:{a1:{st:'plan',memo:'old note'},a999:{st:'doc',memo:'orphan'}}};
 const once=r.merge(old,incoming),twice=r.merge(once.data,incoming);
 assert.deepEqual(once.data,twice.data);assert.equal(once.data.apps.a1.memo,'new note');assert.equal(once.data.apps.a999.st,'doc');assert.equal(once.conflicts.length,1);
 assert.equal(once.data['careerpick-import-archive'][0].apps.a1.memo,'old note');
});
test('rejects invalid types/status/prototype input',()=>{
 for(const d of [{saved:[3]},{apps:{a1:{st:'invented'}}},JSON.parse('{"__proto__":{"bad":1}}')])assert.throws(()=>r.validate(backup(d)));
});
test('storage failure rolls back every existing key',()=>{
 const m=new Map([['saved','["a1"]'],['apps','{}']]);let writes=0;
 const s={getItem:k=>m.get(k)??null,removeItem:k=>m.delete(k),setItem:(k,v)=>{if(++writes===3)throw Error('quota');m.set(k,v);}};
 assert.throws(()=>r.apply(s,backup({saved:['a2']})));assert.equal(m.get('saved'),'["a1"]');assert.equal(m.get('apps'),'{}');
});
