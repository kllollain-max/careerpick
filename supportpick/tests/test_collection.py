import sys,unittest,tempfile,json,copy
from unittest.mock import patch,Mock
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_full import collect,period,region,GuardedOpener,APIError
from refresh import install_candidate,read_current,mark_failure,verify_snapshot
from build import build

def rows(n=103):
    return [{'서비스ID':f'B{i:05d}','서비스명':f'공식 혜택 {i}','소관기관명':'강원특별자치도 춘천시',
             '서비스분야':'생활안정','서비스목적요약':'안내','지원대상':'공식 공고의 대상','지원내용':'금액 미제공',
             '신청기한':'예산 소진 시 종료','사용자구분':'가구','지원유형':'이용권',
             '상세조회URL':f'https://plus.gov.kr/benefit?id=B{i:05d}'} for i in range(n)]

class Client:
    def __init__(self,data=None,fail_at=None,edit=None):
        self.data=data or rows();self.requests=0;self.fail_at=fail_at;self.edit=edit
    def get(self,endpoint,page,per_page):
        self.requests+=1
        if self.fail_at==self.requests:raise APIError('network_error')
        data=copy.deepcopy(self.data[(page-1)*per_page:page*per_page])
        response={'page':page,'perPage':per_page,'totalCount':len(self.data),'matchCount':len(self.data),'currentCount':len(data),'data':data}
        return self.edit(endpoint,page,response,self.requests) if self.edit else response

