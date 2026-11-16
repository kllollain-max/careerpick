"""No-send regression cases for explicitly reviewed same-day missing slots."""
import copy,hashlib,unittest
from datetime import timedelta
from unittest.mock import patch
from scripts import threads_catchup as catchup
from scripts.threads_writer_queue import select_ready,QueueValidationError
from scripts.threads_v5 import CTA,ID
from tests.test_threads_v5_editorial import contract_meta


class ExplicitCatchupTests(unittest.TestCase):
    def setUp(self):
        from tests.test_threads_writer_queue import WriterQueueTests
        b=WriterQueueTests();b.setUp();self.b=b;self.now=b.slot.replace(hour=17)
        e=copy.deepcopy(b.entry);p=copy.deepcopy(b.policy);p['cta']=CTA
        p['editorial_v5']={'id':ID,'enabled':True,'sha256':'v5hash','effective_at':'2026-11-06T10:09:00+09:00'}
        e.update(publication_policy_id=ID,publication_policy_sha256='v5hash',prepared_at=b.now.isoformat(),format_id='eligibility',recovery_for_slot=b.slot.isoformat())
        body='정보보안 자격을 갖춘 분께,\n예시연구원 정보보안 담당자 정규직 채용 3명이에요.\n\n근무: 서울\n정보보안 기사 자격증이 필요해요.\n\n마감: 2026-11-18 17:00\n\n'+CTA
        e['writer']['post_text']=body;r=e['writer']['review'];job=e['image_job'];ref='alio-detail.json#a700';evidence='정보보안 담당자 정규직 채용 3명 정규직 서울';r['source_refs'][0]['excerpt']=evidence
        r['fact_evidence']=[{'field':key,'value':job[key],'source_ref':ref,'excerpt':evidence} for key in ['title','count','employment','location']]
        r['v5']=contract_meta(body,r,'정보보안 기사 자격증이 필요해요.','정보보안 기사 자격증 소지자 3명 모집',ref,job,evidence)
        self.entry=e;self.policy=p;self.queue={'schema_version':1,'entries':[e]};self.history=copy.deepcopy(b.history)
        self.report={'schema_version':1,'checked_at':self.now.isoformat(),'window_start':(self.now-timedelta(hours=48)).isoformat(),'account':'hid_119','pagination_complete':True,'posts':[]}
        self.env=patch.dict(catchup.os.environ,{'THREADS_RECOVERY_CONFIRMATION':'RECOVER_SLOT','THREADS_MANUAL_PUBLISH':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_RUN_ATTEMPT':'1'});self.env.start();self.addCleanup(self.env.stop)
        self.receipt=patch('scripts.threads_reviewed_ingest.verify_official_receipt',return_value={'verified_fact_sources':[]}).start();self.addCleanup(patch.stopall)

    def call(self):
        return catchup.select_recovery(self.queue,self.b.slot,self.now,self.history,self.b.source,self.b.details,self.policy,'a700',self.report)

    def test_explicit_recovery_uses_real_v5_validator(self):
        self.assertEqual(self.call()['job_id'],'a700');self.receipt.assert_called_once_with(self.entry)
        self.entry['writer']['post_text']+=' https://bad.example'
        with self.assertRaises(QueueValidationError):self.call()

    def test_normal_selector_still_refuses_expired_slot(self):
        with self.assertRaisesRegex(QueueValidationError,'PUBLISH_SLOT_NOT_CURRENT'):
            select_ready(self.queue,self.b.slot,self.now,self.history,self.b.source,self.b.details,self.policy)

    def test_both_explicit_confirmation_and_first_dispatch_required(self):
        for key,value in [('THREADS_RECOVERY_CONFIRMATION','PUBLISH'),('THREADS_MANUAL_PUBLISH','false'),('GITHUB_EVENT_NAME','schedule'),('GITHUB_RUN_ATTEMPT','2')]:
            with self.subTest(key=key),patch.dict(catchup.os.environ,{key:value}):
                with self.assertRaisesRegex(RuntimeError,'EXPLICIT_FIRST_DISPATCH'):self.call()

    def test_cross_day_future_and_recent_slots_rejected(self):
        for slot in [self.b.slot-timedelta(days=1),self.now.replace(hour=20),self.now.replace(hour=16)]:
            with self.subTest(slot=slot),self.assertRaisesRegex(RuntimeError,'SAME_DAY_MISSED_SLOT'):
                catchup.recovery_slot(slot.isoformat(),self.now)

    def test_incomplete_stale_wrong_account_inventory_rejected(self):
        for key,value in [('pagination_complete',False),('account','hid_1004'),('checked_at',(self.now-timedelta(minutes=11)).isoformat())]:
            with self.subTest(key=key):
                r=copy.deepcopy(self.report);self.report[key]=value
                with self.assertRaisesRegex(RuntimeError,'COMPLETE_FRESH_INVENTORY'):self.call()
                self.report=r

    def test_remote_unknown_main_needs_reconciliation(self):
        self.report['posts']=[{'post_id':'123','timestamp':self.now.isoformat(),'is_reply':False,'text_sha256':'a'*64}]
        with self.assertRaisesRegex(RuntimeError,'UNRECONCILED_REMOTE_POST'):self.call()

    def test_current_regular_post_does_not_conflict_with_missing_noon(self):
        self.report['posts']=[{'post_id':'123','timestamp':self.now.isoformat(),'is_reply':False,'text_sha256':'a'*64}]
        self.history['records']=[{'job_id':'other','threads_post_id':'123','scheduled_at':self.now.replace(hour=16).isoformat(),'reserved_date':self.now.date().isoformat(),'status':'published'}]
        self.assertEqual(self.call()['job_id'],'a700')

    def test_live_matching_text_is_not_reposted(self):
        self.report['posts']=[{'post_id':'123','timestamp':self.now.isoformat(),'is_reply':False,'text_sha256':hashlib.sha256(self.entry['writer']['post_text'].encode()).hexdigest()}]
        with self.assertRaisesRegex(RuntimeError,'TEXT_ALREADY_PUBLISHED'):self.call()

    def test_recorded_or_pending_slot_blocks_even_if_inventory_empty(self):
        for row in [{'scheduled_at':self.b.slot.isoformat(),'status':'published'}, {'scheduled_at':self.b.slot.isoformat(),'status':'failed'}, {'job_id':'other','status':'pending'}]:
            self.history['records']=[row]
            with self.assertRaisesRegex(RuntimeError,'SLOT_ALREADY_RECORDED|UNRESOLVED_PRIOR'):self.call()

    def test_local_daily_cap_blocks_even_if_remote_inventory_empty(self):
        self.history['records']=[{'job_id':'other'+str(i),'status':'published','reserved_date':self.now.date().isoformat()} for i in range(4)]
        with self.assertRaisesRegex(RuntimeError,'DAILY_LIMIT_REACHED'):self.call()

    def test_remote_four_main_posts_block_even_if_local_dates_missing(self):
        self.history['records']=[{'status':'published','threads_post_id':str(i)} for i in range(1,5)]
        self.report['posts']=[{'post_id':str(i),'timestamp':self.now.isoformat(),'is_reply':False,'text_sha256':'a'*64} for i in range(1,5)]
        with self.assertRaisesRegex(RuntimeError,'DAILY_LIMIT_REACHED'):self.call()

    def test_official_document_change_blocks_recovery(self):
        self.receipt.side_effect=ValueError('OFFICIAL_SOURCE_BYTES_CHANGED')
        with self.assertRaisesRegex(ValueError,'OFFICIAL_SOURCE_BYTES_CHANGED'):self.call()

    def test_future_regular_entry_cannot_be_consumed(self):
        self.entry['scheduled_at']=(self.b.slot+timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(RuntimeError,'ENTRY_BINDING_REQUIRED'):self.call()

    def test_prepare_and_pre_send_preserve_missing_slot_and_recheck_live_inventory(self):
        import tempfile,json
        from pathlib import Path
        from scripts import threads_auto as publisher
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.threads-writer-queue.json').write_text(json.dumps(self.queue))
            with patch.object(publisher,'ROOT',root), patch.object(publisher,'writer_inputs',return_value=(self.policy,self.b.source,self.b.details)), patch.object(publisher,'save') as save, patch('scripts.threads_catchup.read_live_inventory',return_value=self.report) as live, patch.dict(publisher.os.environ,{'THREADS_MANUAL_SLOT':self.now.isoformat(),'THREADS_RECOVERY_SLOT':self.b.slot.isoformat(),'THREADS_DISPATCH_NOTICE_ID':'a700'}):
                publisher.prepare_master(self.history,self.now,'777')
                record=self.history['records'][0]
                self.assertEqual(record['scheduled_at'],self.b.slot.isoformat())
                self.assertEqual(record['recovery_mode'],'explicit_reviewed_missing_slot')
                self.assertEqual(record['text'],self.entry['writer']['post_text'])
                self.assertEqual(record['writer_entry'],self.entry)
                save.assert_called_once_with(self.history)
                publisher.validate_master_before_send(record,self.history,self.now+timedelta(minutes=1))
                self.assertEqual(live.call_count,2)
                with patch.dict(publisher.os.environ,{'THREADS_RECOVERY_SLOT':''}):
                    with self.assertRaisesRegex(RuntimeError,'CATCHUP_RESERVED_SLOT_CHANGED'):
                        publisher.validate_master_before_send(record,self.history,self.now+timedelta(minutes=1))

if __name__=='__main__':unittest.main()
