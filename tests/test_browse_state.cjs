const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx=vm.createContext({document:{addEventListener(){}},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync('homepage-ui.js','utf8').split('/* UI wiring')[0],ctx);
const valid=raw=>JSON.parse(JSON.stringify(vm.runInContext('cpBrowseValid('+JSON.stringify(raw)+')',ctx)));
const base={version:1,state:{tab:'all',sort:'due',q:'간호',region:'강원',onlyNew:false},limit:90,top:1234,anchor:{id:'a123',offset:31}};
test('browse snapshot retains range and relative anchor',()=>assert.deepEqual(valid(base),base));
test('unknown versions and malformed containers are ignored',()=>{for(const x of [null,{},[],{...base,version:2},{...base,state:[]}])assert.equal(valid(x),null);});
test('unsupported menus and sorting cannot enter restore',()=>{for(const state of [{tab:'bad',sort:'due'},{tab:'all',sort:'bad'}])assert.equal(valid({...base,state}),null);});
test('damaged field types cannot replace valid text with a boolean or object',()=>{const r=valid({...base,state:{...base.state,q:true,region:{},onlyNew:'yes'}});assert(!('q'in r.state));assert(!('region'in r.state));assert(!('onlyNew'in r.state));});
test('memo, credentials and arbitrary payloads never enter navigation snapshot',()=>{const r=valid({...base,state:{...base.state,memo:'private',token:'private',prefs:{}}});assert.deepEqual(r.state,base.state);});
test('invalid numeric positions and huge ranges are bounded without altering records',()=>{const r=valid({...base,limit:1e8,top:-5,anchor:{id:'a',offset:1e9}});assert.equal(r.limit,30000);assert.equal(r.top,0);assert.equal(r.anchor.offset,5000);});

test('optional public neighbor IDs survive restore and reject arbitrary payloads',()=>{const r=valid({...base,anchor:{...base.anchor,neighbors:['next',null,{memo:'private'},'previous','ignored'],memo:'private'}});assert.deepEqual(r.anchor,{...base.anchor,neighbors:['next','previous']});});

test('new prefix expands only far enough to retain the restored public anchor',()=>{ctx.__rows=Array.from({length:251},(_,i)=>({id:'a'+i}));ctx.__snapshot={anchor:{id:'a175',neighbors:['a176','a174']}};assert.equal(vm.runInContext('cpBrowseRangeForAnchor(__rows,90,__snapshot)',ctx),180);ctx.__rows=ctx.__rows.filter(x=>x.id!=='a175');assert.equal(vm.runInContext('cpBrowseRangeForAnchor(__rows,90,__snapshot)',ctx),180);assert.equal(vm.runInContext('cpBrowseRangeForAnchor([],90,__snapshot)',ctx),90);});
