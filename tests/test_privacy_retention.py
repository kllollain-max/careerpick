"""Meaningful retention boundaries, legacy protection and privacy isolation."""
import copy
from datetime import datetime, timedelta, timezone
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scripts.privacy_retention import MetadataError, audit_legacy, decide, review, GATES
from scripts.build_public_site import write_text_atomic

NOW = datetime(2026, 11, 4, 6, tzinfo=timezone.utc)
OK = {key: True for key in GATES}
def stamp(days): return (NOW - timedelta(days=days)).isoformat()
def row(kind, days=100, **extra):
 return dict(kind=kind, event_at=stamp(days), event_verified=True, **extra)

class RetentionTests(unittest.TestCase):
 def test_log_cap_boundary_and_early_purpose_end(self):
  self.assertEqual(decide(row('delivery_log',29),now=NOW,evidence=OK).action,'keep')
  x=decide(row('delivery_log',30),now=NOW,evidence=OK);self.assertEqual(x.action,'delete_candidate');self.assertFalse(x.overdue)
  x=decide(row('delivery_log',31),now=NOW,evidence=OK);self.assertTrue(x.overdue)
  self.assertEqual(decide(row('delivery_log',5,purpose_ended_at=stamp(1)),now=NOW,evidence=OK).action,'delete_candidate')
 def test_dedup_90_days_and_replay_gate(self):
  self.assertEqual(decide(row('dedup_record',89),now=NOW,evidence=OK).action,'keep')
  self.assertEqual(decide(row('dedup_record',90),now=NOW,evidence=OK).action,'delete_candidate')
  missing=dict(OK,replay_prevention_verified=False)
  self.assertEqual(decide(row('dedup_record'),now=NOW,evidence=missing).action,'blocked')
 def test_purpose_finished_inquiry_does_not_wait_30_days(self):
  x=decide(row('inquiry',1,purpose_ended_at=stamp(0)),now=NOW,evidence=OK)
  self.assertEqual(x.action,'delete_candidate');self.assertEqual(x.deadline,NOW)
 def test_follow_up_has_cap_and_can_end_earlier(self):
  x=row('inquiry',40,purpose_ended_at=stamp(10),follow_up_required=True)
  self.assertEqual(decide(x,now=NOW,evidence=OK).action,'keep')
  x['follow_up_ended_at']=stamp(1)
  self.assertEqual(decide(x,now=NOW,evidence=OK).action,'delete_candidate')
  x.pop('follow_up_ended_at');x['purpose_ended_at']=stamp(30)
  self.assertEqual(decide(x,now=NOW,evidence=OK).action,'delete_candidate')
 def test_unanswered_inquiry_needs_closure_not_auto_delete(self):
  x=row('inquiry',40,last_contact_at=stamp(30))
  self.assertEqual(decide(x,now=NOW,evidence=OK).action,'review_closure')
 def test_revocation_is_immediate_candidate_with_five_day_target(self):
  x=row('push_subscription',1,revocation_at=stamp(0),identity_verified=True)
  d=decide(x,now=NOW,evidence=OK);self.assertEqual(d.action,'delete_candidate');self.assertTrue(d.stop_delivery_candidate);self.assertEqual(d.deadline,NOW+timedelta(days=5))
  x['event_at']=stamp(10);x['revocation_at']=stamp(6);self.assertTrue(decide(x,now=NOW,evidence=OK).overdue)
 def test_unverified_subject_or_missing_revocation_never_deletes(self):
  for x in [row('push_subscription',1,revocation_at=stamp(0)),row('push_subscription',1,opted_in=False)]:
   self.assertEqual(decide(x,now=NOW,evidence=OK).action,'blocked')
  self.assertEqual(decide(row('push_subscription',1,opted_in=True),now=NOW,evidence=OK).action,'keep')
 def test_local_data_stays_user_controlled(self):
  self.assertEqual(decide({'kind':'local_record'},now=NOW,evidence=OK).action,'client_managed')
 def test_legacy_missing_timestamp_cannot_be_redated(self):
  x={'kind':'dedup_record','event_verified':True};before=copy.deepcopy(x)
  self.assertEqual(decide(x,now=NOW,evidence=OK).action,'blocked');self.assertEqual(x,before)
  self.assertEqual(decide({'kind':'dedup_record','event_at':stamp(100),'event_verified':False},now=NOW,evidence=OK).action,'blocked')
 def test_bad_clock_timezone_and_future_dates_block(self):
  with self.assertRaises(MetadataError): decide(row('delivery_log'),now=NOW.replace(tzinfo=None))
  with self.assertRaises(MetadataError): review([],now=NOW.replace(tzinfo=None))
  for t in ['2026-11-01','broken',(NOW+timedelta(seconds=1)).isoformat()]:
   x=row('delivery_log');x['event_at']=t;self.assertEqual(decide(x,now=NOW,evidence=OK).action,'blocked')
 def test_every_copy_and_restore_prerequisite_is_required(self):
  for gate in ['scope_verified','all_copies_accounted_for','restore_protection_verified']:
   evidence=dict(OK);evidence[gate]=False
   self.assertEqual(decide(row('delivery_log'),now=NOW,evidence=evidence).action,'blocked')
 def test_provider_scope_required_for_subscription(self):
  evidence=dict(OK,provider_scope_verified=False)
  d=decide(row('push_subscription',1,revocation_at=stamp(0),identity_verified=True),now=NOW,evidence=evidence)
  self.assertEqual(d.action,'blocked');self.assertTrue(d.stop_delivery_candidate)
 def test_no_assumed_permission_without_evidence(self):
  self.assertEqual(decide(row('delivery_log'),now=NOW).action,'blocked')
 def test_inflight_or_uncertain_is_manual_review(self):
  for kind in ['delivery_log','dedup_record']:
   result=decide(row(kind,unresolved=True),now=NOW,evidence=OK)
   self.assertEqual(result.reason,'unresolved_delivery_requires_review');self.assertTrue(result.overdue)
 def test_legal_hold_requires_finite_verified_basis(self):
  x=row('delivery_log',legal_hold_until=(NOW+timedelta(days=2)).isoformat())
  self.assertEqual(decide(x,now=NOW,evidence=OK).action,'blocked')
  x['legal_basis_verified']=True;self.assertEqual(decide(x,now=NOW,evidence=OK).action,'restricted_hold')
  x['legal_hold_until']=stamp(1);self.assertEqual(decide(x,now=NOW,evidence=OK).action,'delete_candidate')
 def test_backup_inherits_original_deadline(self):
  x={'kind':'backup_copy','event_verified':True,'original_deadline_at':stamp(1)}
  self.assertEqual(decide(x,now=NOW,evidence=OK).action,'delete_candidate')
  x.pop('original_deadline_at');self.assertEqual(decide(x,now=NOW,evidence=OK).action,'blocked')
 def test_unknown_fields_and_non_boolean_attestation_rejected(self):
  for extra in [{'email':'private@example.invalid'},{'token':'secret'},{'unresolved':'false'}]:
   x=row('delivery_log');x.update(extra);self.assertEqual(decide(x,now=NOW,evidence=OK).action,'blocked')
  self.assertEqual(decide(row('delivery_log'),now=NOW,evidence={'scope_verified':'yes'}).action,'blocked')
 def test_impossible_event_order_is_not_a_cleanup_candidate(self):
  x=row('inquiry',1,purpose_ended_at=stamp(5));self.assertEqual(decide(x,now=NOW,evidence=OK).action,'blocked')
 def test_summary_never_echoes_input_and_performs_no_io(self):
  rows=[row('delivery_log')];before=copy.deepcopy(rows)
  with patch('socket.socket.connect',side_effect=AssertionError('No network')):
   out=review(rows,now=NOW,evidence=OK)
  self.assertEqual(rows,before);self.assertEqual(out['actual_deleted'],0);self.assertFalse(out['live_activation_ready']);self.assertNotIn('2026-',json.dumps(out))
 def test_legacy_inventory_preserves_ids_and_reports_no_deletion(self):
  ledger={'delivered':['a'*64],'pending':[]};queue={'version':1,'tasks':{'a'*64:{'state':'accepted','subscriber_hash':'b'*64,'message_id':'synthetic'}}};before=copy.deepcopy((ledger,queue))
  result=audit_legacy(ledger,queue);self.assertEqual(result['legacy_records_requiring_timestamp_review'],2);self.assertEqual(result['actual_deleted'],0);self.assertNotIn('synthetic',json.dumps(result));self.assertNotIn('a'*64,json.dumps(result));self.assertEqual((ledger,queue),before)
 def test_empty_legacy_is_not_proof_all_provider_data_is_gone(self):
  x=audit_legacy({'delivered':[],'pending':[]},{'version':1,'tasks':{}})
  self.assertEqual(x['history_and_provider_coverage'],'not_verified')
  with self.assertRaises(MetadataError):audit_legacy({}, {'version':1,'tasks':{}})
  with self.assertRaises(MetadataError):review([],now=NOW,evidence={'scope_verified':'yes'})
 def test_conflicting_legacy_cannot_be_treated_as_empty(self):
  with self.assertRaises(MetadataError):audit_legacy({'delivered':['a'*64],'pending':['a'*64]},{'version':1,'tasks':{}})
 def test_cli_example_and_secret_input_never_mutate_or_leak(self):
  out=subprocess.run([sys.executable,'scripts/privacy_retention.py','--example','--at',NOW.isoformat()],capture_output=True,text=True,check=True)
  self.assertEqual(json.loads(out.stdout)['actual_deleted'],0)
  secret='NEVER_ECHO_THIS_PRIVATE_TOKEN';bad=json.dumps({'records':[dict(row('delivery_log'),token=secret)]})
  out=subprocess.run([sys.executable,'scripts/privacy_retention.py','--at',NOW.isoformat()],input=bad,capture_output=True,text=True)
  self.assertNotIn(secret,out.stdout+out.stderr);self.assertEqual(json.loads(out.stdout)['actual_deleted'],0)
  out=subprocess.run([sys.executable,'scripts/privacy_retention.py','--at',NOW.isoformat()],input='{"secret":"'+secret,capture_output=True,text=True)
  self.assertEqual(out.returncode,2);self.assertNotIn(secret,out.stdout+out.stderr)
 def test_cli_has_no_apply_switch(self):
  out=subprocess.run([sys.executable,'scripts/privacy_retention.py','--apply'],capture_output=True,text=True)
  self.assertNotEqual(out.returncode,0)
  secret='DO_NOT_ECHO_ARGUMENT_VALUE'
  out=subprocess.run([sys.executable,'scripts/privacy_retention.py','--unknown',secret],capture_output=True,text=True)
  self.assertNotEqual(out.returncode,0);self.assertNotIn(secret,out.stdout+out.stderr)

 def test_atomic_transformed_output_preserves_complete_utf8(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'page.html';p.write_text('original')
   write_text_atomic(p,'<p>커리어픽 /careerpick/</p>')
   self.assertEqual(p.read_text(),'<p>커리어픽 /careerpick/</p>')
   self.assertEqual(p.stat().st_mode & 0o777,0o644)
   self.assertEqual([x.name for x in Path(directory).iterdir()],['page.html'])
 def test_failed_atomic_replace_keeps_original_output(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'page.html';p.write_text('original')
   with patch('scripts.build_public_site.os.replace',side_effect=OSError('synthetic failure')):
    with self.assertRaises(OSError):write_text_atomic(p,'replacement')
   self.assertEqual(p.read_text(),'original')
   self.assertEqual([x.name for x in Path(directory).iterdir()],['page.html'])

if __name__=='__main__':unittest.main()
