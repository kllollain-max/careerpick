/* Local-only record backup/import. No network, provider credentials or account sync. */
(function(root){
'use strict';
const keys=['prefs','spec','saved','apps','careerpick-import-archive'];
const recoveryKeys=['careerpick-record-checkpoints','careerpick-before-import'];
const journalKey='careerpick-before-import',maxBytes=16*1024*1024;
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const secretKey=k=>/(?:apikeys?|tokens?|password|authorization|privatekey|clientsecret|credentials?|secret)$/.test(String(k).replace(/[^a-z0-9]/gi,'').toLowerCase())||/^(?:alio|gojobs|mpmexam)key$/i.test(String(k).replace(/[^a-z0-9]/gi,''));
function safe(v,depth=0){
 if(depth>15)throw Error('기록 구조가 너무 깊습니다.');
 if(v&&typeof v==='object')for(const k of Object.keys(v)){
  if(['__proto__','prototype','constructor'].includes(k))throw Error('허용되지 않는 데이터 키입니다.');
  if(secretKey(k))throw Error('백업에 불필요한 인증 필드가 있습니다. 해당 필드를 제외한 개인 기록 백업을 사용하세요.');
  safe(v[k],depth+1);
 }
}
function stable(v){return JSON.stringify(canonical(v));}
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(object(v))return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v;}
function sourceOf(id,a={}){
 const inferred=/^a\d+$/.test(id)?'alio':/^gojobs-/.test(id)?'gojobs':/^work24:/.test(id)?'work24':/^saramin:/.test(id)?'saramin':'';
 if(a.source&&inferred&&a.source!==inferred)throw Error('출처와 공고 ID가 일치하지 않습니다.');
 return a.source||inferred||'unknown';
}
function validate(backup){
 safe(backup);
 if(!object(backup)||backup.format!=='careerpick-backup'||backup.version!==1||!object(backup.data))throw Error('지원하는 커리어픽 백업 형식·버전이 아닙니다.');
 if(backup.recovery_required===true)throw Error('미완료 가져오기 상태에서 생성된 백업입니다. 복구 사본을 먼저 확인하세요.');
 if((backup.invalid_keys||[]).length||(backup.unavailable_keys||[]).length)throw Error('손상 또는 읽지 못한 항목이 있는 부분 백업입니다. 원문을 복구한 뒤 가져오세요.');
 if(backup.service&&backup.service.id!=='careerpick')throw Error('다른 서비스의 백업입니다.');
 const d=backup.data;
 if(Object.keys(d).some(k=>!keys.includes(k)&&!recoveryKeys.includes(k)))throw Error('지원하지 않는 백업 항목이 있습니다. 기존 기록은 변경하지 않았습니다.');
 if(d.saved!==undefined&&(!Array.isArray(d.saved)||d.saved.length>10000||d.saved.some(x=>typeof x!=='string'||!x||x.length>128)))throw Error('저장 공고 ID가 올바르지 않습니다.');
 if(d.apps!==undefined){
  if(!object(d.apps)||Object.keys(d.apps).length>10000)throw Error('지원 기록이 올바르지 않습니다.');
  for(const [id,a]of Object.entries(d.apps)){
   if(!id||id.length>128||!object(a)||(a.st!==undefined&&!['plan','applied','doc','exam','itv','pass','fail'].includes(a.st)))throw Error('지원 상태가 올바르지 않습니다.');
   for(const k of ['memo','title','org','url','exam','itv','source'])if(a[k]!==undefined&&(typeof a[k]!=='string'||a[k].length>(k==='memo'?maxBytes:20000)))throw Error('지원 기록 필드가 올바르지 않습니다.');
   if(a.due!==undefined&&a.due!==null&&typeof a.due!=='string')throw Error('마감일 형식이 올바르지 않습니다.');
   if(a.ck!==undefined&&(!Array.isArray(a.ck)||a.ck.some(x=>!object(x)||typeof x.t!=='string'||(x.ph!==undefined&&!['pre','post'].includes(x.ph))||![0,1,false,true].includes(x.d))))throw Error('체크리스트가 올바르지 않습니다.');
   if(a.url&&!/^https?:\/\//i.test(a.url))throw Error('지원 기록 링크가 올바르지 않습니다.');
   sourceOf(id,a);
  }
 }
 for(const k of ['prefs','spec'])if(d[k]!==undefined&&!(k==='spec'&&d[k]===null)&&!object(d[k]))throw Error('맞춤 설정이 올바르지 않습니다.');
 if(d.prefs){for(const k of ['emp','edu','region','cat'])if(d.prefs[k]!==undefined&&(!Array.isArray(d.prefs[k])||d.prefs[k].some(v=>typeof v!=='string')))throw Error('맞춤 조건 배열이 올바르지 않습니다.');if(d.prefs.kw!==undefined&&typeof d.prefs.kw!=='string')throw Error('검색 조건이 올바르지 않습니다.');}
 if(d.spec)for(const k of ['want','lic','special'])if(d.spec[k]!==undefined&&(!Array.isArray(d.spec[k])||d.spec[k].some(v=>typeof v!=='string')))throw Error('스펙 배열이 올바르지 않습니다.');
 if(d['careerpick-import-archive']!==undefined&&(!Array.isArray(d['careerpick-import-archive'])||d['careerpick-import-archive'].some(v=>!object(v))))throw Error('이전 보관 기록이 올바르지 않습니다.');
 return Object.fromEntries(keys.filter(k=>d[k]!==undefined).map(k=>[k,d[k]]));
}
function counts(d){return{saved:(d.saved||[]).length,apps:Object.keys(d.apps||{}).length,memos:Object.values(d.apps||{}).filter(a=>a.memo).length,checklist_items:Object.values(d.apps||{}).reduce((n,a)=>n+(a.ck||[]).length,0),schedules:Object.values(d.apps||{}).reduce((n,a)=>n+Number(!!a.exam)+Number(!!a.itv),0),prefs:d.prefs?1:0,spec:d.spec?1:0,archives:(d['careerpick-import-archive']||[]).length};}
function merge(current,incoming){
 const d=validate({format:'careerpick-backup',version:1,data:incoming});validate({format:'careerpick-backup',version:1,data:current});
 const merged=JSON.parse(JSON.stringify(current)),conflicts=[],duplicates={saved:0,apps:0,prefs:0,spec:0};
 const existingSaved=new Set(current.saved||[]);duplicates.saved=(d.saved||[]).filter(x=>existingSaved.has(x)).length;
 merged.saved=[...new Set([...(current.saved||[]),...(d.saved||[])])];merged.apps={...(current.apps||{})};
 for(const [id,a]of Object.entries(d.apps||{})){
  if(!Object.hasOwn(merged.apps,id))merged.apps[id]=a;
  else if(stable(merged.apps[id])===stable(a))duplicates.apps++;
  else{
   conflicts.push(id);
   // Keep the existing record whole, even when a legacy ID has no reliable source.
   // Incoming fields cannot silently fill a different notice's missing metadata.
   // The complete incoming record is retained in the archive below.
  }
 }
 for(const k of ['prefs','spec'])if(d[k]!==undefined){if(current[k]===undefined||(k==='spec'&&current[k]===null))merged[k]=d[k];else if(stable(current[k])===stable(d[k]))duplicates[k]++;else conflicts.push(k);}
 const payload=Object.fromEntries(Object.entries(d).filter(([k])=>k!=='careerpick-import-archive'));
 const archive=[...(current['careerpick-import-archive']||[]),...(d['careerpick-import-archive']||[])];
 if(Object.keys(payload).length&&!archive.some(x=>stable(x)===stable(payload)))archive.push(payload);
 merged['careerpick-import-archive']=[...new Map(archive.map(x=>[stable(x),x])).values()];
 return{data:merged,conflicts,duplicates,savedAdded:merged.saved.length-existingSaved.size,appsAdded:Object.keys(merged.apps).length-Object.keys(current.apps||{}).length};
}
function snapshot(storage){const raw={},data={};for(const k of keys){raw[k]=storage.getItem(k);if(raw[k]!==null)data[k]=JSON.parse(raw[k]);}validate({format:'careerpick-backup',version:1,data});return{raw,data};}
function recoveryStatus(storage){
 try{const raw=storage.getItem(journalKey);if(raw===null)return{pending:false};const j=JSON.parse(raw);
  if(j.format!=='careerpick-before-import')return{pending:false,legacy:true};
  const pending=j.version!==1||!['complete','rolled_back'].includes(j.state);
  return{pending,state:j.state||'unknown',message:pending?'미완료 가져오기·복구 확인이 필요합니다. 원본을 백업하고 복구 사본을 확인하세요.':''};
 }catch(_){return{pending:true,state:'unreadable',message:'가져오기 복구 상태를 읽을 수 없습니다. 추가 저장을 중단하고 원본 백업을 보관하세요.'};}
}
function preview(storage,backup){
 const d=validate(backup),old=snapshot(storage),result=merge(old.data,d);
 if(recoveryStatus(storage).pending)throw Error('이전 가져오기 복구가 필요합니다. 먼저 복구 사본을 확인하세요.');
 const seen=new Set();let internalDuplicates=0;for(const id of d.saved||[]){if(seen.has(id))internalDuplicates++;seen.add(id);}
 return{version:backup.version,exportedAt:typeof backup.exported_at==='string'&&Number.isFinite(Date.parse(backup.exported_at))?backup.exported_at:null,counts:counts(d),savedAdded:result.savedAdded,appsAdded:result.appsAdded,duplicates:result.duplicates,internalDuplicates,conflicts:result.conflicts.length,invalid:0,originals:old.raw};
}
function checkedWrite(storage,key,value){storage.setItem(key,value);if(storage.getItem(key)!==value)throw Error('저장 후 재검증 실패');}
function verifyRaw(storage,raw){for(const k of keys)if(storage.getItem(k)!==raw[k])throw Error('저장 후 재검증 실패');}
function rollback(storage,originals){let ok=true;for(const k of keys)try{originals[k]===null?storage.removeItem(k):storage.setItem(k,originals[k]);if(storage.getItem(k)!==originals[k])ok=false;}catch(_){ok=false;}return ok;}
function apply(storage,backup,options={}){
 const d=validate(backup),old=snapshot(storage);
 if(recoveryStatus(storage).pending)throw Error('이전 가져오기 복구가 필요합니다. 기존 사본을 덮어쓰지 않았습니다.');
 if(options.expectedOriginals&&stable(old.raw)!==stable(options.expectedOriginals))throw Error('미리보기 후 다른 탭에서 기록이 변경됐습니다. 파일을 다시 선택해 비교하세요.');
 const result=merge(old.data,d),after={...old.raw};for(const k of keys)if(result.data[k]!==undefined)after[k]=JSON.stringify(result.data[k]);
 const journal={format:'careerpick-before-import',version:1,state:'prepared',created_at:new Date().toISOString(),exported_at:backup.exported_at||null,raw_records:old.raw,expected_after:after};
 // Failure before checkpoint verification cannot justify writing any active record.
 checkedWrite(storage,journalKey,JSON.stringify(journal));
 try{
  verifyRaw(storage,old.raw);
  for(const k of keys)if(after[k]!==old.raw[k])checkedWrite(storage,k,after[k]);
  verifyRaw(storage,after);
  journal.state='complete';journal.completed_at=new Date().toISOString();checkedWrite(storage,journalKey,JSON.stringify(journal));
 }catch(_){
  const restored=rollback(storage,old.raw);journal.state=restored?'rolled_back':'recovery_required';
  try{checkedWrite(storage,journalKey,JSON.stringify(journal));}catch(_){/* prepared checkpoint remains the durable hold */}
  throw Error(restored?'가져오기에 실패해 기존 기록으로 복구했습니다. 다운로드 백업을 보관하세요.':'가져오기 실패 후 일부 복구를 확인하지 못했습니다. 추가 저장을 중단하고 복구 사본으로 원상복구하세요.');
 }
 return result;
}
function recover(storage){
 const raw=storage.getItem(journalKey);let j;try{j=JSON.parse(raw);}catch(_){throw Error('복구 사본을 읽지 못했습니다. 원본 JSON 백업을 보관하세요.');}
 if(!j||j.format!=='careerpick-before-import'||j.version!==1||!object(j.raw_records)||!object(j.expected_after))throw Error('자동 복구를 지원하는 사본이 아닙니다. 원본 백업을 확인하세요.');
 const old={};for(const k of keys){if(!(k in j.raw_records)||(j.raw_records[k]!==null&&typeof j.raw_records[k]!=='string'))throw Error('복구 사본이 불완전합니다.');if(j.raw_records[k]!==null)old[k]=JSON.parse(j.raw_records[k]);}
 validate({format:'careerpick-backup',version:1,data:old});
 // A later legitimate edit must never be destroyed by an old checkpoint.
 for(const k of keys){const current=storage.getItem(k);if(current!==j.raw_records[k]&&current!==j.expected_after[k])throw Error('사본 생성 후 다른 변경이 있습니다. 자동 덮어쓰기를 중단했습니다. 현재 기록과 원본을 각각 백업하세요.');}
 if(!rollback(storage,j.raw_records))throw Error('원상복구를 확인하지 못했습니다. 원본 사본은 보존했습니다.');
 j.state='rolled_back';j.recovered_at=new Date().toISOString();checkedWrite(storage,journalKey,JSON.stringify(j));
 return{restored:true};
}
const api={keys,recoveryKeys,maxBytes,validate,merge,apply,preview,counts,recoveryStatus,recover,sourceOf};if(typeof module!=='undefined')module.exports=api;else root.CPRecords=api;
})(typeof window==='undefined'?{}:window);
