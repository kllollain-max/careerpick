/* Homepage presentation rules. No storage writes or network requests. */
(function(root){
  'use strict';
  const day = d => new Date(+d + 9*3600000).toISOString().slice(0,10);
  const date = v => {
    if(typeof v==='string' && /^\d{4}-\d{2}-\d{2}$/.test(v)){
      const d=new Date(v+'T00:00:00+09:00'); return Number.isFinite(+d) && day(d)===v ? d:null;
    }
    const d=v instanceof Date?v:new Date(v);return v && Number.isFinite(+d)?d:null;
  };
  function deadline(p, now = new Date()){
    const due = date(p.due);
    if(p.cleaneye && ['expired','cancelled'].includes(p.receptionState))return {cls:'closed',big:p.receptionState==='cancelled'?'취소':'마감',n:Infinity};
    const uncertain=p.cleaneye && ['verification_pending','source_error','invalid_date'].includes(p.receptionState);
    if(!due) return uncertain ? {cls:'verify',big:'상태 확인',n:Infinity} : null;
    const exact=p.dueHasTime===true && !(typeof p.due==='string' && /^\d{4}-\d{2}-\d{2}$/.test(p.due));
    const n = Math.round((Date.parse(day(due)) - Date.parse(day(now))) / 86400000);
    if(n < 0 || (exact && +now >= +due)) return {cls:'closed',big:'마감',n:Infinity};
    if(uncertain)return {cls:'verify',big:'상태 확인',n:Infinity};
    const start = date(p.start || p.startDate);
    if(start && (/^\d{4}-\d{2}-\d{2}$/.test(String(p.start || p.startDate)) ? String(p.start || p.startDate) > day(now) : +start > +now)) return {cls:'upcoming',big:'접수 예정',n};
    if(n === 0 && !exact) return {cls:'verify',big:'시각 확인',n:0};
    return {cls:n <= 3 ? 'hot':'open',big:n === 0 ? 'D-DAY':`D-${n}`,n};
  }
  function sector(p){
    if(p.type !== 'j') return 'content';
    if(/공무직|무기계약/.test([p.cleaneye ? '' : p.title,...(p.emp||[])].join(' '))) return 'service';
    if(p.enterprise && p.group && p.group !== '기타') return 'enterprise';
    if(p.cleaneye || p.gojobs || p.alio || p.alioUrl || /공공기관|기관 공식/.test(p.cat||'')) return 'public';
    return 'other';
  }
  function employment(p){
    const values = p.emp || [];
    return [...new Set(values.flatMap(v => /무기계약|공무직/.test(v) ? ['무기계약직'] : /비정규|계약|기간제/.test(v) ? ['비정규직'] : /인턴/.test(v) ? ['인턴'] : /^정규직$/.test(v) ? ['정규직'] : []))];
  }
  function career(p){
    const raw = [p.career,...(p.emp||[])].filter(Boolean).join(' ');
    return ['신입','경력'].filter(v => raw.includes(v));
  }
  function matches(p, state){
    return (!state.sector || sector(p) === state.sector) && (!state.employment || employment(p).includes(state.employment)) && (!state.career || career(p).includes(state.career));
  }
  function enterprise(j){
    if(!j || j.status!=='verified' || !j.id || !j.company || !j.title || !date(j.deadline) || +date(j.deadline)<=Date.now() || !/^https:\/\//i.test(j.url||'')) return null;
    return {id:j.id,type:'j',enterprise:true,group:j.group,cat:'기업 채용',org:j.company,title:j.title,url:j.url,src:j.url,career:j.career,region:j.location||'',emp:j.employment?[j.employment]:[],edu:[],pub:date(j.first_seen_at)||new Date(0),due:date(j.deadline),dueHasTime:true};
  }
  function work24(j){
    if(!j || j.status!=='verified' || !j.id || !j.company || !j.title || !date(j.deadline))return null;
    try {const u=new URL(j.url);if(u.protocol!=='https:' || u.username || u.password || !/(^|\.)work24\.go\.kr$|(^|\.)work\.go\.kr$/.test(u.hostname))return null;}catch(e){return null;}
    if(String(j.deadline).slice(0,10)<=day(new Date()))return null;
    return {id:'work24:'+j.id,type:'j',work24:true,cat:'고용24 공식 공고',org:j.company,title:j.title,
      url:j.url,src:j.url,region:j.region||'',career:j.career||'',emp:[],edu:[],pub:date(j.posted)||date(j.first_seen_at)||new Date(0),
      due:date(j.deadline),dueHasTime:false};
  }
  function cleaneyeUrl(value){
    try{
      const u=new URL(value);
      return u.protocol==='https:' && !u.username && !u.password && !u.port && ['job.cleaneye.go.kr','www.job.cleaneye.go.kr'].includes(u.hostname) ? u.href : '';
    }catch(e){return '';}
  }
  function cleaneye(p){
    if(!p || p.cleaneye!==true || p.type!=='j' || !/^cleaneye-[A-Za-z0-9][A-Za-z0-9._:-]{0,118}$/.test(p.id||'') || !cleaneyeUrl(p.url))return null;
    const detail=p.cleaneyeDetail && typeof p.cleaneyeDetail==='object' && !Array.isArray(p.cleaneyeDetail) ? p.cleaneyeDetail : {};
    return {...p,source:'클린아이 잡플러스',url:cleaneyeUrl(p.url),src:cleaneyeUrl(p.url),cat:p.cat||'지방공공기관 채용',
      cleaneyeDetail:Object.fromEntries(Object.entries(detail).filter(([k,v])=>/[가-힣]/.test(k) && (typeof v==='string' || typeof v==='number' && Number.isFinite(v))))};
  }
  function noticeKey(p){
    if(p.alio && /^a\d+$/.test(String(p.id||''))) return String(p.id).slice(1);
    for(const v of [p.alioUrl,p.url,p.src]){
      try{const u=new URL(v);const id=u.searchParams.get('idx');if(/(^|\.)job\.alio\.go\.kr$/i.test(u.hostname) && /^\d+$/.test(id||''))return id;}catch(e){}
    }
    return '';
  }
  function identity(p){
    const id=noticeKey(p);if(id)return 'alio:'+id;
    try{const u=new URL(p.url);u.hash='';return u.href.replace(/\/$/,'');}catch(e){return 'id:'+p.id;}
  }
  function receptionState(p, now=new Date()){
    const status=p.verificationStatus || p.receptionState;
    if(status==='source_error' || p.sourceFetchOk===false || p.sourceError)return 'source_error';
    const malformed=v=>typeof v==='string' && v!=='' && (!/^\d{4}-\d{2}-\d{2}(?:T.+)?$/.test(v) || !date(v.slice(0,10)));
    const due=date(p.due),start=date(p.start || p.startDate);
    if(status==='invalid_date' || malformed(p.due) || malformed(p.start || p.startDate))return 'invalid_date';
    if((p.due && !due) || ((p.start || p.startDate) && !start) || (due && start && +start>+due))return 'invalid_date';
    if(status==='expired' || (due && (day(due)<day(now) || (p.dueHasTime===true && !/^\d{4}-\d{2}-\d{2}$/.test(String(p.due)) && +due<=+now))))return 'expired';
    if(status==='cancelled')return 'cancelled';
    if(start && +start>+now)return 'upcoming';
    if(!due || (day(due)===day(now) && p.dueHasTime!==true))return 'verification_pending';
    return ['verified','verified_open'].includes(status)?'verified_open':'verification_pending';
  }
  // Explicitly reviewed identities; supporting official documents are in
  // docs/collection-recovery/notice-identity-evidence-20261030.json.
  // Never infer cross-source identity from institution/title/deadline alone.
  const reviewedNotices = [
    {alio:'a305872',institution:'m7110dd3748cabc2b',seq:'12692',number:'2026-56',count:'6',title:'2026년도 한국임업진흥원 제3차 인재채용(보훈특별고용) 공고'},
    {alio:'a306052',institution:'mddc0be9c3f7638ae',seq:'12698',number:'2026-57',count:'7',title:'2026년도 한국임업진흥원 제4차 인재채용(공무직) 공고'}
  ];
  const normalized = v => String(v||'').normalize('NFKC').replace(/\s+/g,'');
  function unifyNotices(input){
    const rows=input.map(p=>({...p})),removed=new Set(),pending=[];
    for(const proof of reviewedNotices){
      const a=rows.find(p=>p.id===proof.alio && p.alio),m=rows.find(p=>p.id===proof.institution && p.monitor);
      if(!a || !m)continue;
      const institutionUrl='https://kllollain-max.github.io/kofpi.html?seq='+proof.seq;
      let alioUrlValid=false;
      try{const u=new URL(a.alioUrl || a.url);alioUrlValid=u.protocol==='https:' && u.hostname==='job.alio.go.kr' && u.searchParams.get('idx')===proof.alio.slice(1);}catch(e){}
      const valid=alioUrlValid && noticeKey(a)===proof.alio.slice(1) && normalized(a.org)==='한국임업진흥원' && normalized(m.org)===normalized(a.org)
        && normalized(a.title)===normalized(proof.title) && normalized(m.title)===normalized(proof.title)
        && String(a.n)===proof.count && (m.n==null || String(m.n)===proof.count)
        && date(a.due) && date(m.due) && day(date(a.due))==='2026-11-02' && day(date(m.due))==='2026-11-02'
        && String(m.start).slice(0,10)==='2026-10-26' && m.url===institutionUrl
        && ['verified','verified_open'].includes(m.verificationStatus)
        && (!m.officialNoticeNumber || m.officialNoticeNumber===proof.number);
      if(!valid){pending.push([a.id,m.id]);continue;}
      a.sourceIds=[a.id,m.id];
      a.sourceRecords=[{...a,sourceRecords:undefined},{...m}];
      a.officialSources=[{label:'잡알리오 공식 공고',url:a.alioUrl || a.url},{label:'기관 공식 원문',url:institutionUrl}];
      a.officialNoticeNumber=proof.number;
      a.start=m.start; // actual reception start, not the ALIO publication date
      removed.add(m);
    }
    for(const a of rows.filter(p=>noticeKey(p))){
      for(const m of rows.filter(p=>p.monitor && !removed.has(p))){
        if(normalized(a.org)===normalized(m.org) && normalized(a.title)===normalized(m.title) && date(a.due) && date(m.due) && day(date(a.due))===day(date(m.due))){
          a.identityVerification=m.identityVerification='verification_pending';
          if(!pending.some(pair=>pair[0]===a.id && pair[1]===m.id))pending.push([a.id,m.id]);
        }
      }
    }
    const ids=new Set(),noticeIds=new Set(),output=[];let exactRemoved=0;
    for(const p of rows){
      if(removed.has(p))continue;
      const key=noticeKey(p);
      if(ids.has(p.id) || (key && noticeIds.has(key))){exactRemoved++;continue;}
      ids.add(p.id);if(key)noticeIds.add(key);output.push(p);
    }
    return {rows:output,before:input.length,after:output.length,removed:removed.size+exactRemoved,crossSourceRemoved:removed.size,pending};
  }
  function parseFeed(data, field='posts', now=new Date()){
    if(!data || typeof data!=='object' || !Array.isArray(data[field])) throw Error('invalid_feed_schema');
    const issues=[],rows=[],states={};
    for(const raw of data[field]){
      if(!raw || typeof raw!=='object' || typeof raw.id!=='string' || !raw.id || typeof raw.title!=='string' || !raw.title){issues.push('invalid_row');continue;}
      const p=raw.cleaneye ? cleaneye(raw) : {...raw};
      if(!p){issues.push('invalid_row');continue;}
      if(raw.monitor){
        const status=receptionState(raw,now);states[status]=(states[status]||0)+1;p.receptionState=status;
        if(status!=='verified_open'){
          if(['verification_pending','invalid_date','source_error'].includes(status))issues.push(status);
          continue;
        }
      }
      for(const key of ['emp','edu','exam']){
        if(p[key]!==undefined && !Array.isArray(p[key]))issues.push('invalid_metadata');
        p[key]=Array.isArray(p[key])?p[key].filter(v=>typeof v==='string'):[];
      }
      for(const key of ['region','org','cat','desc','text'])if(typeof p[key]!=='string')p[key]='';
      p.pub=date(p.pub);
      if(!p.pub && !p.cleaneye){p.pub=new Date(0);issues.push('invalid_pub');}
      else if(!p.pub && raw.pub!=null && raw.pub!=='')issues.push('invalid_pub');
      if(p.cleaneye){
        p.start=date(raw.start) ? raw.start : null;
        if(raw.start && !p.start)issues.push('invalid_date');
      }
      p.due=date(p.due);if(raw.due && !p.due)issues.push('invalid_deadline');
      p.dueHasTime=!!p.due && raw.dueHasTime===true && !/^\d{4}-\d{2}-\d{2}$/.test(String(raw.due));
      rows.push(p);
    }
    return {rows,issues:[...new Set(issues)],states,updated:data.updated||data.updated_at||null,collectionStatus:data.collectionStatus||null};
  }
  function healthNotices(health, stamps, issues, now=new Date()){
    const names={cleaneye:'클린아이 잡플러스',gojobs:'나라일터',posts:'블로그',alio:'잡알리오',monitor:'기관 공고',enterprise:'기업 채용',detail:'상세 정보',work24:'고용24'};
    const notes=[];
    for(const [key,status] of Object.entries(health)){
      if(status==='disabled')notes.push(names[key]+' 수집이 비활성 상태입니다.');
      if(status==='not_collected')notes.push(names[key]+' 공고를 아직 수집하지 않았습니다.');
      if(key==='work24' && status==='awaiting_approval')notes.push('고용24 채용정보는 현재 API 이용 승인 대기 중입니다.');
      if(key==='work24' && status==='config_error')notes.push('고용24 채용정보 설정을 확인하지 못했습니다.');
      if(status==='error')notes.push(key==='work24'?'고용24 채용정보를 불러오지 못했습니다.':names[key]+' 데이터를 불러오지 못했습니다.');
      if(status==='ok' && key!=='detail'){
        const stamp=date(stamps[key]);
        if(!stamp || +stamp>+now+300000)notes.push(names[key]+' 갱신 시각을 확인할 수 없습니다.');
        else if(+now-+stamp>48*3600000)notes.push(names[key]+' 데이터가 48시간 이상 갱신되지 않았습니다.');
      }
      if(issues[key]?.includes('verification_pending'))notes.push(names[key]+'의 접수기간 미확인 공고는 검증 후 표시됩니다.');
      if(issues[key]?.includes('invalid_date'))notes.push(names[key]+'의 날짜 형식에 오류가 있어 확인이 필요합니다.');
      if(issues[key]?.includes('source_error'))notes.push(names[key]+'의 원문 확인·수집에 오류가 있습니다.');
      if(issues[key]?.some(v=>!['verification_pending','invalid_date','source_error'].includes(v)))notes.push(names[key]+' 일부 데이터에 오류가 있어 확인이 필요합니다.');
    }
    return notes;
  }
  function detailFields(p,det){
    if(!p.alio || !det || (det.recrutPblntSn && String(det.recrutPblntSn)!==noticeKey(p)))return {};
    const fields={};
    if(typeof det.recrutSeNm==='string' && det.recrutSeNm)fields.career=det.recrutSeNm;
    if(typeof det.workRgnNmLst==='string' && det.workRgnNmLst)fields.region=det.workRgnNmLst;
    const start=String(det.pbancBgngYmd||'');
    if(/^\d{8}$/.test(start)){
      const value=start.slice(0,4)+'-'+start.slice(4,6)+'-'+start.slice(6,8);if(date(value))fields.startDate=p.officialNoticeNumber && p.start ? p.start : value;
    }
    return fields;
  }
  const api = {deadline,sector,employment,career,matches,enterprise,work24,cleaneyeUrl,cleaneye,noticeKey,identity,receptionState,unifyNotices,parseFeed,healthNotices,detailFields};
  if(typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CPHome = api;
})(typeof window !== 'undefined' ? window : globalThis);
