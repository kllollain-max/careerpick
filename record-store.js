/* Local-only, verified writes. Existing keys and raw records remain compatible. */
(function(root,factory){const api=factory();if(typeof module==='object')module.exports=api;else root.CPStore=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  const object=x=>!!x&&typeof x==='object'&&!Array.isArray(x);
  const safeKey=k=>!['__proto__','prototype','constructor'].includes(k);
  const saved=x=>Array.isArray(x)&&x.every(id=>typeof id==='string'&&safeKey(id)&&id.length>0);
  const apps=x=>object(x)&&Object.entries(x).every(([id,a])=>safeKey(id)&&object(a)&&
    (a.st===undefined||['plan','applied','doc','exam','itv','pass','fail'].includes(a.st))&&
    ['title','org','url','memo','exam','itv','due'].every(k=>a[k]==null||typeof a[k]==='string')&&
    (a.ck==null||Array.isArray(a.ck)&&a.ck.every(c=>object(c)&&typeof c.t==='string')));
  const prefs=x=>object(x)&&['emp','edu','region','cat'].every(k=>x[k]===undefined||Array.isArray(x[k])&&x[k].every(v=>typeof v==='string'))&&(x.kw===undefined||typeof x.kw==='string');
  function read(storage,key,fallback,valid){
    try{const raw=storage.getItem(key),data=raw===null?fallback:JSON.parse(raw);if(!valid(data))throw Error('invalid');return{ok:true,data,raw};}
    catch(_){return{ok:false,data:fallback,error:'저장된 기록을 읽지 못했습니다. 원본은 보존했으며 덮어쓰지 않습니다. JSON 백업을 확인해 주세요.'};}
  }
  async function mutate(storage,key,fallback,valid,edit,locks){
    const work=()=>{
      const old=read(storage,key,fallback,valid);if(!old.ok)throw Error(old.error);
      const next=edit(JSON.parse(JSON.stringify(old.data)));
      if(!valid(next))throw Error('기록 형식을 확인해 주세요. 기존 기록은 변경하지 않았습니다.');
      const text=JSON.stringify(next);
      if(storage.getItem(key)!==old.raw)throw Error('다른 탭에서 기록이 변경됐습니다. 다시 열어 확인해 주세요.');
      // Verify a recoverable pre-write copy before changing or deleting any bucket.
      const checkpointKey='careerpick-record-checkpoints',checkpointRaw=storage.getItem(checkpointKey);
      let checkpoints;
      try{checkpoints=checkpointRaw===null?{version:1,records:{}}:JSON.parse(checkpointRaw);
        if(checkpoints.version!==1||!object(checkpoints.records))throw Error('checkpoint');
      }catch(_){throw Error('복구 사본을 읽지 못했습니다. 기존 기록을 변경하지 않았습니다. 원본 JSON 백업을 받아 주세요.');}
      checkpoints.records[key]={raw:old.raw,at:new Date().toISOString()};
      const checkpointText=JSON.stringify(checkpoints);
      try{storage.setItem(checkpointKey,checkpointText);
        if(storage.getItem(checkpointKey)!==checkpointText)throw Error('checkpoint');
        if(storage.getItem(key)!==old.raw)throw Error('conflict');
        storage.setItem(key,text);
      }catch(_){throw Error('기기 저장 실패: 저장 공간 또는 사이트 저장 권한을 확인해 주세요. 입력 내용은 화면에 남아 있습니다.');}
      if(storage.getItem(key)!==text)throw Error('저장 결과를 확인하지 못했습니다. 다시 열어 확인해 주세요.');
      return next;
    };
    return locks&&typeof locks.request==='function'?locks.request('careerpick-records',work):work();
  }
  function replaceApp(data,id,next,expected){
    if(JSON.stringify(data[id]??null)!==expected)throw Error('다른 탭에서 이 지원 기록이 변경됐습니다. 입력 내용을 복사한 뒤 기록을 다시 열어 주세요.');
    if(next===null)delete data[id];else data[id]=next;return data;
  }
  function exportRecords(storage,keys){
    const result={data:{},raw_records:{},invalid_keys:[],unavailable_keys:[]},validators={saved,apps,prefs};
    for(const key of keys){
      let raw;try{raw=storage.getItem(key);}catch(_){result.unavailable_keys.push(key);continue;}
      if(raw===null)continue;result.raw_records[key]=raw;
      try{const value=JSON.parse(raw);if(validators[key]&&!validators[key](value))throw Error('schema');result.data[key]=value;}
      catch(_){result.invalid_keys.push(key);}
    }
    return result;
  }
  return{read,mutate,replaceApp,saved,apps,prefs,exportRecords};
});
