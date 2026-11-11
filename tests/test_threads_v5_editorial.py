"""Synthetic adverse editorial cases; no network, queue writes or publication."""
import copy
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from scripts.threads_v5 import (
    ID, CTA, CONTRACT_VERSION, KST, copy_check, validate_review,
    balanced_intro_type, ranking_key, entry_mode,
)
from scripts.threads_writer_queue import QueueValidationError


def contract_meta(body, review, useful_text, useful_excerpt, ref, job, unit_excerpt):
    opening = body.split('\n\n')[0]
    return {
        'policy_id': ID, 'contract_version': CONTRACT_VERSION,
        'restrictions_complete': True, 'fact_consistency_check': 'passed',
        'recruitment_unit': {**{key:job[key] for key in ['title','count','employment']},
                             'scope':'single_recruitment_unit','source_ref':ref,'excerpt':unit_excerpt},
        'key_restrictions': [], 'selection_reason': 'Synthetic official-evidence fixture; not a live job.',
        'public_preview': {'main_text': body, 'detail_reply': ''},
        'hook_candidates': [
            {'id': 'a', 'type': 'target', 'text': opening},
            {'id': 'b', 'type': 'condition', 'text': '정보보안 기사 자격을 갖춘 분을 위한 공고예요.'},
            {'id': 'c', 'type': 'job', 'text': '정보보안 업무를 맡을 정규직을 모집해요.'},
        ],
        'selected_hook_id': 'a', 'first_sentence_type': 'target',
        'hook_review': {'factual': True, 'target_clear': True, 'natural': True},
        'useful_point': {'text': useful_text, 'source_ref': ref, 'excerpt': useful_excerpt},
        'style_rewrites': 0,
        'correction_check': {'source_ref': ref, 'checked_at': review['checked_at'], 'result': 'none_found'},
    }


class EditorialContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 19, 20, tzinfo=KST)
        self.slot = self.now.replace(hour=20, minute=0)
        self.ref = 'https://official.example/notice/fixture'
        self.job = {'id': 'synthetic', 'org': '예시연구원', 'title': '정보보안 담당자',
                    'count': 3, 'employment': '정규직', 'location': '서울',
                    'due': '2026-11-12', 'deadline_label': '2026-11-12 18:00'}
        self.useful = '정보보안 기사 자격증이 필요해요.'
        self.evidence = '예시연구원 정보보안 담당자 정규직 3명 서울. 정보보안 기사 자격증 소지자.'
        self.body = ('정보보안 담당자 정규직을 찾는 분께,\n예시연구원에서 3명을 모집해요.\n\n'
                     '근무: 서울\n' + self.useful + '\n\n'
                     '마감: 2026-11-12 18:00\n\n' + CTA)
        self.review = {'checked_at': self.now.isoformat(), 'reference_at': self.now.isoformat(),
                       'scheduled_at': self.slot.isoformat(),
                       'application_period': {'date_only': False},
                       'fact_evidence': [{'field': k, 'value': self.job[k], 'source_ref': self.ref, 'excerpt': self.evidence}
                                         for k in ['title', 'count', 'employment', 'location']]}
        self.review['v5'] = contract_meta(self.body, self.review, self.useful,
                                          '정보보안 기사 자격증 소지자.', self.ref,self.job,self.evidence)
        self.refs = [{'url': self.ref, 'excerpt': self.evidence}]
        self.entry = {'scheduled_at': self.slot.isoformat(), 'writer': {'post_text': self.body}}
        self.history = {'records': [], 'posted_ids': []}

    def validate(self):
        return validate_review(self.entry,self.job,self.review,self.refs,{},self.history,now=self.now)

    def replace_body(self, body):
        self.body = body
        self.entry['writer']['post_text'] = body
        self.review['v5']['public_preview']['main_text'] = body
        self.review['v5']['hook_candidates'][0]['text'] = body.split('\n\n')[0]

    def test_excluded_intro_does_not_bias_future_assignment(self):
        before = balanced_intro_type(self.slot, [], 'TEXT')
        excluded = [{'status': 'published', 'scheduled_at': self.slot.isoformat(), 'image_url': '',
                     'writer_review': {'v5': {'contract_version': 2, 'first_sentence_type': before,
                                             'experiment_eligible': False}}}]
        self.assertEqual(balanced_intro_type(self.slot, excluded, 'TEXT'), before)

    def test_complete_contract_passes_and_does_not_change_copy(self):
        before = copy.deepcopy(self.entry)
        checked = self.validate()
        self.assertEqual(checked['chars'],len(self.body))
        self.assertEqual(self.entry,before)

    def test_unit_count_cannot_use_later_notice_total(self):
        self.refs[0]['excerpt'] += ' 전체 공고 합계 7명.'
        self.review['v5']['recruitment_unit']['excerpt']=self.refs[0]['excerpt']
        self.validate()
        self.job['count']=7
        self.review['v5']['recruitment_unit']['count']=7
        self.review['fact_evidence'][1].update(value=7,excerpt=self.refs[0]['excerpt'])
        self.replace_body(self.body.replace('3명을','7명을'))
        with self.assertRaisesRegex(QueueValidationError,'UNIT_COUNT_BECAME_NOTICE_TOTAL'):self.validate()

    def test_ordered_table_row_plain_count_supported(self):
        row='정보보안 담당자 | 정규직 | 3 | 서울'
        self.refs[0]['excerpt']+=' '+row
        self.review['v5']['recruitment_unit']['excerpt']=row
        self.validate()

    def test_pay_number_needs_official_text_and_unit_evidence(self):
        salary='연봉 4,000만원이에요.'
        self.replace_body(self.body.replace('\n\n'+CTA,'\n\n'+salary+'\n\n'+CTA))
        with self.assertRaisesRegex(QueueValidationError,'SALARY_EVIDENCE_REQUIRED'):self.validate()
        self.refs[0]['excerpt']+=' 연봉 4,000만원.'
        self.review['v5']['salary_claims']=[{'text':salary,'source_ref':self.ref,'excerpt':'연봉 4,000만원.'}]
        self.validate()
        bad='연봉 4,000억원이에요.'
        self.replace_body(self.body.replace(salary,bad))
        self.review['v5']['salary_claims'][0]['text']=bad
        with self.assertRaisesRegex(QueueValidationError,'SALARY_EVIDENCE_REQUIRED'):self.validate()

    def test_emoji_default_is_reported_not_a_subjective_infinite_rewrite_gate(self):
        body=self.body.replace('근무:','📌 근무:')
        self.assertTrue(copy_check(body,self.review,self.job)['emoji_default_met'])
        body=body.replace('마감:','📅 마감:')
        checks=copy_check(body,self.review,self.job)
        self.assertEqual(checks['emoji_count'],2)
        self.assertFalse(checks['emoji_default_met'])

    def test_three_hooks_and_selected_opening_are_required(self):
        self.review['v5']['hook_candidates'].pop()
        with self.assertRaisesRegex(QueueValidationError,'THREE_HOOK'): self.validate()
        self.setUp()
        self.review['v5']['selected_hook_id']='b'
        with self.assertRaisesRegex(QueueValidationError,'SELECTED_HOOK'): self.validate()

    def test_useful_point_must_appear_and_have_retained_evidence(self):
        self.review['v5']['useful_point']['excerpt']='자격증 없이 누구나 가능'
        with self.assertRaisesRegex(QueueValidationError,'USEFUL_POINT_EVIDENCE'): self.validate()

    def test_correction_review_and_bounded_style_rewrites(self):
        self.review['v5']['style_rewrites']=3
        with self.assertRaisesRegex(QueueValidationError,'STYLE_REWRITE_LIMIT'): self.validate()
        self.review['v5']['style_rewrites']=2
        self.review['v5']['correction_check']['checked_at']=(self.now+timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(QueueValidationError,'CORRECTION_CHECK_TIME'): self.validate()

    def test_length_exception_preserves_conditions_without_multiple_roles(self):
        padding='안내 문구 ' * 40
        long_body=self.body.replace('\n\n'+CTA,'\n\n'+padding+'\n\n'+CTA)
        long_body=long_body.replace(padding,'가'*(315-len(self.body)-2))
        self.assertEqual(len(long_body),315)
        with self.assertRaisesRegex(QueueValidationError,'LENGTH'):
            copy_check(long_body,self.review,self.job)
        self.review['v5']['length_exception_reason']='지원자격의 여러 인정 경로와 기준일을 보존해야 함.'
        self.assertEqual(copy_check(long_body,self.review,self.job)['chars'],315)
        with self.assertRaisesRegex(QueueValidationError,'LENGTH'):
            copy_check(long_body.replace('가'*10,'가'*50,1),self.review,self.job)

    def test_split_obfuscated_link_and_hype_fail_before_send(self):
        for extra in ['1/2','2/2','이어서 설명','https ://example.com','example[dot]app','누구나 지원해요','경쟁률 낮아요']:
            with self.subTest(extra=extra),self.assertRaises(QueueValidationError):
                copy_check(self.body.replace('\n\n'+CTA,'\n\n'+extra+'\n\n'+CTA),self.review,self.job)

    def test_last_eight_confirmed_posts_only(self):
        rows=[{'status':'published','threads_post_id':str(i),'published_at':f'2026-11-{i+1:02}T12:00:00+09:00',
               'text':self.body if i==1 else f'별도 도입 {i}'} for i in range(1,10)]
        copy_check(self.body,self.review,self.job,rows)  # matching oldest is outside the last 8
        rows.append({'status':'failed','text':self.body})
        copy_check(self.body,self.review,self.job,rows)
        rows[-2]['text']=self.body
        with self.assertRaisesRegex(QueueValidationError,'REPEATED_FIRST_LINE'):
            copy_check(self.body,self.review,self.job,rows)

    def test_month_day_label_preserves_source_clock_and_precision(self):
        short=self.body.replace('2026-11-12 18:00','11월 12일 18:00')
        copy_check(short,self.review,self.job)
        for wrong in ['11월 12일 19:00','11월 12일 18:00:01','11월 13일 18:00']:
            with self.subTest(wrong=wrong),self.assertRaisesRegex(QueueValidationError,'MISSING_DEADLINE_LABEL'):
                copy_check(self.body.replace('2026-11-12 18:00',wrong),self.review,self.job)
        seconds={**self.job,'deadline_label':'2026-11-12 17:30:00'}
        copy_check(self.body.replace('2026-11-12 18:00','11월 12일 17:30:00'),self.review,seconds)
        with self.assertRaisesRegex(QueueValidationError,'MISSING_DEADLINE_LABEL'):
            copy_check(self.body.replace('2026-11-12 18:00','11월 12일 17:30'),self.review,seconds)

    def test_cutover_protects_only_before_boundary_and_never_exempts_future_ready(self):
        from scripts.threads_writer_queue import fingerprint
        entry={'scheduled_at':self.slot.isoformat(),'publication_policy_id':ID,'publication_policy_sha256':'hash',
               'prepared_at':self.now.isoformat(),'writer':{'review':{'reference_at':self.now.isoformat()}}}
        config={'enabled':True,'sha256':'hash','effective_at':(self.now-timedelta(minutes=1)).isoformat(),
                'first_new_slot':self.slot.isoformat(),'preserved_entry_sha256':[]}
        self.assertTrue(entry_mode(entry,{'editorial_v5':config}))
        config['preserved_entry_sha256']=[fingerprint(entry)]
        with self.assertRaisesRegex(QueueValidationError,'FUTURE_ENTRY_CANNOT_BE_PRESERVED'):
            entry_mode(entry,{'editorial_v5':config})
        old=copy.deepcopy(entry);old['scheduled_at']=self.slot.replace(hour=16).isoformat()
        config['preserved_entry_sha256']=[fingerprint(old)]
        self.assertFalse(entry_mode(old,{'editorial_v5':config}))
        config['preserved_entry_sha256']=[]
        with self.assertRaisesRegex(QueueValidationError,'BEFORE_CUTOVER_SLOT'):
            entry_mode(old,{'editorial_v5':config})

    def test_relative_date_uses_actual_korean_day(self):
        body=self.body.replace('마감:', '내일 마감:')
        copy_check(body,self.review,self.job,now=self.now)
        with self.assertRaisesRegex(QueueValidationError,'RELATIVE_DATE_NEEDS_CURRENT_TIME'):
            copy_check(body,self.review,self.job)
        with self.assertRaisesRegex(QueueValidationError,'RELATIVE_DATE_CHANGED'):
            copy_check(body,self.review,self.job,now=self.now+timedelta(days=1))

    def test_value_and_reader_question_daily_caps(self):
        value='지원 조건을 확인한 채용 소식을 정리해요.'
        self.replace_body(self.body.replace('\n\n'+CTA,'\n\n'+value+'\n\n'+CTA))
        self.review['v5']['value_sentence']=value
        self.validate()
        self.history['records']=[{'status':'published','threads_post_id':'123','scheduled_at':self.slot.replace(hour=8).isoformat(),
                                 'writer_review':{'v5':{'value_sentence':value}}}]
        with self.assertRaisesRegex(QueueValidationError,'OPTIONAL_SENTENCE_DAILY_LIMIT'):self.validate()
        self.history['records']=[]
        question='어느 지역의 채용 소식이 필요하세요?'
        self.review['v5']['question']=question
        self.replace_body(self.body.replace('\n\n'+CTA,'\n\n'+question+'\n\n'+CTA))
        with self.assertRaisesRegex(QueueValidationError,'VALUE_AND_QUESTION_TOGETHER'):self.validate()

    def install_alternatives(self):
        text='충남 학력·주소·거주이력 중 하나의 인정 경로를 충족해야 해요.'
        sources=['충남 고교·대학 졸업(예정)', '공고 전일부터 최종면접일까지 충남 주소 유지', '공고 전까지 충남 거주이력 합산 3년']
        evidence=' / '.join(sources)
        self.refs[0]['excerpt']+=' '+evidence
        self.replace_body(self.body.replace(self.useful,text))
        self.review['v5']['useful_point']={'text':text,'source_ref':self.ref,'excerpt':evidence}
        self.review['v5']['key_restrictions']=[{'text':text,'source_ref':self.ref,'excerpt':evidence,
            'classification':'required','logic':'any_of',
            'paths':[{'summary':k,'source_ref':self.ref,'excerpt':v} for k,v in zip(['학력','주소','거주이력'],sources)]}]
        return text

    def test_chungnam_alternative_routes_not_current_residency_only(self):
        text=self.install_alternatives()
        self.validate()
        bad='현재 충남 거주자만 지원하며 학력·주소·거주이력을 모두 충족해야 해요.'
        self.replace_body(self.body.replace(text,bad))
        self.review['v5']['key_restrictions'][0]['text']=bad
        self.review['v5']['useful_point']['text']=bad
        with self.assertRaisesRegex(QueueValidationError,'ALTERNATIVE_'):self.validate()

    def test_expected_graduates_may_not_disappear_from_direct_summary(self):
        text=self.install_alternatives()
        changed='충남 고교·대학 졸업 또는 주소·거주이력 경로를 충족해야 해요.'
        self.replace_body(self.body.replace(text,changed))
        item=self.review['v5']['key_restrictions'][0]
        item['text']=changed
        item['paths'][0]['summary']='졸업'
        self.review['v5']['useful_point']['text']=changed
        with self.assertRaisesRegex(QueueValidationError,'EXPECTED_GRADUATES_OMITTED'):self.validate()

    def test_bonus_qualification_not_made_mandatory(self):
        self.review['v5']['key_restrictions']=[{'text':self.useful,'source_ref':self.ref,
            'excerpt':'정보보안 기사 자격증 소지자.','classification':'bonus','logic':'single'}]
        with self.assertRaisesRegex(QueueValidationError,'PREFERENCE_AS_REQUIREMENT'):self.validate()

    def test_card_restriction_is_from_reviewed_body(self):
        text=self.install_alternatives()
        self.review['v5']['card_restriction']='충남 학력·주소·거주이력'
        self.validate()
        self.review['v5']['card_restriction']='현재 충남 거주자만'
        with self.assertRaisesRegex(QueueValidationError,'CARD_RESTRICTION_UNREVIEWED'):self.validate()

    def test_real_prepare_and_pre_send_paths_keep_one_body_zero_replies_without_api(self):
        from test_threads_writer_queue import WriterQueueTests
        from scripts import threads_auto
        base=WriterQueueTests();base.setUp()
        entry=copy.deepcopy(base.entry);policy=copy.deepcopy(base.policy)
        policy['cta']=CTA
        policy['editorial_v5']={'enabled':True,'id':ID,'sha256':'v2-test',
            'effective_at':'2026-11-06T10:00:00+09:00','first_new_slot':base.slot.isoformat()}
        entry.update(publication_policy_id=ID,publication_policy_sha256='v2-test',
                     prepared_at=base.now.isoformat(),format_id='eligibility')
        body=('정보보안 담당자 정규직 채용을 찾는 분께,\n예시연구원이 3명을 모집해요.\n\n'
              '근무: 서울\n정보보안 기사 자격증이 필요해요.\n\n'
              '마감: 11월 18일 17:00\n\n'+CTA)
        entry['writer']['post_text']=body
        review=entry['writer']['review'];job=entry['image_job'];ref='alio-detail.json#a700'
        evidence='정보보안 담당자 정규직 채용 3명 정규직 서울'
        review['source_refs'][0]['excerpt']=evidence
        review['fact_evidence']=[{'field':key,'value':job[key],'source_ref':ref,'excerpt':evidence}
                                 for key in ['title','count','employment','location']]
        review['v5']=contract_meta(body,review,'정보보안 기사 자격증이 필요해요.',
                                   '정보보안 기사 자격증 소지자 3명 모집',ref,job,evidence)
        queue={'schema_version':1,'entries':[entry]}
        now=base.slot+timedelta(minutes=10)
        with patch.object(threads_auto,'writer_inputs',return_value=(policy,base.source,base.details)), \
             patch.object(threads_auto,'load',return_value=queue), \
             patch.object(threads_auto,'save'), \
             patch.object(threads_auto,'current_publication_slot',return_value=base.slot), \
             patch.object(threads_auto,'api',side_effect=AssertionError('No HTTP/API is allowed in a preflight')):
            threads_auto.prepare_master(base.history,now,'123')
            record=base.history['records'][0]
            self.assertEqual(record['text'],body)
            self.assertEqual(record['reply_text'],'')
            self.assertEqual(record['engagement_text'],'')
            self.assertEqual(record['publication_style'],'single_main_v5')
            threads_auto.validate_master_before_send(record,base.history,now)
            record['reply_text']='Legacy detail must not return.'
            with self.assertRaisesRegex(RuntimeError,'Reserved text, detail reply or format changed'):
                threads_auto.validate_master_before_send(record,base.history,now)

    def test_experiment_never_assigns_an_arm_only_to_one_hour(self):
        history=[]
        for day in range(4):
            for hour in (8,12,16,20):
                at=self.slot.replace(hour=hour)+timedelta(days=day)
                media='IMAGE' if hour in (8,16) else 'TEXT'
                arm=balanced_intro_type(at,history,media)
                history.append({'status':'published','scheduled_at':at.isoformat(),'image_url':'card' if media=='IMAGE' else '',
                    'writer_review':{'v5':{'contract_version':2,'first_sentence_type':arm}}})
        for hour in (8,12,16,20):
            arms=[r['writer_review']['v5']['first_sentence_type'] for r in history if datetime.fromisoformat(r['scheduled_at']).hour==hour]
            self.assertEqual(arms.count('target'),arms.count('condition'))

    def test_ranking_does_not_invent_sector_demand_or_use_total_count(self):
        base={'employment_priority':0,'unit_count':3,'unit_scope':'reviewed_unit','application_period':{'end':'2026-12-01T18:00:00+09:00'},'notice_id':'x'}
        a={**base,'sector_group':'hospital_health'}
        b={**base,'sector_group':'energy_power'}
        self.assertEqual(ranking_key(a,self.now),ranking_key(b,self.now))
        unknown={**base,'unit_count':999,'unit_scope':'unit_count_unconfirmed'}
        self.assertLess(ranking_key(base,self.now),ranking_key(unknown,self.now))


if __name__=='__main__':unittest.main()
