/* Ephemeral, tab-scoped browsing state. Never touches personal record buckets. */
const CP_BROWSE_KEY='careerpick-browse-v1';
const cpBrowseMemory=new Map();let cpActiveBrowseId=null;
function cpNewBrowseEntry(){cpActiveBrowseId=Date.now().toString(36)+Math.random().toString(36).slice(2,8);return cpActiveBrowseId;}
function cpRememberBrowse(){if(cpBrowseReady&&!cpRestoringBrowse&&!JV&&!location.hash.startsWith('#job=')&&cpActiveBrowseId){cpBrowseMemory.set(cpActiveBrowseId,cpBrowseSnapshot());if(cpBrowseMemory.size>50)cpBrowseMemory.delete(cpBrowseMemory.keys().next().value);}}
function cpRestoreBrowseEntry(entry){cpActiveBrowseId=entry?.cpBrowseId||cpNewBrowseEntry();return cpRestoreBrowse(cpBrowseMemory.get(cpActiveBrowseId)||entry?.cpNav);}
let cpRestoringBrowse=false,cpBrowseGeneration=0,cpBrowseTimer=null,cpBrowseIgnoreScrollUntil=0,cpBrowseReady=false,cpBrowsePending=null,cpFeedEngaged=false;
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
 if(value.anchor&&Array.isArray(raw.anchor.neighbors))value.anchor.neighbors=raw.anchor.neighbors.filter(id=>typeof id==='string'&&id.length>0&&id.length<=160).slice(0,2);
 return value;
}
function cpBrowseAnchorFor(link){
 if(!link)return null;
 const card=link.closest('li'),cards=[...document.querySelectorAll('#list>li.card')],index=cards.indexOf(card);
 const identify=card=>{const a=card?.querySelector('[data-open],[data-save]');return a?.dataset.open||a?.dataset.save;};
 return {id:link.dataset.open||link.dataset.save,offset:card.getBoundingClientRect().top,
  neighbors:[identify(cards[index+1]),identify(cards[index-1])].filter(Boolean)};
}
function cpBrowseAnchor(){
 const cards=[...document.querySelectorAll('#list>li.card')];
 const el=cards.find(e=>e.getBoundingClientRect().bottom>0&&e.getBoundingClientRect().top<innerHeight);
 return cpBrowseAnchorFor(el?.querySelector('[data-open],[data-save]'));
}
function cpBrowseSnapshot(id){
 let anchor=cpBrowseAnchor();
 if(id){const link=[...document.querySelectorAll('#list [data-open]')].find(e=>e.dataset.open===id);if(link)anchor=cpBrowseAnchorFor(link);}
 return {version:1,state:Object.fromEntries(CP_BROWSE_FIELDS.filter(k=>state[k]!==undefined).map(k=>[k,state[k]])),limit:cpVisibleLimit,top:scrollY,anchor};
}
function cpSaveBrowse(id,sessionOnly=false){
 if(!cpBrowseReady||cpRestoringBrowse||location.hash.startsWith('#job=')||typeof JV!=='undefined'&&JV)return;
 const snapshot={...cpBrowseSnapshot(id),entryId:cpActiveBrowseId};
 if(cpActiveBrowseId)cpBrowseMemory.set(cpActiveBrowseId,snapshot);
 if(!sessionOnly)try{history.replaceState({...history.state,cpBrowseId:cpActiveBrowseId,cpNav:snapshot,cpBrowse:snapshot.state,cpScroll:snapshot.top},'',location.href);}catch(_){}
 try{sessionStorage.setItem(CP_BROWSE_KEY,JSON.stringify(snapshot));}catch(_){}
}
function cpBrowseRangeForAnchor(rows,current,snapshot){
 if(!snapshot?.anchor)return current;
 const candidates=[snapshot.anchor.id,...(snapshot.anchor.neighbors||[])];
 let index=-1;for(const id of candidates){index=rows.findIndex(p=>p.id===id||p.sourceIds?.includes(id));if(index>=0)break;}
 return index<0?current:Math.min(30000,Math.max(current,Math.ceil((index+1)/30)*30));
}
function cpBrowseRestorePosition(snapshot,restoreFocus=false){
 const generation=++cpBrowseGeneration;
 requestAnimationFrame(()=>requestAnimationFrame(()=>{
  if(generation!==cpBrowseGeneration||typeof JV!=='undefined'&&JV)return;
  const candidates=[...document.querySelectorAll('#list [data-open],#list [data-save]')];
  const lookup=id=>candidates.find(e=>(e.dataset.open||e.dataset.save)===id);
  const link=snapshot.anchor&&(lookup(snapshot.anchor.id)||(snapshot.anchor.neighbors||[]).map(lookup).find(Boolean));
  const card=link?.closest('li'),top=card?scrollY+card.getBoundingClientRect().top-snapshot.anchor.offset:snapshot.top;
  cpBrowseIgnoreScrollUntil=performance.now()+250;window.scrollTo({top:Math.max(0,top),behavior:'instant'});
  if(link&&restoreFocus)link.focus({preventScroll:true});
  cpRestoringBrowse=false;if(cpActiveBrowseId)cpBrowseMemory.set(cpActiveBrowseId,snapshot);
 }));
}
function cpBrowseCanRestore(snapshot){
 if(CP_DATA_LOADING&&snapshot.anchor)return [...document.querySelectorAll('#list [data-open],#list [data-save]')].some(e=>(e.dataset.open||e.dataset.save)===snapshot.anchor.id);
 return POSTS.length>0||!CP_DATA_LOADING;
}
function cpCancelBrowseRestore(){if(cpRestoringBrowse){cpRestoringBrowse=false;cpBrowsePending=null;cpBrowseGeneration++;}}
function cpRestoreBrowse(raw,renderNow=true){
 const snapshot=cpBrowseValid(raw);if(!snapshot)return false;
 cpRestoringBrowse=true;cpBrowsePending=snapshot;Object.assign(state,snapshot.state);$('q').value=state.q;
 cpVisibleLimit=snapshot.limit;cpLastFilter=JSON.stringify(state);
 if(renderNow){CP_RESTORING_TAB=true;refresh();CP_RESTORING_TAB=false;}
 if(cpBrowseCanRestore(snapshot)){cpBrowsePending=null;cpBrowseRestorePosition(snapshot,true);}
 return true;
}
function cpBrowseAfterRender(anchor){
 if(location.hash.startsWith('#job='))return;
 cpRememberBrowse();
 if(cpBrowsePending&&cpBrowseCanRestore(cpBrowsePending)){const snapshot=cpBrowsePending;cpBrowsePending=null;cpBrowseRestorePosition(snapshot,true);}
 else if(anchor&&!cpRestoringBrowse)cpBrowseRestorePosition({...cpBrowseSnapshot(),anchor});
}
function cpSetupBrowse(){
 cpBrowseReady=true;cpActiveBrowseId=history.state?.cpBrowseId||cpNewBrowseEntry();
 try{history.replaceState({...history.state,cpBrowseId:cpActiveBrowseId},"",location.href);}catch(_){}
 try{history.scrollRestoration='manual';}catch(_){}
 const fromURL=new URLSearchParams(location.search).has('q');
 let raw=history.state?.cpNav;
 if(!fromURL)try{const saved=JSON.parse(sessionStorage.getItem(CP_BROWSE_KEY));if(!raw||saved?.entryId===history.state?.cpBrowseId)raw=saved;}catch(_){}
 if(!fromURL&&raw)cpRestoreBrowse(raw,false);
 const params=new URLSearchParams(location.search);if(fromURL){state.q=params.get('q')||'';state.tab='all';$('q').value=state.q;}
 if(['spec','cert'].includes(params.get('tab')))state.tab=params.get('tab');
 CP_URL_APPLIED=true;
 let scrollTimer;
 window.addEventListener('scroll',()=>{if(!JV&&!cpRestoringBrowse&&performance.now()>=cpBrowseIgnoreScrollUntil){cpFeedEngaged=true;clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>cpSaveBrowse(),180);}},{passive:true});
 document.addEventListener('pointerdown',()=>{cpFeedEngaged=true;cpBrowseIgnoreScrollUntil=0;cpCancelBrowseRestore();},{passive:true});
 document.addEventListener('keydown',()=>{cpFeedEngaged=true;cpBrowseIgnoreScrollUntil=0;cpCancelBrowseRestore();},{passive:true});
 window.addEventListener('wheel',()=>{cpBrowseIgnoreScrollUntil=0;},{passive:true});window.addEventListener('touchstart',()=>{cpBrowseIgnoreScrollUntil=0;},{passive:true});
 document.addEventListener('input',()=>{cpFeedEngaged=true;cpCancelBrowseRestore();},true);
 document.addEventListener('click',e=>{const a=e.target.closest('a[data-open],a[target="_blank"],[data-cpnav],[data-tab],[data-dash]');if(a)cpSaveBrowse(a.dataset.open);},true);
 window.addEventListener('pageshow',e=>{if(e.persisted&&!JV)cpRestoreBrowseEntry(history.state);});
 window.addEventListener('pagehide',()=>cpSaveBrowse(null,true));
 document.addEventListener('visibilitychange',()=>{if(document.hidden)cpSaveBrowse(null,true);});
 // Reflow changes card height without a user scroll; retain the last public card anchor.
 let viewportWidth=innerWidth,rootFont=getComputedStyle(document.documentElement).fontSize;
 const restoreReflow=()=>{
  const font=getComputedStyle(document.documentElement).fontSize,changed=viewportWidth!==innerWidth||rootFont!==font;
  viewportWidth=innerWidth;rootFont=font;
  if(!changed||!cpFeedEngaged||document.hidden||JV||cpRestoringBrowse||$('sheet')?.classList.contains('open')||$('panel')?.classList.contains('open'))return;
  const snapshot=cpBrowseMemory.get(cpActiveBrowseId);
  if(snapshot?.anchor&&JSON.stringify(snapshot.state)===JSON.stringify(cpBrowseSnapshot().state)){cpRestoringBrowse=true;cpBrowseRestorePosition(snapshot);}
 };
 window.addEventListener('resize',restoreReflow,{passive:true});
 if(typeof ResizeObserver!=='undefined'){const observer=new ResizeObserver(restoreReflow);observer.observe($('list'));}

}
let cpQueuedFeedUpdate=null,cpApplyingFeedUpdates=false;
function cpFlushFeedUpdate(){
 if(!cpQueuedFeedUpdate)return false;
 const apply=cpQueuedFeedUpdate;cpQueuedFeedUpdate=null;if($('cpFeedUpdate'))$('cpFeedUpdate').hidden=true;
 cpApplyingFeedUpdates=true;try{apply();}finally{cpApplyingFeedUpdates=false;}return true;
}
function cpOfferFeedUpdate(apply){
 if(!cpFeedEngaged||location.hash.startsWith('#job=')||!document.querySelector('#list .card')){apply();return;}
 const prior=cpQueuedFeedUpdate;cpQueuedFeedUpdate=prior?()=>{prior();apply();}:apply;
 const anchor=scrollY>0&&!cpRestoringBrowse?cpBrowseAnchor():null;let box=$('cpFeedUpdate');
 if(!box){box=document.createElement('div');box.id='cpFeedUpdate';box.setAttribute('role','status');box.innerHTML='공고·조건 자료가 준비됐습니다. 현재 목록을 유지하고 있어요. <button type="button" id="cpApplyFeedUpdate">자료 갱신</button>';$('summary').parentElement.before(box);}
 box.hidden=false;if(anchor)cpBrowseRestorePosition({...cpBrowseSnapshot(),anchor});const summary=$('summary');if(summary)summary.innerHTML=summary.innerHTML.replace(' · 일부 출처 확인 중 · 최종 건수 미확정',' · 추가 자료 준비됨 (자료 갱신 후 전체 결과 확인)');
}
document.addEventListener('click',e=>{if(e.target.closest('#cpApplyFeedUpdate')&&cpQueuedFeedUpdate){cpFlushFeedUpdate();refresh();cpSaveBrowse();}});

