(function(){
  'use strict';
  const C=window.SupportPick,$=id=>document.getElementById(id),VIEW='supportpick:view:v1';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const initial={tab:'all',query:'',category:'',region:'',supportType:'',sort:'updated',scroll:0};
  let view={...initial},snapshot={raw:null,data:C.blank()},writable=true,items=[],feedError='',toastTimer,detailFromList=false;
  const drafts=new Map();
  try{snapshot=C.load(localStorage);}catch(e){writable=false;warn(e.message);}
  try{const saved=JSON.parse(sessionStorage.getItem(VIEW)||'null');if(saved&&typeof saved==='object')for(const key of Object.keys(initial))if(typeof saved[key]===typeof initial[key])view[key]=saved[key];}catch(e){}
  if(!['all','matched','saved','apps','guide'].includes(view.tab))view.tab='all';
  try{items=C.parseFeed(window.SUPPORTPICK_DATA);}catch(e){feedError=e.message;}
  function warn(message){$('storageWarning').textContent=message;$('storageWarning').hidden=false;}
  function toast(message){clearTimeout(toastTimer);$('toast').textContent=message;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,4200);}
  function remember(){try{sessionStorage.setItem(VIEW,JSON.stringify(view));}catch(e){}}
  function persist(next){if(!writable)throw Error('기존 기록을 확인할 수 없어 변경을 중단했습니다.');snapshot=C.save(localStorage,snapshot.raw,next);return snapshot.data;}
  function change(update){try{persist(update(structuredClone(snapshot.data)));render();return true;}catch(e){toast(e.message);warn(e.message);return false;}}
  function koreanTime(value){const d=new Date(value);return Number.isFinite(+d)?new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(d):'시각 미확인';}
  function setTab(tab){view.tab=tab;view.scroll=0;remember();if(location.hash.startsWith('#benefit='))history.replaceState(null,'',location.pathname+location.search);render();window.scrollTo({top:0,behavior:'auto'});}
  function categories(){const all=['전체',...new Set([...C.CATEGORIES,...items.map(x=>x.category)])];$('categories').innerHTML=all.map(x=>`<button class="chip" type="button" data-category="${esc(x==='전체'?'':x)}" aria-pressed="${(x==='전체'?'':x)===view.category}">${esc(x)}</button>`).join('');}
  function card(p){
    const saved=snapshot.data.saved.includes(p.id),tracked=C.own(snapshot.data.apps,p.id),reason=view.tab==='matched'?C.matchReasons(p,snapshot.data.prefs):null;
    return `<article class="benefit-card"><div class="card-content"><div class="card-top"><span class="category-badge">${esc(p.category)}</span><span class="badge">${esc(C.status(p))}</span></div><h3><button class="title-link" data-detail="${esc(p.id)}">${esc(p.title)}</button></h3><p class="organization">${esc(p.organization)} · ${esc(p.region)}</p><p class="card-summary">${esc(p.summary)}</p><dl class="card-meta"><dt>지원</dt><dd>${esc(p.supportType)}</dd><dt>기간</dt><dd>${esc(p.period||'공식 공고 확인')}</dd><dt>출처</dt><dd>${esc(p.source)} · ${esc(koreanTime(p.checkedAt))}</dd></dl>${reason&&reason.length?`<p class="match-reason">${esc(reason.join(' · '))}</p>`:''}</div><div class="card-actions"><button data-save="${esc(p.id)}" aria-pressed="${saved}" class="${saved?'saved':''}">${saved?'★ 저장됨':'☆ 관심 저장'}</button><button data-track="${esc(p.id)}">${tracked?'신청 기록 보기':'신청 준비하기'}</button></div></article>`;
  }
  function empty(title,text,action='reset'){return `<div class="empty-state"><span class="empty-mark" aria-hidden="true">◎</span><h3>${esc(title)}</h3><p>${esc(text)}</p>${action==='preferences'?'<button class="primary" data-open-preferences>관심 조건 설정하기</button>':action==='all'?'<button class="quiet" data-show-all>전체 혜택 보기</button>':action==='reset'?'<button class="quiet" data-reset>검색·필터 초기화</button>':''}</div>`;}
  function render(){
    $('savedCount').textContent=snapshot.data.saved.length;$('appCount').textContent=Object.keys(snapshot.data.apps).length;
    document.querySelectorAll('[data-tab]').forEach(b=>{if(b.dataset.tab===view.tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    const isDetail=location.hash.startsWith('#benefit=');
    $('detailSection').hidden=!isDetail;$('hero').hidden=isDetail||view.tab!=='all';$('browseSection').hidden=isDetail||view.tab==='guide';$('guideSection').hidden=isDetail||view.tab!=='guide';$('portals').hidden=isDetail;
    if(isDetail){renderDetail();return;}
    $('preferencesButton').hidden=view.tab==='apps';$('searchForm').hidden=view.tab==='apps';$('categories').hidden=view.tab==='apps';$('filterPanel').hidden=view.tab==='apps'||$('filterToggle').getAttribute('aria-expanded')!=='true';$('sort').closest('label').hidden=view.tab==='apps';
    $('query').value=view.query;$('region').value=view.region;$('supportType').value=view.supportType;$('sort').value=view.sort;categories();
    const titles={all:'관심 있는 혜택을 찾아보세요',matched:'내 관심 조건에 맞는 혜택',saved:'다시 보고 싶은 혜택',apps:'내가 챙기는 신청 기록'};
    $('sectionTitle').textContent=titles[view.tab]||titles.all;
    $('matchNotice').hidden=view.tab!=='matched';
    const prefs=snapshot.data.prefs;
    $('matchNotice').textContent=`${prefs.region||'모든 지역'} · ${prefs.category||'모든 분야'}. 관심 조건이 비슷한 정보이며 실제 수급 자격을 판정하지 않습니다.`;
    $('dataNote').textContent=feedError||`${window.SUPPORTPICK_DATA.coverage} 자료 조회 ${koreanTime(window.SUPPORTPICK_DATA.updatedAt)} KST · 신청 가능 여부는 공식 원문에서 확인하세요.`;
    if(view.tab==='apps'){renderApps();return;}
    const rows=C.filter(items,view,snapshot.data);
    $('resultCount').textContent=`${view.tab==='saved'?'저장한 혜택':'혜택 정보'} ${rows.length}건`;
    if(feedError){$('list').innerHTML=empty('자료를 확인하지 못했어요',feedError,'none');return;}
    if(view.tab==='matched'&&!prefs.region&&!prefs.category){$('list').innerHTML=empty('어떤 혜택에 관심 있으세요?','관심 지역과 분야를 선택하면 관련 정보를 먼저 볼 수 있어요.','preferences');return;}
    let body=rows.map(card).join('');
    if(view.tab==='saved'){
      const missing=snapshot.data.saved.filter(id=>!items.some(p=>p.id===id));
      body+=missing.map(id=>`<article class="benefit-card"><div class="card-content"><span class="badge">자료 미확인</span><h3>${esc(snapshot.data.apps[id]?.title||id)}</h3><p class="card-summary">현재 목록에서 이 혜택 자료를 찾지 못했습니다. 저장 기록은 보존됩니다.</p></div></article>`).join('');
      $('resultCount').textContent=`저장 ${snapshot.data.saved.length}건 · 현재 검색 결과 ${rows.length}건${missing.length?' · 자료 미확인 '+missing.length+'건':''}`;
    }
    $('list').innerHTML=body||empty(view.tab==='saved'?'저장한 혜택이 없어요':'조건에 맞는 정보가 없어요',view.tab==='saved'?'관심 혜택의 저장 버튼을 눌러 다시 확인하세요.':'검색 조건을 바꾸거나 공식 창구에서 더 많은 정보를 확인해보세요.',view.tab==='saved'?'all':'reset');
  }
  function renderDetail(){
    let id='';try{id=decodeURIComponent(location.hash.slice(9));}catch(e){}
    const p=items.find(x=>x.id===id);
    if(!p){$('detailSection').innerHTML='<button class="quiet back-button" data-back>← 목록으로</button>'+empty('혜택 자료를 찾지 못했어요','목록으로 돌아가 공식 정보를 다시 확인하세요.','all');return;}
    document.title=p.title+' | 지원금픽';
    const isSaved=snapshot.data.saved.includes(p.id);
    const fields=[['지원대상',p.target],['지원내용',p.support],['신청방법',p.method],['구비서류',p.documents],['문의처',p.contact]];
    $('detailSection').innerHTML=`<button class="quiet back-button" data-back>← 목록으로 돌아가기</button><article class="detail-header"><span class="category-badge">${esc(p.category)}</span> <span class="badge">${esc(C.status(p))}</span><h2 id="detailTitle" tabindex="-1">${esc(p.title)}</h2><p>${esc(p.organization)} · ${esc(p.region)}</p><dl class="card-meta"><dt>신청기간</dt><dd>${esc(p.period)}</dd><dt>지원방식</dt><dd>${esc(p.supportType)}</dd><dt>자료조회</dt><dd>${esc(koreanTime(p.checkedAt))} KST</dd></dl><p class="context-note">아래 내용은 공식 API에서 조회한 안내입니다. 실제 접수 여부·금액·대상은 최신 공식 공고와 대조해 확인하세요.</p><div class="detail-actions"><a class="primary" href="${esc(p.officialUrl)}" target="_blank" rel="noopener noreferrer">정부24 공식 안내 확인 ↗</a><button class="quiet" data-save="${esc(p.id)}" aria-pressed="${isSaved}">${isSaved?'★ 저장됨':'☆ 관심 저장'}</button><button class="quiet" data-track="${esc(p.id)}">내 신청에 기록</button></div></article>${fields.map(([title,value])=>`<section class="detail-block"><h3>${title}</h3><p class="source-text">${esc(value||'공식 안내 확인')}</p></section>`).join('')}<section class="detail-block"><h3>정보 출처</h3><p class="source-meta">${esc(p.source)} · 서비스 ID ${esc(p.id)}<br>출처 수정일 ${esc(p.sourceUpdatedAt)} · 조회 ${esc(koreanTime(p.checkedAt))} KST<br>API 조회 성공과 실제 신청 가능 여부는 별개입니다.</p><a href="${esc(p.officialUrl)}" target="_blank" rel="noopener noreferrer">공식 원문 다시 확인 ↗</a></section>`;
  }
  function renderApps(){
    const records=Object.entries(snapshot.data.apps).sort((a,b)=>b[1].updatedAt.localeCompare(a[1].updatedAt));
    $('resultCount').textContent=`신청 준비·진행 기록 ${records.length}건`;
    $('dataNote').textContent='직접 입력하는 개인 메모입니다. 공식 접수·선정 결과와 자동으로 연결되지 않습니다.';
    $('list').innerHTML=records.length?records.map(([id,a])=>{
      const d=drafts.get(id)||a,p=items.find(x=>x.id===id);
      return `<article class="tracker-card"><h3>${p?`<button class="title-link" data-detail="${esc(id)}">${esc(a.title)}</button>`:esc(a.title)}</h3><p>마지막 저장 ${esc(koreanTime(a.updatedAt))} KST${p?'':' · 현재 자료 미확인'}</p><form data-app-form="${esc(id)}"><div class="tracker-grid"><label>신청 단계<select name="stage">${C.STAGES.map(s=>`<option${s===d.stage?' selected':''}>${s}</option>`).join('')}</select></label><label>나의 준비 메모<textarea name="note" maxlength="6000" placeholder="준비할 서류, 확인할 내용을 기록하세요">${esc(d.note)}</textarea></label><button class="primary" type="submit">기록 저장</button></div><span class="draft-indicator" data-draft="${esc(id)}">${drafts.has(id)?'저장하지 않은 변경이 있어요':''}</span></form></article>`;
    }).join(''):empty('아직 신청 기록이 없어요','혜택의 ‘신청 준비하기’를 눌러 준비할 내용을 챙겨보세요.','all');
  }
  function openPreferences(){const p=snapshot.data.prefs;$('prefRegion').value=p.region;$('prefCategory').value=p.category;$('preferencesError').textContent='';$('preferencesDialog').showModal();}
  function openDetail(id){view.scroll=window.scrollY;remember();detailFromList=true;history.pushState({supportpickDetail:true},'', '#benefit='+encodeURIComponent(id));render();window.scrollTo(0,0);$('detailTitle')?.focus({preventScroll:true});}
  function back(){if(detailFromList){history.back();return;}history.replaceState(null,'',location.pathname+location.search);render();window.scrollTo(0,view.scroll||0);}
  function reset(){view={...view,query:'',category:'',region:'',supportType:'',sort:'updated',scroll:0};remember();render();}
  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.tab){document.title='지원금픽 · 한눈에 보는 생활혜택';setTab(b.dataset.tab);}
    if(b.hasAttribute('data-category')){view.category=b.dataset.category;remember();render();}
    if(b.dataset.detail)openDetail(b.dataset.detail);
    if(b.hasAttribute('data-back'))back();
    if(b.hasAttribute('data-show-all'))setTab('all');
    if(b.hasAttribute('data-reset'))reset();
    if(b.hasAttribute('data-open-preferences'))openPreferences();
    if(b.hasAttribute('data-close-dialog'))b.closest('dialog').close();
    if(b.dataset.save){const id=b.dataset.save;if(change(s=>{s.saved=s.saved.includes(id)?s.saved.filter(x=>x!==id):[...s.saved,id];return s;}))toast(snapshot.data.saved.includes(id)?'관심 혜택에 저장했어요.':'관심 저장을 해제했어요.');}
    if(b.dataset.track){const id=b.dataset.track,p=items.find(x=>x.id===id);if(!p)return;if(!C.own(snapshot.data.apps,id)&&!change(s=>{s.apps[id]={title:p.title,stage:'관심',note:'',updatedAt:new Date().toISOString()};return s;}))return;setTab('apps');toast('이곳에서 신청 준비 상황을 직접 기록하세요.');}
  });
  $('query').addEventListener('input',e=>{view.query=e.target.value;remember();render();});
  $('searchForm').addEventListener('submit',e=>{e.preventDefault();render();});
  for(const [id,key] of [['region','region'],['supportType','supportType'],['sort','sort']])$(id).addEventListener('change',e=>{view[key]=e.target.value;remember();render();});
  $('filterToggle').onclick=()=>{const expanded=$('filterToggle').getAttribute('aria-expanded')!=='true';$('filterToggle').setAttribute('aria-expanded',String(expanded));$('filterPanel').hidden=!expanded;};
  $('resetFilters').onclick=reset;$('heroMatch').onclick=openPreferences;$('preferencesButton').onclick=openPreferences;
  $('preferencesForm').onsubmit=e=>{e.preventDefault();try{persist({...snapshot.data,prefs:{region:$('prefRegion').value,category:$('prefCategory').value}});$('preferencesDialog').close();setTab('matched');toast('관심 조건을 저장했어요.');}catch(error){$('preferencesError').textContent=error.message;}};
  document.addEventListener('input',e=>{const form=e.target.closest('[data-app-form]');if(!form)return;drafts.set(form.dataset.appForm,{stage:form.elements.stage.value,note:form.elements.note.value});form.querySelector('[data-draft]').textContent='저장하지 않은 변경이 있어요';});
  document.addEventListener('submit',e=>{const form=e.target.closest('[data-app-form]');if(!form)return;e.preventDefault();const id=form.dataset.appForm,d={stage:form.elements.stage.value,note:form.elements.note.value};try{persist({...snapshot.data,apps:{...snapshot.data.apps,[id]:{...snapshot.data.apps[id],...d,updatedAt:new Date().toISOString()}}});drafts.delete(id);render();toast('신청 기록을 저장했어요.');}catch(error){toast(error.message);warn(error.message);}});
  $('recordsButton').onclick=()=>{$('recordsError').textContent='';$('recordsDialog').showModal();};
  function backupText(){return C.exportBackup(C.load(localStorage).data);}
  function restoreText(text){persist(C.merge(snapshot.data,C.importBackup(text)));render();$('recordsError').textContent='';toast('기존 기록을 보존하며 백업을 가져왔어요.');}
  $('showBackupText').onclick=()=>{try{$('backupText').value=backupText();$('backupText').focus();$('backupText').select();$('recordsError').textContent='';}catch(e){$('recordsError').textContent=e.message;}};
  $('importTextButton').onclick=()=>{try{restoreText($('backupText').value);}catch(e){$('recordsError').textContent=e.message;}};
  $('exportButton').onclick=()=>{try{const text=backupText();$('backupText').value=text;const blob=new Blob([text],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='supportpick-records-'+new Date().toISOString().slice(0,10)+'.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);toast('백업 다운로드를 요청했어요. 저장한 파일을 확인하세요.');}catch(e){$('recordsError').textContent=e.message;}};
  $('importInput').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>2*1024*1024)throw Error('백업은 2MB 이하의 JSON 파일만 가져올 수 있습니다.');restoreText(await file.text());}catch(error){$('recordsError').textContent=error.message;}finally{e.target.value='';}};
  window.addEventListener('popstate',()=>{render();if(!location.hash.startsWith('#benefit=')){document.title='지원금픽 · 한눈에 보는 생활혜택';requestAnimationFrame(()=>window.scrollTo(0,view.scroll||0));}});
  window.addEventListener('hashchange',()=>render());
  window.addEventListener('storage',e=>{if(e.key!==C.KEY)return;if(drafts.size){warn('다른 탭에서 기록이 변경되었습니다. 입력 중인 메모를 보관한 뒤 새로고침하세요.');return;}try{snapshot=C.load(localStorage);render();toast('다른 탭에서 변경한 기록을 반영했어요.');}catch(error){writable=false;warn(error.message);}});
  window.addEventListener('beforeunload',e=>{if(drafts.size){e.preventDefault();e.returnValue='';}});
  render();if(!location.hash)requestAnimationFrame(()=>window.scrollTo(0,view.scroll||0));
})();
