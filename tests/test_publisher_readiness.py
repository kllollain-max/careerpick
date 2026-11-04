import copy
import re
import unittest
from scripts.build_job_pages import render
from scripts.publisher_readiness import placement_candidate

class PublisherReadinessTests(unittest.TestCase):
 def test_ambiguous_counts_preserve_text_and_both_sources(self):
  p={'id':'a123','alio':True,'title':'가상 공고','org':'가상 기관','n':'분야별 2명·3명','due':'2099-01-01','dueHasTime':False}
  d={'recrutPblntSn':'123','recrutNope':'미정'};before=copy.deepcopy((p,d));s=render(p,d)
  self.assertIn('분야별 2명·3명',s);self.assertIn('상세 미정',s);self.assertNotIn('23명',s);self.assertEqual((p,d),before)
 def test_publication_period_never_becomes_application_deadline_schema(self):
  s=render({'id':'a123','alio':True,'title':'가상 공고','org':'가상 기관','due':'2099-01-01T23:59:00+09:00','dueHasTime':False},{'pbancBgngYmd':'20981201','pbancEndYmd':'20990101'})
  self.assertIn('ALIO 게시 종료일',s);self.assertIn('원서 접수기간',s);self.assertNotIn('application/ld+json',s);self.assertNotIn('2099-01-01 23:59',s)
 def test_different_notice_detail_never_enters_page(self):
  s=render({'id':'a123','alio':True,'title':'가상','org':'가상','n':'미정'},{'recrutPblntSn':'999','aplyQlfcCn':'다른 공고 비밀문장'})
  self.assertNotIn('다른 공고 비밀문장',s)
 def test_all_functional_and_same_url_states_deny_requests(self):
  for kind in ['app','guide','job','collection','settings']:
   for screen in ['all','saved','track','prefs','spec','error','article','loading','empty']:
    for state in ['ready','empty','error','loading','unfinished']:
     self.assertFalse(placement_candidate(kind,screen,state,True)['ad_request_allowed'])
     if screen!='article' or state!='ready' or kind!='guide':self.assertFalse(placement_candidate(kind,screen,state,True)['candidate'])
 def test_automated_review_is_not_human_approval(self):
  self.assertFalse(placement_candidate('guide','article','ready')['candidate'])
  self.assertFalse(placement_candidate('guide','article','ready','auto-pass')['candidate'])
  self.assertTrue(placement_candidate('guide','article','ready',True)['candidate'])

if __name__=='__main__':unittest.main()
