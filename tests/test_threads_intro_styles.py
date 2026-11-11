import hashlib
import tempfile
import unittest
from pathlib import Path
from scripts.threads_intro_styles import load_guidance, plan_styles


class IntroStylesTest(unittest.TestCase):
    def test_cutover_and_media_are_independent(self):
        slots=[{'scheduled_at':'2026-11-11T20:00:00+09:00','planned_media':'TEXT'},
               {'scheduled_at':'2026-11-12T08:00:00+09:00','planned_media':'IMAGE'},
               {'scheduled_at':'2026-11-12T12:00:00+09:00','planned_media':'TEXT'}]
        plan_styles(slots, [], {'enabled':True,'first_new_slot':slots[1]['scheduled_at']})
        self.assertNotIn('presentation_style',slots[0])
        self.assertEqual([s['presentation_style'] for s in slots[1:]],['regular_interest','eligibility_info'])
        self.assertEqual([s['planned_media'] for s in slots],['TEXT','IMAGE','TEXT'])

    def test_only_successful_v2_history_controls_next_style(self):
        history=[{'status':'published','threads_post_id':'1','writer_review':{'v5':{'contract_version':2,'presentation_style':'regular_interest'}}},
                 {'status':'pending','threads_post_id':'2','writer_review':{'v5':{'contract_version':2,'presentation_style':'eligibility_info'}}}]
        slots=[{'scheduled_at':'2026-11-12T08:00:00+09:00'}]
        plan_styles(slots,history,{'enabled':True,'first_new_slot':slots[0]['scheduled_at']})
        self.assertEqual(slots[0]['presentation_style'],'eligibility_info')
        self.assertEqual(history[1]['status'],'pending')

    def test_missing_old_style_uses_observed_intro(self):
        history=[{'status':'published','threads_post_id':'1','writer_review':{'v5':{'contract_version':2,'first_sentence_type':'condition'}}}]
        slots=[{'scheduled_at':'2026-11-12T08:00:00+09:00'}]
        plan_styles(slots,history,{'enabled':True,'first_new_slot':slots[0]['scheduled_at']})
        self.assertEqual(slots[0]['presentation_style'],'regular_interest')

    def test_prompt_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'threads/prompts').mkdir(parents=True)
            path='threads/prompts/intro-styles-v2-20261111.txt'
            (root/path).write_text('실제 지침',encoding='utf-8')
            policy={'intro_style_policy':{'enabled':True,'path':path,'sha256':'0'*64}}
            with self.assertRaisesRegex(ValueError,'INTRO_STYLE_HASH'):load_guidance(root,policy)
            policy['intro_style_policy']['sha256']=hashlib.sha256((root/path).read_bytes()).hexdigest()
            self.assertEqual(load_guidance(root,policy),'실제 지침')
