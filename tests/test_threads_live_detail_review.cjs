const test=require('node:test');
const assert=require('node:assert/strict');
const {eligible,inspect}=require('../scripts/threads_live_detail_review.cjs');
const goodManifest={notice_id:'a307271',automatic_approval:false,approved_for_queue:false,meta_posted:false,
 documents:[{name:'notice.pdf',status:'raw_bytes_captured_for_review',sha256:'a'.repeat(64)}]};
const at=new Date('2026-11-25T06:00:00Z');
const good={url:'https://kllollain-max.github.io/careerpick/#job=a307271',visible:true,
 title:'한국농어촌공사 철원화천지사 공무직(청소원) 공개경쟁 채용 공고',org:'한국농어촌공사',
 text:'공식 확인 접수마감 2026-11-30 16:00',links:['https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=307271'],
 rows:[{label:'모집 인원',value:'1명'},{label:'고용 형태',value:'무기계약직'}],
 sections:[{title:'지원 자격',text:'정년 미도달, 출퇴근 가능해야 합니다'},{title:'전형 절차·방법',text:'서류 심사 후 면접 전형을 진행합니다'}],page_errors:[]};
test('only pinned, unapproved and unexpired raw-review case is eligible',()=>{
 assert.equal(eligible(goodManifest,at),true);
 for(const m of [{...goodManifest,approved_for_queue:true},{...goodManifest,meta_posted:true},
 {...goodManifest,notice_id:'a307000'},{...goodManifest,documents:[]}])assert.equal(eligible(m,at),false);
 assert.equal(eligible(goodManifest,new Date('2026-11-30T07:00:00Z')),false);
});
test('fully loaded exact detail remains review evidence, not approval',()=>{
 assert.equal(inspect(good).status,'captured_for_semantic_review');
 assert.equal(inspect(good).approved_for_queue,undefined);
});
test('list, loading, wrong notice, mismatches and missing cutoff fail closed',()=>{
 for(const s of [{...good,visible:false},{...good,sections:[]},{...good,links:[]},{...good,rows:[]},
 {...good,url:'https://kllollain-max.github.io/careerpick/'},{...good,text:'시각 미확인'},
 {...good,text:good.text+' 공고번호가 달라 표시를 보류했습니다.'},{...good,page_errors:['error']}])
 assert.equal(inspect(s).status,'hold_ui_check');
});
