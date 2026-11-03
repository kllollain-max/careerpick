import unittest
from datetime import datetime
from scripts.collect_gojobs import merge

NOW=datetime.fromisoformat('2026-11-03T17:00:00+09:00')


def report(eligible=True):
    return {'complete_window':True,'total_by_filter':{'e01':{'records':10}},
        'records':[{'id':'7','registered_date':'2026-11-01'}],
        'official_page_samples':[{'id':'gojobs-7','title':'임기제 채용 공고','org':'기관',
            'url':'https://www.gojobs.go.kr/apmView.do?empmnsn=7','region':'서울',
            'application_start':'2026-11-01','application_end':'2026-11-04',
            'content':'공식 모집 내용','classification':{'recruiting':eligible}}]}


class CollectionTests(unittest.TestCase):
    def test_id_preserved_and_repeated_collection_has_no_change(self):
        feed,changed,counts=merge({'posts':[]},report(),NOW)
        self.assertTrue(changed);self.assertEqual(counts['new'],1)
        self.assertEqual(feed['posts'][0]['id'],'gojobs-7')
        same,changed,counts=merge(feed,report(),NOW)
        self.assertIs(same,feed);self.assertFalse(changed);self.assertEqual(counts['new'],0)
    def test_result_or_unconfirmed_never_inserted_or_deletes_prior_record(self):
        feed,_,_=merge({'posts':[]},report(),NOW)
        retained,changed,counts=merge(feed,report(False),NOW)
        self.assertIs(retained,feed);self.assertFalse(changed);self.assertEqual(counts['deleted'],0)
    def test_partial_or_sudden_zero_rejected_before_replacement(self):
        feed,_,_=merge({'posts':[]},report(),NOW)
        for changes in [{'complete_window':False},{'total_by_filter':{'e01':{'records':0}}}]:
            data=report();data.update(changes)
            with self.assertRaises(ValueError):merge(feed,data,NOW)
        self.assertEqual(len(feed['posts']),1)
    def test_source_namespaced_and_details_retained(self):
        feed,_,_=merge({'posts':[]},report(),NOW)
        post=feed['posts'][0]
        self.assertFalse(post.get('alio',False))
        self.assertEqual(post['gojobsDetail']['공식 모집 내용'],'공식 모집 내용')
        self.assertFalse(post['dueHasTime'])


if __name__=='__main__':unittest.main()
