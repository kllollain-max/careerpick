let cpVisibleLimit=30, cpLastFilter="";
function cpCheckVisibleLimit(){ const key=JSON.stringify(state);if(key!==cpLastFilter){cpVisibleLimit=30;cpLastFilter=key;} }
/* UI wiring for the existing homepage; no changes to delivery or collection. */
const CP_FEED_STAMPS={},CP_FEED_ISSUES={};
const CP_UNCONFIRMED_IDS=new Set();
async function cpFetchJson(path){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
  try{const response=await fetch(path,{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('feed_http');return await response.json();}
  finally{clearTimeout(timer);}
}
async function cpReadFeed(path,key){
  const parsed=CPHome.parseFeed(await cpFetchJson(path+'?t='+Date.now()));
  CP_FEED_STAMPS[key]=parsed.updated;CP_FEED_ISSUES[key]=parsed.issues;
  return parsed.rows;
}
function cpResetBrowseFilters(){Object.assign(state,{q:'',sector:'',employment:'',career:'',cat:null,region:'',status:'all',onlyNew:false,deadline:'all'});$('q').value='';}
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
