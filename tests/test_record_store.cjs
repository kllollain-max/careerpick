const test=require('node:test'),assert=require('node:assert/strict');
const store=require('../record-store.js');
function storage(seed={}){const data={...seed};return{data,getItem:k=>data[k]??null,setItem:(k,v)=>{data[k]=v}};}
test('corrupt bytes and schema remain byte-for-byte preserved, writes fail closed',async()=>{
 for(const [key,raw,valid,fallback]of [['saved','{bad',store.saved,[]],['saved','{}',store.saved,[]],['apps','{"old":null}',store.apps,{}],['prefs','{"emp":null}',store.prefs,{}]]){
  const s=storage({[key]:raw});assert(!store.read(s,key,fallback,valid).ok);
  await assert.rejects(store.mutate(s,key,fallback,valid,()=>fallback));assert.equal(s.data[key],raw);
 }
});
test('quota failure does not report success or change old saved records',async()=>{
 const s=storage({saved:'["old"]'});s.setItem=()=>{throw Error('quota');};
 await assert.rejects(store.mutate(s,'saved',[],store.saved,rows=>[...rows,'new']),/기기 저장 실패/);assert.equal(s.data.saved,'["old"]');
});
test('latest records merge by identity; stale same-record edits cannot overwrite notes',async()=>{
 const old={st:'plan',memo:'old',unknown_field:'keep'},s=storage({apps:JSON.stringify({a:old,b:{st:'applied'}})});
 await store.mutate(s,'apps',{},store.apps,rows=>store.replaceApp(rows,'a',{...old,memo:'new'},JSON.stringify(old)));
 assert.equal(JSON.parse(s.data.apps).b.st,'applied');assert.equal(JSON.parse(s.data.apps).a.unknown_field,'keep');
 await assert.rejects(store.mutate(s,'apps',{},store.apps,rows=>store.replaceApp(rows,'a',null,JSON.stringify(old))),/다른 탭/);
 assert.equal(JSON.parse(s.data.apps).a.memo,'new');
});
test('unlinked saved identities are retained and duplicate IDs collapse only on successful mutation',async()=>{
 const s=storage({saved:'["missing","missing"]'});
 const result=await store.mutate(s,'saved',[],store.saved,rows=>[...new Set([...rows,'a'])]);assert.deepEqual(result,['missing','a']);
});
test('denied reads and malicious prototype identities never overwrite raw data',async()=>{
 const denied={getItem:()=>{throw Error('denied')},setItem:()=>assert.fail('write')};
 assert(!store.read(denied,'apps',{},store.apps).ok);await assert.rejects(store.mutate(denied,'apps',{},store.apps,()=>({})));
 assert(!store.apps(JSON.parse('{"__proto__":{"st":"plan"}}')));assert(!store.saved(['constructor']));
});
test('Web Locks serialize concurrent tab updates without losing unrelated IDs',async()=>{
 let chain=Promise.resolve();const locks={request:(name,fn)=>{const next=chain.then(fn);chain=next.catch(()=>{});return next;}};
 const s=storage({saved:'[]'});await Promise.all(['a','b'].map(id=>store.mutate(s,'saved',[],store.saved,rows=>[...rows,id],locks)));
 assert.deepEqual(JSON.parse(s.data.saved),['a','b']);
});
test('existing legacy record and long multiline note remain compatible',async()=>{
 const note='긴 메모\n<&>🙂'.repeat(1000),old={title:'원본',memo:note},s=storage({apps:JSON.stringify({a:old})});
 const out=await store.mutate(s,'apps',{},store.apps,rows=>store.replaceApp(rows,'a',{...old,st:'plan'},JSON.stringify(old)));
 assert.equal(out.a.memo,note);
});

test('backup preserves corrupt raw bytes and reports unreadable keys explicitly',()=>{
 const raw='{corrupt original',s=storage({apps:raw,saved:'["a"]'});
 const result=store.exportRecords(s,['saved','apps']);assert.equal(result.raw_records.apps,raw);assert.deepEqual(result.invalid_keys,['apps']);assert.deepEqual(result.data.saved,['a']);assert(!('apps' in result.data));
 assert.deepEqual(store.exportRecords({getItem:()=>{throw Error('denied')}},['saved']).unavailable_keys,['saved']);
});

test('delete has a verified exact pre-write copy; checkpoint failure leaves active record unchanged',async()=>{
 const raw=' {"a":{"st":"plan","memo":"original"}} ',s=storage({apps:raw});
 await store.mutate(s,'apps',{},store.apps,rows=>store.replaceApp(rows,'a',null,JSON.stringify({st:'plan',memo:'original'})));
 assert.equal(JSON.parse(s.data['careerpick-record-checkpoints']).records.apps.raw,raw);assert.equal(s.data.apps,'{}');
 const denied=storage({apps:raw});const put=denied.setItem;denied.setItem=(k,v)=>{if(k==='careerpick-record-checkpoints')throw Error('quota');put(k,v);};
 await assert.rejects(store.mutate(denied,'apps',{},store.apps,()=>({})));assert.equal(denied.data.apps,raw);
});
