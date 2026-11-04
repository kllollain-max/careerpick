const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
const openCode=html.slice(html.indexOf('async function openJob('),html.indexOf('function refreshJobView('));
const popCode=html.slice(html.indexOf('window.addEventListener("popstate", (event) => {'),html.indexOf('// CareerPick 2.0 step 4:'));
test('opening a notice snapshots current filters, range and position without changing records',async()=>{
 const browse={tab:'all',q:'충북대학교병원',region:'충북',employment:'정규직',sort:'count',status:'all',onlyNew:true};
 const records={apps:{a1:{st:'doc',memo:'기존 메모\n둘째 줄'}},saved:['a1']},before=JSON.stringify(records),calls=[];
 const elements={jobview:{hidden:true,scrollTop:7},jvBody:{innerHTML:''},jvBack:{focus(){}}};
 const ctx={POSTS:[{id:'a1',alio:false}],JV:null,JV_PUSHED:false,state:browse,cpVisibleLimit:90,scrollY:671,location:{hash:'',href:'https://example.test/careerpick/'},history:{state:{cpTab:'all',cpQ:'',cpDepth:2},replaceState(s){this.state=s;calls.push(['replace',s]);},pushState(s){this.state=s;calls.push(['push',s]);}},$:id=>elements[id],cpSyncDialogState(){},document:{body:{style:{}}},jobViewHTML:()=>'<p>공고 본문</p>',records};
 vm.createContext(ctx);vm.runInContext(openCode,ctx);await ctx.openJob('a1');
 assert.equal(calls[0][1].cpBrowse.q,browse.q);assert.equal(calls[0][1].cpBrowse.region,'충북');assert.equal(calls[0][1].cpLimit,90);assert.equal(calls[0][1].cpScroll,671);assert.equal(calls[0][1].cpDepth,2);assert.equal(calls[1][1].job,'a1');assert.equal(JSON.stringify(records),before);
});
test('back restores query, intersected filters, expanded range, position and link focus',()=>{
 let handler,position,focused=false;
 const query={value:''},state={tab:'all',q:'',region:'',employment:'',sort:'due',status:'all',onlyNew:false};
 const browse={...state,q:'병원',region:'충북',employment:'정규직',sort:'count',onlyNew:true};
 const ctx={state,CP_RESTORING_TAB:false,cpVisibleLimit:30,cpLastFilter:'',location:{hash:''},window:{addEventListener(_,fn){handler=fn;},scrollTo(p){position=p.top;}},closeJob(){},$:()=>query,refresh(){if(JSON.stringify(state)!==ctx.cpLastFilter)ctx.cpVisibleLimit=30;},requestAnimationFrame:fn=>fn(),document:{querySelectorAll:()=>[{dataset:{open:'a1'},focus(opts){focused=opts.preventScroll;}}]}};
 vm.createContext(ctx);vm.runInContext(popCode,ctx);handler({state:{cpTab:'all',cpQ:'',cpBrowse:browse,cpLimit:90,cpScroll:671,cpAnchor:'a1'}});
 assert.equal(query.value,'병원');assert.equal(state.region,'충북');assert.equal(state.employment,'정규직');assert.equal(state.sort,'count');assert.equal(state.onlyNew,true);assert.equal(ctx.cpVisibleLimit,90);assert.equal(position,671);assert(focused);
});
