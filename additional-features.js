/* Pure additional-feature adapters. No storage, provider calls or calendar writes. */
(function(root,factory){const api=factory();if(typeof module==='object')module.exports=api;else root.CPExtras=api;})(globalThis,()=>{
'use strict';
const text=v=>String(v??'').replace(/<\/?(?:p|div|br|span|b|strong|em|ul|ol|li|table|tr|td|th|a)\b[^>]*>/gi,' ').replace(/&nbsp;/g,' ').trim();
const missing=v=>v===null||v===undefined||v===''||(Array.isArray(v)&&!v.length);
const value=v=>missing(v)?'미기재 · 공식 원문 확인':Array.isArray(v)?v.map(text).join(' · '):text(v);
function date(s){if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(s))return '';const d=new Date(s+'T00:00:00Z');return Number.isFinite(+d)&&d.toISOString().slice(0,10)===s?s:'';}
function next(s){if(!date(s))return '';return new Date(Date.parse(s+'T00:00:00Z')+86400000).toISOString().slice(0,10);}
function kstDay(v){if(typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v))return date(v);const d=new Date(v);if(!Number.isFinite(+d))return '';return new Date(+d+32400000).toISOString().slice(0,10);}
function url(v){try{if(/[\r\n]/.test(v))return '';const u=new URL(v);return ['https:','http:'].includes(u.protocol)?u.href:'';}catch(_){return '';}}
const escape=v=>String(v??'').replace(/\\/g,'\\\\').replace(/\r\n|\r|\n/g,'\\n').replace(/,/g,'\\,').replace(/;/g,'\\;');
function fold(line){const enc=new TextEncoder();let out='',row='',n=0;for(const c of line){const len=enc.encode(c).length;if(n+len>75){out+=row+'\r\n';row=' ';n=1;}row+=c;n+=len;}return out+row;}
function utc(v){if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(v)||!date(v.slice(0,10)))return '';const parts=v.match(/T(\d{2}):(\d{2})(?::(\d{2}))?/);if(!parts||+parts[1]>23||+parts[2]>59||+(parts[3]||0)>59)return '';const d=new Date(v);return Number.isFinite(+d)?d.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}/,''):'';}
function calendar(events,now=new Date()){
 const stamp=now.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}/,'');const lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//CareerPick//Selected Dates//KO','CALSCALE:GREGORIAN'];let count=0;const seen=new Set();
 for(const e of events){
  if(!e||!e.id||!e.kind||!e.scope)continue;
  const uid=encodeURIComponent([e.scope,e.id,e.kind].join('|'))+'@careerpick.local';if(seen.has(uid))continue;
  let start,end;
  if(e.timed===true){start=utc(e.start);end=utc(e.end||e.start);if(!start||!end||end<start)continue;start='DTSTART:'+start;end='DTEND:'+end;}
  else{const day=date(e.date),last=date(e.lastDate||e.date);if(!day||!last||last<day)continue;start='DTSTART;VALUE=DATE:'+day.replace(/-/g,'');end='DTEND;VALUE=DATE:'+next(last).replace(/-/g,'');}
  const revision=Number.isSafeInteger(e.revision)&&e.revision>=0?e.revision:0;
  const seq=Math.min(2147483647,Math.floor(revision/1000));
  lines.push('BEGIN:VEVENT','UID:'+uid,'DTSTAMP:'+stamp,'SEQUENCE:'+seq,start,end,'SUMMARY:'+escape(e.title));
  const description=['출처: '+(e.source||'사용자가 입력한 지원 일정'),'자료 확인: '+(e.checkedAt||'미확인'),'정확한 일정은 공식 공고에서 확인하세요. 자동 동기화되지 않으며 재가져오기 시 중복될 수 있습니다.'].join('\n');
  lines.push('DESCRIPTION:'+escape(description));const link=url(e.url);if(link)lines.push('URL:'+link);
  if(e.cancelled===true)lines.push('STATUS:CANCELLED');
  lines.push('END:VEVENT');seen.add(uid);count++;
 }
 lines.push('END:VCALENDAR');return {text:lines.map(fold).join('\r\n')+'\r\n',count};
}
function applications(apps,now=new Date()){
 const today=kstDay(now),out=[];
 for(const [id,a] of Object.entries(apps||{})){
  if(!a||['pass','fail'].includes(a.st))continue;
  for(const [kind,label,raw] of [['due','접수 마감',a.st==='plan'?a.due:null],['exam','필기',a.exam],['itv','면접',a.itv]]){
   if(!raw)continue;const day=kstDay(raw);if(!date(day)||day<today)continue;
   const verified=kind==='due'&&a.dueHasTime===true&&!!utc(raw);
   out.push({scope:'application',id,kind,date:day,timed:verified,start:raw,end:raw,title:'[커리어픽] '+label+' · '+(a.org||a.title||'공고 미확인'),url:a.url,source:'사용자가 저장한 지원 일정',checkedAt:'공식 변경 여부 재확인 필요',revision:Number.isSafeInteger(a.upd)?a.upd:0});
  }
 }
 return out;
}
function exactMention(body,name){
 const escaped=String(name).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 return new RegExp('(?:^|[^가-힣A-Za-z0-9])'+escaped+'(?=$|[^가-힣A-Za-z0-9]|이상|자격|소지|보유|취득|을|를|와|과|는|의)').test(text(body));
}
function certificateEvidence(d,name){
 const result=[];
 if(exactMention(d?.aplyQlfcCn,name))result.push('지원자격 원문 언급 · 필수 여부·예외 확인');
 if(exactMention([d?.prefCn,d?.prefCondCn].filter(Boolean).join('\n'),name))result.push('우대사항 원문 언급 · 직무별 적용 확인');
 return result;
}
function comparison(p,d={}){
 const reception=p.alio?'접수기간 미확인 · ALIO 공고 게시기간과 다름':value(p.start||p.startDate)+' ~ '+value(p.due instanceof Date? kstDay(p.due):p.due);
 const count=missing(p.n)?value(d.recrutNope):value(p.n)+(missing(d.recrutNope)||String(p.n)===String(d.recrutNope)?'':' / 상세 원문: '+value(d.recrutNope)+' · 불일치 확인');
 return [
 ['기관·직무',value(p.org)+' / '+value(p.title)+'\n공고 전체 기준 · 직무별 선택 미지원'],
 ['근무지역',value(p.regions?.length?p.regions:p.region||d.workRgnNmLst)],
 ['고용형태',value(p.emp?.length?p.emp:d.hireTypeNmLst)],
 ['모집인원',count+' · 전체/직무별 범위 원문 확인'],
 ['지원자격',value(d.aplyQlfcCn)],['우대사항',value([d.prefCn,d.prefCondCn].filter(Boolean).join('\n'))],
 ['접수기간',reception],['보수·근무시간','미확인 · 원문 단위·조건 확인 (환산하지 않음)'],
 ['전형·서류',value(d.scrnprcdrMthdExpln)+'\n제출서류: 공식 첨부문서 확인']
 ];
}
return {text,value,date,next,kstDay,url,escape,fold,utc,calendar,applications,exactMention,certificateEvidence,comparison};
});