class CollectionTests(unittest.TestCase):
    def test_complete_three_endpoints_join_every_id(self):
        with tempfile.TemporaryDirectory() as p:
            c=Client();r=collect(c,p,'test')
            self.assertEqual(r['status'],'passed');self.assertEqual(r['storedCount'],103)
            self.assertEqual(c.requests,9)
            self.assertTrue(all(v['receivedCount']==v['uniqueCount']==v['reportedTotal']==103 for v in r['endpoints'].values()))
            data=json.loads((Path(p)/'snapshot/data.json').read_text());self.assertFalse(data['isSample'])
            self.assertTrue(all(x['factsVerifiedAt'] is None and not x['applicationOpenVerified'] for x in data['items']))
            shards=list((Path(p)/'snapshot/details/test').glob('*.json'))
            self.assertEqual(sum(len(json.loads(x.read_text())['items']) for x in shards),103)
    def test_partial_failure_resumes_completed_pages(self):
        with tempfile.TemporaryDirectory() as p:
            first=collect(Client(fail_at=3),p,'test');self.assertEqual(first['status'],'failed')
            b=Client();second=collect(b,p,'test');self.assertEqual(second['status'],'passed');self.assertEqual(b.requests,7)
    def test_empty_or_short_page_is_a_failure(self):
        def edit(e,p,r,n):
            if e=='serviceList' and p==2:r['data']=[];r['currentCount']=0
            return r
        with tempfile.TemporaryDirectory() as p:
            r=collect(Client(edit=edit),p,'test');self.assertEqual(r['errorCode'],'partial_or_empty_page')
            self.assertFalse((Path(p)/'snapshot/data.json').exists())
    def test_duplicates_do_not_mask_a_missing_id(self):
        data=rows();data[-1]=data[0]
        with tempfile.TemporaryDirectory() as p:
            r=collect(Client(data=data),p,'test');self.assertEqual(r['errorCode'],'page_coverage_mismatch')
    def test_detail_set_mismatch_blocks_snapshot(self):
        def edit(e,p,r,n):
            if e=='serviceDetail' and p==2:r['data'][-1]['서비스ID']='OTHER'
            return r
        with tempfile.TemporaryDirectory() as p:
            r=collect(Client(edit=edit),p,'test');self.assertEqual(r['errorCode'],'detail_or_conditions_join_mismatch')
    def test_boundary_change_blocks_snapshot(self):
        def edit(e,p,r,n):
            if n>6:r['data'][0]['지원내용']='changed'
            return r
        with tempfile.TemporaryDirectory() as p:
            r=collect(Client(edit=edit),p,'test');self.assertEqual(r['errorCode'],'source_changed_at_snapshot_boundary')
    def test_tampered_checkpoint_is_not_reused(self):
        with tempfile.TemporaryDirectory() as p:
            collect(Client(fail_at=3),p,'test')
            f=Path(p)/'pages/serviceList/00001.json';v=json.loads(f.read_text());v['response']['data'][0]['서비스명']='tampered';f.write_text(json.dumps(v))
            r=collect(Client(),p,'test');self.assertEqual(r['errorCode'],'checkpoint_hash_mismatch')
    def test_budget_checked_before_transport_request(self):
        class Opener:
            def open(self):return 'response'
        g=GuardedOpener(Opener(),max_requests=1,interval=0)
        self.assertEqual(g.open(),'response')
        with self.assertRaises(APIError):g.open()
        self.assertEqual(g.calls,1)
    def test_period_types_never_invent_a_deadline(self):
        for text,kind in [('', 'not_provided'),('상시 신청','ongoing'),('예산 소진 시까지','budget_limited'),('신청기관 문의','needs_check')]:
            r=period(text);self.assertEqual(r['periodKind'],kind);self.assertIsNone(r['endDate'])
        self.assertEqual(period('2026. 6. 15. ~ 2026. 12. 31.')['endDate'],'2026-12-31')
        self.assertIsNone(period('2026. 2. 31. ~ 2026. 12. 31.')['endDate'])
    def test_central_agency_is_not_inferred_as_nationwide(self):
        self.assertEqual(region('기후에너지환경부','특정 세대 지원')[0],'확인 필요')
        self.assertEqual(region('강원특별자치도 춘천시','원문 확인')[1],'agency_jurisdiction')
    def test_promote_then_failure_preserves_data_and_success_time(self):
        with tempfile.TemporaryDirectory() as p:
            p=Path(p);collect(Client(),p/'run1','test1');installed=install_candidate(p/'run1',p/'state')
            before=(p/'state/current.json').read_bytes();_,snapshot=read_current(p/'state')
            first=(snapshot/'data.json').read_bytes()
            collect(Client(fail_at=2),p/'run2','test2')
            with self.assertRaises(ValueError):install_candidate(p/'run2',p/'state')
            mark_failure(p/'state','network_error')
            self.assertEqual((p/'state/current.json').read_bytes(),before)
            self.assertEqual((snapshot/'data.json').read_bytes(),first)
            status=json.loads((p/'state/status.json').read_text())
            self.assertEqual(status['lastSuccessAt'],installed['lastSuccessAt']);self.assertEqual(status['status'],'failed')
            result=build(p/'public',p/'state');self.assertEqual(result['benefits'],103);self.assertEqual(result['status'],'failed')
            self.assertFalse((p/'public/tools').exists());self.assertFalse((p/'public/report.json').exists())
    def test_abnormal_drop_never_replaces_current_generation(self):
        with tempfile.TemporaryDirectory() as p:
            p=Path(p);collect(Client(),p/'run1','test1');install_candidate(p/'run1',p/'state');old=(p/'state/current.json').read_bytes()
            collect(Client(data=rows(5)),p/'run2','test2')
            with self.assertRaisesRegex(ValueError,'abnormal_count_drop'):install_candidate(p/'run2',p/'state')
            self.assertEqual((p/'state/current.json').read_bytes(),old)
    def test_manifest_tamper_cannot_be_built_or_restored(self):
        with tempfile.TemporaryDirectory() as p:
            p=Path(p);collect(Client(),p/'run1','test1');install_candidate(p/'run1',p/'state');_,snapshot=read_current(p/'state')
            (snapshot/'data.js').write_text('window.SUPPORTPICK_DATA = {};')
            with self.assertRaises(ValueError):read_current(p/'state')
            with self.assertRaises(ValueError):build(p/'public',p/'state')
    def test_operational_build_requires_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as p:
            with self.assertRaisesRegex(ValueError,'complete_snapshot_required'):build(Path(p)/'out',Path(p)/'missing')
    def test_runtime_state_lookup_failure_blocks_instead_of_using_old_baseline(self):
        import restore_latest_state
        opener=Mock();opener.open.side_effect=OSError('network failure')
        with patch.object(restore_latest_state,'ensure_bootstrap'),patch.object(restore_latest_state,'build_opener',return_value=opener),patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/supportpick','GITHUB_TOKEN':'test-only-placeholder'}):
            with self.assertRaisesRegex(ValueError,'latest_state_lookup_failed'):restore_latest_state.main()
    def test_latest_completed_run_without_state_does_not_fall_back_to_older_data(self):
        import restore_latest_state
        class Response:
            def __init__(self,value):self.value=value
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps(self.value).encode()
        opener=Mock();opener.open.side_effect=[Response({'workflow_runs':[{'id':1,'run_number':1,'head_branch':'main','event':'schedule'}]}),Response({'artifacts':[]})]
        with patch.object(restore_latest_state,'ensure_bootstrap'),patch.object(restore_latest_state,'build_opener',return_value=opener),patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/supportpick','GITHUB_TOKEN':'test-only-placeholder','GITHUB_RUN_NUMBER':'2'}):
            with self.assertRaisesRegex(ValueError,'latest_runtime_state_unavailable'):restore_latest_state.main()

if __name__=='__main__':unittest.main()
