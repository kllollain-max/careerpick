/* Pure personal planning rules. No delivery, account sync or storage side effects. */
(function(root,factory){const api=factory();if(typeof module==='object')module.exports=api;else root.CPManage=api;})(globalThis,()=>{
'use strict';
const stages=['plan','prepare','applied','doc','exam','itv','pass','fail','withdrawn'];
const terminal=s=>['pass','fail','withdrawn'].includes(s);
const date=v=>{if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v))return '';const d=new Date(v+'T00:00:00Z');return Number.isFinite(+d)&&d.toISOString().slice(0,10)===v?v:'';};
const day=now=>new Date(+now+32400000).toISOString().slice(0,10);
const count=v=>/^\d+$/.test(String(v??''))?Number(v):null;
function priority(a,b){const reg=p=>(p.emp||[]).includes('정규직')?1:0;return reg(b)-reg(a)||(count(b.n)??-1)-(count(a.n)??-1);}
function events(a,p,now=new Date()){
 if(terminal(a.st))return [];
 const out=[];for(const[k,label]of [['submit','서류 제출 · 직접 입력'],['exam','필기 · 직접 입력'],['itv','면접 · 직접 입력']]){const d=date(a[k]);if(d)out.push({date:d,kind:k,label,source:'user',past:d<day(now)});}
 // ALIO publication dates never become application deadline reminders.
 const due=p?.due||a.due,isPublication=p?p.alio===true:a.dueIsPublication!==false;
 if(['plan','prepare'].includes(a.st)&&due&&!isPublication){const d=typeof due==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(due)?date(due):Number.isFinite(+new Date(due))?day(new Date(due)):'';if(d)out.push({date:d,kind:'due',label:'접수마감 자료 · 원문 확인',source:'notice',past:d<day(now)});}
 return out.sort((a,b)=>a.date.localeCompare(b.date));
}
function next(a,p,now=new Date()){return events(a,p,now).find(e=>!e.past)||null;}
function transition(old,stage,now=Date.now()){
 if(!stages.includes(stage))throw Error('지원 단계 확인 필요');
 const result={...old,st:stage,upd:now};
 if(stage!==old.st)result.stageHistory=[...(Array.isArray(old.stageHistory)?old.stageHistory:[]),{from:old.st||'plan',to:stage,at:now}];
 return result; // Never marks preparation items complete as a side effect.
}
return{stages,terminal,date,day,count,priority,events,next,transition};
});
