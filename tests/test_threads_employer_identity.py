"""Parent feed labels never silently become the subsidiary employer."""
import unittest
from copy import deepcopy
from scripts.threads_writer_queue import verified_employer, QueueValidationError
from scripts.threads_reviewed_ingest import verify_official_receipt


class EmployerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.url='https://www.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0155'
        self.entry={'notice_id':'cleaneye-80820','image_job':{'org':'서울도시철도그린환경'}}
        self.post={'cleaneye':True}
        self.detail={'기관명':'서울교통공사'}
        self.policy={'official_employer_mappings':{'cleaneye-80820':{
            'parent':'서울교통공사','employer':'서울도시철도그린환경','source_ref':self.url}}}
        self.refs=[{'url':self.url,'document_sha256':'a'*64,
                    'text':'서울도시철도그린환경 2026년 하반기 공무직 공개채용'}]
        self.review={'fact_evidence':[{'field':'employer','value':'서울도시철도그린환경',
                       'source_ref':self.url,'excerpt':self.refs[0]['text']}]}

    def check(self):
        return verified_employer(self.entry,self.post,self.detail,self.review,self.refs,self.policy)

    def test_pinned_employer_with_literal_official_evidence(self):
        self.assertEqual(self.check(),'서울도시철도그린환경')

    def test_unconfigured_writer_override_is_rejected(self):
        self.policy={}
        with self.assertRaisesRegex(QueueValidationError,'IMAGE_ORGANIZATION_CONFLICT'):self.check()

    def test_mapping_cannot_apply_to_another_notice(self):
        self.entry['notice_id']='cleaneye-80848'
        with self.assertRaisesRegex(QueueValidationError,'IMAGE_ORGANIZATION_CONFLICT'):self.check()

    def test_changed_parent_feed_identity_rejected(self):
        self.detail['기관명']='다른기관'
        with self.assertRaisesRegex(QueueValidationError,'IMAGE_ORGANIZATION_CONFLICT'):self.check()

    def test_different_source_url_or_missing_digest_rejected(self):
        for field,value in [('url','https://www.smrtg.co.kr/'),('document_sha256',None)]:
            with self.subTest(field=field):
                previous=deepcopy(self.refs);self.refs[0][field]=value
                with self.assertRaisesRegex(QueueValidationError,'IMAGE_EMPLOYER_SOURCE_UNVERIFIED'):self.check()
                self.refs=previous

    def test_uncited_or_invented_employer_excerpt_rejected(self):
        self.review['fact_evidence'][0]['excerpt']='서울도시철도그린환경 다른 허구 공고'
        with self.assertRaisesRegex(QueueValidationError,'IMAGE_EMPLOYER_SOURCE_UNVERIFIED'):self.check()

    def test_employer_bytes_must_also_be_rechecked_during_ingest(self):
        other='https://www.alio.go.kr/download/notice.pdf'
        review={'source_refs':self.refs+[{'url':other,'sha256':'b'*64}],
                'fact_evidence':self.review['fact_evidence']+[
                    {'field':field,'source_ref':other} for field in ['title','count','employment']]}
        entry={'writer':{'review':review}}
        with self.assertRaisesRegex(ValueError,'OFFICIAL_SOURCE_BYTES_CHANGED'):
            verify_official_receipt(entry,fetch_digest=lambda url:'c'*64 if url==self.url else 'b'*64)

if __name__=='__main__':unittest.main()
