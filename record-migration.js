/* Local-only, idempotent record migration. No network or account access. */
(function(root){
'use strict';
const keys=['prefs','spec','saved','apps','careerpick-import-archive'];
function object(v){return v!==null && typeof v==='object' && !Array.isArray(v);}
function safe(v,depth=0){
 if(depth>15)throw Error('기록 구조가 너무 깊습니다.');
 if(v && typeof v==='object')for(const k of Object.keys(v)){
  if(['__proto__','prototype','constructor'].includes(k))throw Error('허용되지 않는 데이터 키입니다.');
  safe(v[k],depth+1);
 }
}
function validate(backup){
 safe(backup);
 if(!object(backup)||backup.format!=='careerpick-backup'||backup.version!==1||!object(backup.data))throw Error('커리어픽 백업 형식이 아닙니다.');
 const d=backup.data;
 if(d.saved!==undefined && (!Array.isArray(d.saved)||d.saved.length>10000||d.saved.some(x=>typeof x!=='string'||!x||x.length>128)))throw Error('저장 공고 ID가 올바르지 않습니다.');
 if(d.apps!==undefined){
  if(!object(d.apps)||Object.keys(d.apps).length>10000)throw Error('지원 기록이 올바르지 않습니다.');
  for(const [id,a] of Object.entries(d.apps)){
   if(!id||id.length>128||!object(a)||!['plan','applied','doc','exam','itv','pass','fail'].includes(a.st))throw Error('지원 상태가 올바르지 않습니다.');
   for(const key of ['memo','title','org','url','exam','itv'])if(a[key]!==undefined && (typeof a[key]!=='string'||a[key].length>20000))throw Error('지원 기록 필드가 올바르지 않습니다.');
   if(a.ck!==undefined && !Array.isArray(a.ck))throw Error('체크리스트가 올바르지 않습니다.');
  }
 }
 for(const key of ['prefs','spec'])if(d[key]!==undefined&&!(key==='spec'&&d[key]===null)&&!object(d[key]))throw Error('맞춤 설정이 올바르지 않습니다.');
 if(d['careerpick-import-archive']!==undefined&&!Array.isArray(d['careerpick-import-archive']))throw Error('이전 보관 기록이 올바르지 않습니다.');
 return d;
}
function merge(current,incoming){
 const d=validate({format:'careerpick-backup',version:1,data:incoming});safe(current);
 const merged=JSON.parse(JSON.stringify(current)), conflicts=[];
 merged.saved=[...new Set([...(current.saved||[]),...(d.saved||[])])];
 merged.apps={...(current.apps||{})};
 for(const [id,a] of Object.entries(d.apps||{})){
  if(!Object.hasOwn(merged.apps,id))merged.apps[id]=a;
  else if(JSON.stringify(merged.apps[id])!==JSON.stringify(a)){
   const old=merged.apps[id];
   merged.apps[id]={...a,...old};
   if(a.memo && a.memo!==old.memo)conflicts.push(id);
   else if(JSON.stringify(old)!==JSON.stringify(a))conflicts.push(id);
  }
 }
 for(const key of ['prefs','spec'])if(d[key]!==undefined && current[key]===undefined)merged[key]=d[key];
 const archive=[...(current['careerpick-import-archive']||[]),...(d['careerpick-import-archive']||[])];
 const payload=JSON.stringify(Object.fromEntries(Object.entries(d).filter(([k])=>k!=='careerpick-import-archive')));
 if(!archive.some(x=>JSON.stringify(x)===payload))archive.push(JSON.parse(payload));
 merged['careerpick-import-archive']=[...new Map(archive.map(x=>[JSON.stringify(x),x])).values()];
 return {data:merged,conflicts,savedAdded:merged.saved.length-(current.saved||[]).length,appsAdded:Object.keys(merged.apps).length-Object.keys(current.apps||{}).length};
}
function apply(storage,backup){
 const d=validate(backup),originals={},current={};
 for(const k of keys){originals[k]=storage.getItem(k);if(originals[k]!==null)current[k]=JSON.parse(originals[k]);}
 const result=merge(current,d);
 try{
  // Local pre-import checkpoint, independent of the user's downloaded backup.
  storage.setItem('careerpick-before-import',JSON.stringify(current));
  for(const k of keys)if(result.data[k]!==undefined)storage.setItem(k,JSON.stringify(result.data[k]));
 }catch(e){
  for(const k of keys){try{originals[k]===null?storage.removeItem(k):storage.setItem(k,originals[k]);}catch(_) {}}
  throw Error('저장하지 못했습니다. 가져오기 전 다운로드한 백업을 보관하세요.');
 }
 return result;
}
const api={keys,validate,merge,apply};if(typeof module!=='undefined')module.exports=api;else root.CPRecords=api;
})(typeof window==='undefined'?{}:window);
