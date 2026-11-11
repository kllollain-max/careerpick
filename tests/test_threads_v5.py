import copy,json,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from scripts.threads_v5 import *
from scripts.threads_writer_queue import QueueValidationError
from scripts.threads_auto import master_public_copy
from scripts.threads_performance import measurement_plan
ROOT=Path(__file__).resolve().parents[1]

class V5Tests(unittest.TestCase):
    def setUp(self):
        self.sample=json.loads((ROOT/'docs/evidence/threads-v5/samples.json').read_text())[1]
    def test_copy_and_single_publication(self):
        s=self.sample
        self.assertLessEqual(copy_check(s['text'],{'v5':{}},s['image_job'])['chars'],300)
        selected={'text':s['text'],'image_job':s['image_job'],'writer_review':{'v5':{'policy_id':ID}}}
        self.assertEqual(master_public_copy(selected,STYLE),(s['text'],''))
    def test_cta_url_repeat_and_limit_fail(self):
        s=self.sample
        variants=[s['text'].replace(CTA,'확인하세요'),s['text']+'\nhttps://example.com',s['text'].replace('관련 분야 박사학위를 준비 중인가요?','무조건 합격해요'), '가'*301+'\n\n'+CTA]
        for body in variants:
            with self.subTest(body=body[:20]),self.assertRaises(QueueValidationError):
                copy_check(body,{'v5':{}},s['image_job'])
        with self.assertRaises(QueueValidationError):
            copy_check(s['text'],{'v5':{}},s['image_job'],[{'text':s['text']}])
    def test_staged_activation_and_preservation(self):
        from scripts.threads_writer_queue import fingerprint
        entry={'publication_policy_id':ID,'publication_policy_sha256':'hash','prepared_at':'2026-11-11T10:00:00+09:00','writer':{'review':{'reference_at':'2026-11-11T10:00:00+09:00'}}}
        policy={'editorial_v5':{'enabled':False}}
        with self.assertRaises(QueueValidationError):entry_mode(entry,policy)
        policy['editorial_v5'].update(enabled=True,sha256='hash',effective_at='2026-11-11T09:59:00+09:00')
        self.assertTrue(entry_mode(entry,policy))
        policy['editorial_v5']['preserved_entry_sha256']=[fingerprint(entry)]
        self.assertFalse(entry_mode(entry,policy))
        entry['prepared_at']='2026-11-11T09:58:00+09:00'
        with self.assertRaises(QueueValidationError):entry_mode(entry,policy)
    def test_v5_measurements_separate_24_72h(self):
        at=datetime(2026,11,11,tzinfo=timezone.utc)
        record={'status':'published','threads_post_id':'123','published_at':at.isoformat(),'text':self.sample['text'],'writer_review':{'v5':{'policy_id':ID}},'format_id':'eligibility','content_type':'master_job'}
        plan=measurement_plan({'records':[record]},{'observations':[]},at+timedelta(hours=25))
        self.assertEqual([x['window'] for x in plan['items']],['24h','72h'])
    def test_fact_evidence_cannot_be_bypassed(self):
        s=self.sample
        entry={'writer':{'post_text':s['text']}}
        review={'v5':{'policy_id':ID,'restrictions_complete':True,'fact_consistency_check':'passed','key_restrictions':[]}}
        with self.assertRaises(QueueValidationError):
            validate_review(entry,s['image_job'],review,[],{}, {'records':[]})
    def test_integrated_source_gates_and_preview(self):
        from test_threads_writer_queue import WriterQueueTests
        from scripts.threads_writer_queue import validate_entry
        base=WriterQueueTests();base.setUp()
        e=copy.deepcopy(base.entry);policy=copy.deepcopy(base.policy)
        policy['editorial_v5']={'enabled':True,'sha256':'v5hash','effective_at':'2026-11-06T10:09:00+09:00'}
        e.update(publication_policy_id=ID,publication_policy_sha256='v5hash',prepared_at=base.now.isoformat(),format_id='eligibility')
        body='정보보안 자격을 갖추셨나요?\n예시연구원 정보보안 담당자 정규직 채용 3명이에요.\n\n근무: 서울\n정보보안 기사 자격증이 필요해요.\n\n마감: 2026-11-18 17:00\n\n'+CTA
        e['writer']['post_text']=body
        job=e['image_job'];review=e['writer']['review']
        ref='alio-detail.json#a700'
        evidence='정보보안 담당자 정규직 채용 3명 정규직 서울'
        review['source_refs'][0]['excerpt']=evidence
        review['fact_evidence']=[{'field':key,'value':job[key],'source_ref':ref,'excerpt':evidence} for key in ['title','count','employment','location']]
        review['v5']={'policy_id':ID,'restrictions_complete':True,'fact_consistency_check':'passed','key_restrictions':[],'selection_reason':'synthetic fixture source only','public_preview':{'main_text':body,'detail_reply':''}}
        selected=validate_entry(e,base.slot,base.now,base.history,base.source,base.details,policy)
        self.assertEqual(master_public_copy(selected,STYLE),(body,''))
        stale=copy.deepcopy(base.source);stale['_operations']['last_success_at']='2026-11-01T10:02:00+09:00'
        with self.assertRaises(QueueValidationError):
            validate_entry(e,base.slot,base.now,base.history,stale,base.details,policy)
        e['writer']['review']['v5']['public_preview']['main_text']+='改'
        with self.assertRaises(QueueValidationError):
            validate_entry(e,base.slot,base.now,base.history,base.source,base.details,policy)

    def test_four_examples_are_not_live_queue_entries(self):
        examples=json.loads((ROOT/'docs/evidence/threads-v5/samples.json').read_text())
        self.assertEqual(len({s['format_id'] for s in examples}),4)
        for s in examples:self.assertTrue(s['test_only'] and s['not_ready_or_scheduled'])

if __name__=='__main__':unittest.main()