let cpVisibleLimit=30, cpLastFilter="";
function cpCheckVisibleLimit(){ const key=JSON.stringify(state);if(key!==cpLastFilter){if(cpRestoringBrowse&&cpLastFilter){cpRestoringBrowse=false;cpBrowsePending=null;}cpVisibleLimit=30;cpLastFilter=key;cpBrowseGeneration++;if(cpBrowseReady&&!cpRestoringBrowse&&scrollY>($("summary")?.offsetTop||0))window.scrollTo({top:$("summary")?.offsetTop||0,behavior:"instant"});} }
/* UI wiring for the existing homepage; no changes to delivery or collection. */
const CP_FEED_STAMPS={},CP_FEED_ISSUES={},CP_FEED_CACHE=new Map();
const CP_UNCONFIRMED_IDS=new Set();
async function cpFetchJson(path){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
  try{const response=await fetch(path,{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('feed_http');const file=new URL(path,location.href).pathname.split('/').pop();if(response.headers.get('X-CareerPick-Cache')==='fallback')CP_FEED_CACHE.set(file,response.headers.get('X-CareerPick-Cached-At'));else CP_FEED_CACHE.delete(file);return await response.json();}
  finally{clearTimeout(timer);}
}
async function cpReadFeed(path,key){
  const parsed=CPHome.parseFeed(await cpFetchJson(path+'?t='+Date.now()));
  CP_FEED_STAMPS[key]=parsed.updated;CP_FEED_ISSUES[key]=parsed.issues;
  return parsed.rows;
}
function cpResetBrowseFilters(){cpQueryTouched=true;Object.assign(state,{q:'',sector:'',employment:'',career:'',cat:null,region:'',status:'all',onlyNew:false,deadline:'all'});$('q').value='';}
function cpSyncDialogState(){
  const sheet=$('sheet')?.classList.contains('open'),job=$('jobview') && !$('jobview').hidden,filter=$('panel')?.classList.contains('open') && matchMedia('(max-width:700px)').matches;
  const wrap=document.querySelector('.wrap');if(wrap)wrap.inert=!!(sheet||job);
  if($('jobview'))$('jobview').inert=!!sheet;
  for(const el of document.querySelectorAll('.wrap>header,.wrap>.cp-mobile-nav,.wrap>.cp-support,.wrap>footer,#jobsMain>*:not(#panel)'))el.inert=!!filter;
}
let cpEnterpriseState = 'pending';
async function cpLoadEnterprise(){
  try {
    const data = await cpFetchJson('enterprise_jobs.json?t='+Date.now());
    if(!Array.isArray(data.jobs)) throw Error('enterprise schema');
    const ids = new Set(POSTS.map(p=>p.id));
    POSTS.push(...data.jobs.map(CPHome.enterprise).filter(p=>p && !ids.has(p.id)));
    cpEnterpriseState = data.jobs.length ? 'ok':'empty';
    DATA_HEALTH.enterprise=cpEnterpriseState;CP_FEED_STAMPS.enterprise=data.updated_at;
    if(data.jobs.some(j=>!CPHome.enterprise(j)))CP_FEED_ISSUES.enterprise=['invalid_row'];
  } catch(e){ cpEnterpriseState = 'error';DATA_HEALTH.enterprise='error'; }
}
async function cpLoadWork24(){
  try{
    const policy=await cpFetchJson('work24-policy.json?t='+Date.now());
    if(!policy || typeof policy!=='object' || Array.isArray(policy) || typeof policy.approved!=='boolean')throw Error('work24 policy schema');
    if(policy.approved===false){DATA_HEALTH.work24='awaiting_approval';return;}
  }catch(e){DATA_HEALTH.work24='config_error';return;}
  try{
    const status=await cpFetchJson('work24-status.json?t='+Date.now());
    if(['disabled','blocked_external','awaiting_approval'].includes(status.state)){DATA_HEALTH.work24='disabled';return;}
    if(!['ok','unchanged'].includes(status.state) || status.api_ok!==true)throw Error('work24 collection');
    const checked=Date.parse(status.last_success_at);
    if(!Number.isFinite(checked) || Date.now()-checked>24*3600000 || checked>Date.now()+300000)throw Error('work24 stale receipt');
    const data=await cpFetchJson('work24.json?t='+Date.now());
    if(data.updated_at!==status.snapshot_updated_at || !Array.isArray(data.posts) || data.count!==data.posts.length || status.counts?.stored!==data.count)throw Error('work24 count');
    const ids=new Set(POSTS.map(p=>p.id));
    for(const row of data.posts){const p=CPHome.work24(row);if(p && !ids.has(p.id)){POSTS.push(p);ids.add(p.id);}}
    DATA_HEALTH.work24='ok';CP_FEED_STAMPS.work24=status.last_success_at;
  }catch(e){DATA_HEALTH.work24='error';}
}
function cpRenderHomeFilters(){
  const sectors = [['','전체공고'],['public','공공기관'],['service','공무직']];
  const now = new Date();
  const jobs = POSTS.filter(p=>p.type==='j' && statusOf(p,now)!=='closed');
  $('cpSectors').innerHTML = sectors.map(([key,label])=>`<button type="button" data-sector="${key}" aria-pressed="${state.sector===key}">${label}<small>${jobs.filter(p=>!key || CPHome.sector(p)===key).length}</small></button>`).join('');
  $('cpRegion').value = state.region;
  $('cpEmployment').value = state.employment;
  $('cpCareer').value = state.career;
  $('cpOrder').value = state.sort;
  const parts = [state.q && `검색: ${state.q}`,state.sector && sectors.find(x=>x[0]===state.sector)?.[1],state.region,state.employment,state.career,state.cat,state.status!=='all' && STATUS.find(x=>x[0]===state.status)?.[1],state.deadline!=='all' && `${state.deadline==='today'?'오늘':state.deadline+'일 이내'} 마감`].filter(Boolean);
  $('cpApplied').textContent = parts.length ? '적용 조건 · '+parts.join(' · ') : '';
  if(DATA_HEALTH.detail==='pending')$('cpApplied').textContent += ' · 상세 지역·경력 정보를 확인하고 있습니다.';
  if(state.sector==='enterprise' && cpEnterpriseState==='error') $('cpApplied').textContent += ' · 기업 공고를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.';
  else if(state.sector==='enterprise' && cpEnterpriseState==='empty') $('cpApplied').textContent += ' · 현재 제공된 기업 공고가 없습니다.';
}
let cpFilterFocus = null;
function cpToggleFilters(open){
  $('panel').classList.toggle('open',open);
  $('toggle').setAttribute('aria-expanded',String(open));
  cpSyncDialogState();
  if(open){
    cpFilterFocus = document.activeElement;
    if(matchMedia('(max-width:700px)').matches){
      $('panel').setAttribute('role','dialog'); $('panel').setAttribute('aria-modal','true');
      $('cpFilterClose').focus();
    }
  } else {
    $('panel').removeAttribute('role'); $('panel').removeAttribute('aria-modal');
    cpFilterFocus?.focus();
  }
}
function cpFocusTrap(event, box){
  if(event.key!=='Tab') return;
  const items = [...box.querySelectorAll('a[href],button,input,select,textarea,[tabindex="0"]')].filter(x=>!x.disabled && x.getClientRects().length);
  const first=items[0],last=items[items.length-1];
  if(!first) return;
  if(event.shiftKey && (document.activeElement===first || !box.contains(document.activeElement))){event.preventDefault();last.focus();}
  else if(!event.shiftKey && (document.activeElement===last || !box.contains(document.activeElement))){event.preventDefault();first.focus();}
}
function cpSetupHome(){
  $('cpRegion').innerHTML = '<option value="">전체 지역</option>'+SIDO.map(r=>`<option>${r}</option>`).join('');
  for(const [id,key] of [['cpRegion','region'],['cpEmployment','employment'],['cpCareer','career'],['cpOrder','sort']]){
    $(id).addEventListener('change',e=>{state[key]=e.target.value;refresh();});
  }
  document.addEventListener('click',e=>{
    if(e.target.closest('#cpLoadMore')){cpVisibleLimit+=30;render();}
    const sector=e.target.closest('[data-sector]');
    if(sector){state.sector=sector.dataset.sector;state.tab='all';state.cat=null;refresh();document.querySelector(`[data-sector="${state.sector}"]`)?.focus();}
    if(e.target.closest('#cpFilterClose,#cpFilterDone')) cpToggleFilters(false);
    if(e.target.closest('#cpFilterReset')) $('reset').click();
    const toc=e.target.closest('.jv-toc a');
    if(toc){e.preventDefault();$(toc.hash.slice(1))?.scrollIntoView({block:'start'});}
    if(e.target.closest('[data-dash="all"],[data-dash="saved"],[data-dash="mine"],[data-dash="track"]')) window.scrollTo({top:0,behavior:'instant'});
    if(e.target.closest('#cpFilterDone')) $('summary').scrollIntoView({block:'nearest'});
  });
  document.addEventListener('keydown',e=>{
    if($('sheet').classList.contains('open')){
      if(e.key==='Escape'){e.preventDefault();closeSheet();}
      else cpFocusTrap(e,$('sheet'));
    } else if($('panel').classList.contains('open') && matchMedia('(max-width:700px)').matches){
      if(e.key==='Escape'){e.preventDefault();cpToggleFilters(false);}
      else cpFocusTrap(e,$('panel'));
    } else if(!$('jobview').hidden) cpFocusTrap(e,$('jobview'));
  });
  const media=matchMedia('(max-width:700px)');
  const place=()=>{
    if(media.matches) $('cpFilterScroll').prepend($('cpPrimaryFilters'));
    else {$('panel').before($('cpPrimaryFilters'));$('panel').removeAttribute('role');$('panel').removeAttribute('aria-modal');}
  };
  media.addEventListener('change',()=>{cpToggleFilters(false);place();});place();
  const viewport=()=>{document.documentElement.style.setProperty('--cp-viewport',(window.visualViewport?.height || innerHeight)+'px');document.documentElement.style.setProperty('--cp-viewport-top',(window.visualViewport?.offsetTop || 0)+'px');};
  window.visualViewport?.addEventListener('resize',viewport);window.visualViewport?.addEventListener('scroll',viewport);window.addEventListener('resize',viewport);viewport();
}

// Per-source validation receipt; a failed attempt never replaces this file.
(async()=>{try{const res=await fetch('operations-status.json',{cache:'no-store'});if(!res.ok)return;const r=await res.json();if(r.source!=='alio'||!r.snapshot_at)return;for(const id of r.unconfirmed_ids||[])CP_UNCONFIRMED_IDS.add(id);if(typeof refresh==='function')refresh();const note=document.createElement('p');note.className='muted';note.textContent='ALIO 자료 변경: '+r.snapshot_at+' · 마지막 정상 API 확인: '+r.last_success_at+' · 보관 '+r.counts.archived+'건 포함 · 공식 목록 접수 중 '+(r.counts.confirmed_current??'미확인')+'건 · 목록 부재 상태 미확인 '+(r.counts.unconfirmed??'미확인')+'건. 공식 공고를 확인하세요.';document.querySelector('footer')?.append(note);}catch(_){}})();
