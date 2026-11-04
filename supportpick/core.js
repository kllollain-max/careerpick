/* SupportPick records are isolated from CareerPick even on the same origin. */
(function (root) {
  'use strict';
  const KEY='supportpick:records:v1', RECOVERY='supportpick:recovery:v1';
  const CATEGORIES=['생활안정','주거·자립','보육·교육','고용·창업','소상공인','보건·의료'];
  const REGIONS=['강원','서울','경기','인천','부산','대구','광주','대전','울산','세종','충북','충남','전북','전남','경북','경남','제주'];
  const STAGES=['관심','서류 준비','접수 완료','결과 확인','종료'];
  const plain=v=>!!v && typeof v==='object' && !Array.isArray(v) && Object.getPrototypeOf(v)===Object.prototype;
  const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
  const idOK=id=>typeof id==='string' && /^[A-Za-z0-9:_-]{1,100}$/.test(id) && !['__proto__','constructor','prototype'].includes(id);
  const blank=()=>({version:1,revision:0,saved:[],apps:{},prefs:{region:'',category:''}});
  function validate(data){
    if(!plain(data)||data.version!==1||!Number.isSafeInteger(data.revision)||data.revision<0||!Array.isArray(data.saved)||!plain(data.apps)||!plain(data.prefs))throw Error('지원금픽 기록 형식이 올바르지 않습니다.');
    if(data.saved.length>2000||Object.keys(data.apps).length>2000||data.saved.some(id=>!idOK(id)))throw Error('기록 항목을 확인할 수 없습니다.');
    if(!['',...REGIONS].includes(data.prefs.region)||!['',...CATEGORIES].includes(data.prefs.category))throw Error('관심 조건이 올바르지 않습니다.');
    const apps={};
    for(const [id,a] of Object.entries(data.apps)){
      if(!idOK(id)||!plain(a)||!STAGES.includes(a.stage)||typeof a.note!=='string'||a.note.length>6000||typeof a.title!=='string'||a.title.length>300||typeof a.updatedAt!=='string'||!Number.isFinite(Date.parse(a.updatedAt)))throw Error('신청 기록을 확인할 수 없습니다.');
      apps[id]={stage:a.stage,note:a.note,title:a.title,updatedAt:a.updatedAt};
    }
    return {version:1,revision:data.revision,saved:[...new Set(data.saved)],apps,prefs:{region:data.prefs.region,category:data.prefs.category}};
  }
  function load(storage){
    let raw;try{raw=storage.getItem(KEY);}catch(e){throw Error('브라우저의 기록 저장소에 접근할 수 없습니다.');}
    if(raw===null)return {raw:null,data:blank()};
    try{return {raw,data:validate(JSON.parse(raw))};}catch(e){throw Error('기존 지원금픽 기록을 읽을 수 없습니다. 원문을 보존했으며 덮어쓰지 않습니다.');}
  }
  function save(storage,expectedRaw,next){
    const previous=load(storage);
    if(previous.raw!==expectedRaw)throw Error('다른 탭에서 기록이 변경되었습니다. 입력 중인 내용을 보관한 뒤 새로고침하세요.');
    const validated=validate({...next,version:1,revision:previous.data.revision+1});
    const raw=JSON.stringify(validated);
    try{
      if(previous.raw!==null){storage.setItem(RECOVERY,previous.raw);if(storage.getItem(RECOVERY)!==previous.raw)throw Error('recovery');}
      if(storage.getItem(KEY)!==expectedRaw)throw Error('conflict');
      storage.setItem(KEY,raw);
      if(storage.getItem(KEY)!==raw)throw Error('readback');
    }catch(e){throw Error('기록 저장을 확인하지 못했습니다. 입력한 내용을 보관하고 다시 시도하세요.');}
    return {raw,data:validated};
  }
  function merge(existing,incoming){
    const a=validate(existing),b=validate(incoming),apps={...b.apps,...a.apps};
    return validate({...a,saved:[...new Set([...a.saved,...b.saved])],apps,prefs:a.prefs.region||a.prefs.category?a.prefs:b.prefs});
  }
  function exportBackup(data){return JSON.stringify({format:'supportpick-backup',version:1,exportedAt:new Date().toISOString(),data:validate(data)},null,2);}
  function importBackup(text){if(typeof text!=='string'||new TextEncoder().encode(text).length>2*1024*1024)throw Error('백업은 2MB 이하의 JSON만 가져올 수 있습니다.');const b=JSON.parse(text);if(!plain(b)||b.format!=='supportpick-backup'||b.version!==1)throw Error('지원금픽 전용 백업을 선택하세요.');return validate(b.data);}
  function safeURL(value){
    try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password)return '';return ['gov.kr','go.kr'].some(s=>u.hostname===s||u.hostname.endsWith('.'+s))?u.href:'';}catch(e){return '';}
  }
  function day(value){return new Date(value).toLocaleDateString('sv-SE',{timeZone:'Asia/Seoul'});}
  function validDate(value){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return false;
    const d=new Date(value+'T00:00:00+09:00');return Number.isFinite(+d)&&day(d)===value;
  }
  function status(item,now=new Date()){
    if(validDate(item.endDate)&&item.endDate<day(now))return '안내 기한 경과';
    if(validDate(item.startDate)&&item.startDate>day(now))return '안내 기간 전';
    // A listed future end date or API success is not proof that applications are open.
    return '원문 확인 필요';
  }
  function matchReasons(item,prefs){
    const reasons=[];
    if(prefs.region){if(item.region!=='전국'&&item.region!==prefs.region)return null;reasons.push(item.region==='전국'?'전국 대상 안내 · 지역별 조건 확인':prefs.region+' 지역 정보');}
    if(prefs.category){if(item.category!==prefs.category)return null;reasons.push(prefs.category+' 관심 분야');}
    return reasons;
  }
  function filter(items,view,records){
    const query=String(view.query||'').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return items.filter(p=>{
      const text=[p.title,p.organization,p.summary,p.target,p.category,p.region].join(' ').toLocaleLowerCase();
      return query.every(q=>text.includes(q))&&(!view.category||p.category===view.category)&&(!view.region||p.region==='전국'||p.region===view.region)&&(!view.supportType||p.supportType===view.supportType)&&(view.tab!=='saved'||records.saved.includes(p.id))&&(view.tab!=='matched'||matchReasons(p,records.prefs)!==null);
    }).sort((a,b)=>view.sort==='title'?a.title.localeCompare(b.title,'ko'):view.sort==='deadline'?(validDate(a.endDate)?a.endDate:'9999').localeCompare(validDate(b.endDate)?b.endDate:'9999'):String(b.checkedAt||'').localeCompare(String(a.checkedAt||'')));
  }
  function parseFeed(feed){
    if(!plain(feed)||feed.schemaVersion!==1||!Array.isArray(feed.items)||!Number.isFinite(Date.parse(feed.updatedAt)))throw Error('혜택 자료를 읽지 못했습니다. 잠시 후 다시 확인하세요.');
    const ids=new Set();return feed.items.map(p=>{
      if(!plain(p)||!idOK(p.id)||ids.has(p.id)||typeof p.title!=='string'||!p.title||!safeURL(p.officialUrl)||typeof p.category!=='string'||typeof p.region!=='string'||typeof p.supportType!=='string'||!Number.isFinite(Date.parse(p.checkedAt)))throw Error('혜택 자료의 출처 또는 항목을 확인할 수 없습니다.');
      ids.add(p.id);return {...p,officialUrl:safeURL(p.officialUrl)};
    });
  }
  const api={KEY,RECOVERY,CATEGORIES,REGIONS,STAGES,blank,validate,load,save,merge,exportBackup,importBackup,safeURL,status,filter,parseFeed,matchReasons,idOK,own,validDate};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SupportPick=api;
})(typeof window!=='undefined'?window:globalThis);
