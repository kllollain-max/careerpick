/* Ephemeral, tab-scoped browsing state. Never touches personal record buckets. */
const CP_BROWSE_KEY='careerpick-browse-v1';
let cpRestoringBrowse=false,cpBrowseGeneration=0,cpBrowseTimer=null,cpBrowseReady=false,cpBrowsePending=null,cpFeedEngaged=false;
const CP_BROWSE_FIELDS=['specV','tab','q','sector','employment','career','cat','region','status','sort','onlyNew','deadline','certQ'];
function cpBrowseValid(raw){
 if(!raw||raw.version!==1||!raw.state||typeof raw.state!=='object'||Array.isArray(raw.state))return null;
 const value={version:1,state:{},limit:30,top:0,anchor:null};
 for(const key of CP_BROWSE_FIELDS){const v=raw.state[key];if(key==='onlyNew'){if(typeof v==='boolean')value.state[key]=v;}else if((key==='cat'||key==='certQ')&&v===null||typeof v==='string'&&v.length<=1000)value.state[key]=v;}
 if(!['all','mine','saved','track','spec','cert','p','m'].includes(value.state.tab))return null;
 if(!['due','new'].includes(value.state.sort))return null;
 value.limit=Number.isInteger(raw.limit)&&raw.limit>=30?Math.min(raw.limit,30000):30;
 value.top=Number.isFinite(raw.top)?Math.max(0,Math.min(raw.top,1e7)):0;
 if(raw.anchor&&typeof raw.anchor.id==='string'&&raw.anchor.id.length<=160&&Number.isFinite(raw.anchor.offset))value.anchor={id:raw.anchor.id,offset:Math.max(-5000,Math.min(raw.anchor.offset,5000))};
 return value;
}
function cpBrowseAnchor(){
 const cards=[...document.querySelectorAll('#list>li.card')];
 const el=cards.find(e=>e.getBoundingClientRect().bottom>0&&e.getBoundingClientRect().top<innerHeight);
 const link=el?.querySelector('[data-open],[data-save]');
 return link?{id:link.dataset.open||link.dataset.save,offset:el.getBoundingClientRect().top}:null;
}
function cpBrowseSnapshot(id){
 let anchor=cpBrowseAnchor();
 if(id){const link=[...document.querySelectorAll('#list [data-open]')].find(e=>e.dataset.open===id);if(link)anchor={id,offset:link.closest('li').getBoundingClientRect().top};}
 return {version:1,state:Object.fromEntries(CP_BROWSE_FIELDS.filter(k=>state[k]!==undefined).map(k=>[k,state[k]])),limit:cpVisibleLimit,top:scrollY,anchor};
}
function cpSaveBrowse(id){
 if(!cpBrowseReady||cpRestoringBrowse||typeof JV!=='undefined'&&JV)return;
 const snapshot=cpBrowseSnapshot(id);
 try{history.replaceState({...history.state,cpNav:snapshot,cpBrowse:snapshot.state,cpScroll:snapshot.top},'',location.href);}catch(_){}
 try{sessionStorage.setItem(CP_BROWSE_KEY,JSON.stringify(snapshot));}catch(_){}
}
function cpBrowseRestorePosition(snapshot,restoreFocus=false){
 const generation=++cpBrowseGeneration;
 requestAnimationFrame(()=>requestAnimationFrame(()=>{
  if(generation!==cpBrowseGeneration||typeof JV!=='undefined'&&JV)return;
  const link=snapshot.anchor&&[...document.querySelectorAll('#list [data-open],#list [data-save]')].find(e=>(e.dataset.open||e.dataset.save)===snapshot.anchor.id);
  const card=link?.closest('li'),top=card?scrollY+card.getBoundingClientRect().top-snapshot.anchor.offset:snapshot.top;
  window.scrollTo({top:Math.max(0,top),behavior:'instant'});
  if(link&&restoreFocus)link.focus({preventScroll:true});
  cpRestoringBrowse=false;cpSaveBrowse();
 }));
}
function cpRestoreBrowse(raw,renderNow=true){
 const snapshot=cpBrowseValid(raw);if(!snapshot)return false;
 cpRestoringBrowse=true;cpBrowsePending=snapshot;Object.assign(state,snapshot.state);$('q').value=state.q;
 cpVisibleLimit=snapshot.limit;cpLastFilter=JSON.stringify(state);
 if(renderNow){CP_RESTORING_TAB=true;refresh();CP_RESTORING_TAB=false;}
 if(POSTS.length||!CP_DATA_LOADING){cpBrowsePending=null;cpBrowseRestorePosition(snapshot,true);}
 return true;
}
function cpBrowseAfterRender(anchor){
 if(cpBrowsePending&&(POSTS.length||!CP_DATA_LOADING)){const snapshot=cpBrowsePending;cpBrowsePending=null;cpBrowseRestorePosition(snapshot,true);}
 else if(anchor&&!cpRestoringBrowse)cpBrowseRestorePosition({...cpBrowseSnapshot(),anchor});
}
function cpSetupBrowse(){
 cpBrowseReady=true;
 try{history.scrollRestoration='manual';}catch(_){}
 const fromURL=new URLSearchParams(location.search).has('q');
 let raw=history.state?.cpNav;
 if(!raw&&!fromURL)try{raw=JSON.parse(sessionStorage.getItem(CP_BROWSE_KEY));}catch(_){}
 if(!fromURL&&raw)cpRestoreBrowse(raw,false);
 const params=new URLSearchParams(location.search);if(fromURL){state.q=params.get('q')||'';state.tab='all';$('q').value=state.q;}
 if(['spec','cert'].includes(params.get('tab')))state.tab=params.get('tab');
 CP_URL_APPLIED=true;
 let scrollTimer;
 window.addEventListener('scroll',()=>{if(!JV&&!cpRestoringBrowse){cpFeedEngaged=true;clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>cpSaveBrowse(),180);}},{passive:true});
 document.addEventListener('pointerdown',()=>{cpFeedEngaged=true;},{passive:true});
 document.addEventListener('keydown',()=>{cpFeedEngaged=true;},{passive:true});
 document.addEventListener('input',()=>{cpFeedEngaged=true;if(cpRestoringBrowse){cpRestoringBrowse=false;cpBrowsePending=null;cpBrowseGeneration++;}},true);
 document.addEventListener('click',e=>{const a=e.target.closest('a[data-open],a[target="_blank"],[data-cpnav],[data-tab],[data-dash]');if(a)cpSaveBrowse(a.dataset.open);},true);
 window.addEventListener('pagehide',()=>cpSaveBrowse());
 document.addEventListener('visibilitychange',()=>{if(document.hidden)cpSaveBrowse();});
}
let cpQueuedFeedUpdate=null;
function cpOfferFeedUpdate(apply){
 if(!cpFeedEngaged||location.hash.startsWith('#job=')||!document.querySelector('#list .card')){apply();return;}
 const prior=cpQueuedFeedUpdate;cpQueuedFeedUpdate=prior?()=>{prior();apply();}:apply;
 const anchor=scrollY>0&&!cpRestoringBrowse?cpBrowseAnchor():null;let box=$('cpFeedUpdate');
 if(!box){box=document.createElement('div');box.id='cpFeedUpdate';box.setAttribute('role','status');box.innerHTML='추가 공고·조건 자료가 준비됐습니다. 현재 목록을 유지하고 있어요. <button type="button" id="cpApplyFeedUpdate">자료 갱신</button>';$('summary').parentElement.before(box);}
 box.hidden=false;if(anchor)cpBrowseRestorePosition({...cpBrowseSnapshot(),anchor});const summary=$('summary');if(summary)summary.innerHTML=summary.innerHTML.replace(' · 일부 출처 확인 중 · 최종 건수 미확정',' · 추가 자료 준비됨 (자료 갱신 후 전체 결과 확인)');
}
document.addEventListener('click',e=>{if(e.target.closest('#cpApplyFeedUpdate')&&cpQueuedFeedUpdate){const apply=cpQueuedFeedUpdate;cpQueuedFeedUpdate=null;$('cpFeedUpdate').hidden=true;apply();cpSaveBrowse();}});
