#!/usr/bin/env python3
"""Prepare unapproved Threads copy from the existing candidate handoff.

This is a writing aid, NOT official review, queue approval, or a publisher.
No network access, GitHub writes, or Meta requests.
"""
import argparse
import json
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo


def build_drafts(handoff):
    if handoff.get("automatic_approval") is not False or handoff.get("meta_posted") is not False:
        raise ValueError("UNSAFE_HANDOFF")
    slots = handoff.get("missing_slots", [])
    candidates = handoff.get("candidates", [])
    alternatives = handoff.get("official_source_alternatives", [])
    if not isinstance(slots, list) or not isinstance(candidates, list):
        raise ValueError("INVALID_HANDOFF")
    if not isinstance(alternatives, list):
        raise ValueError("OFFICIAL_ALTERNATIVES_INVALID")
    drafts = []
    used_notice_ids = set()
    # Reject duplicate or malformed slot identifiers before preparing any draft.
    if any(not isinstance(slot, str) for slot in slots) or len(set(slots)) != len(slots):
        raise ValueError("INVALID_OR_DUPLICATE_SLOTS")
    # Keep independent alternatives when the first official review fails.
    # These remain unapproved and cannot reach the publisher.
    for slot in slots:
      slot_drafts = 0
      for candidate in candidates:
          if not isinstance(candidate, dict):
              continue
          nid, org, title = (candidate.get(key) for key in ("notice_id", "org", "title"))
          if not all(isinstance(x, str) and x.strip() for x in (nid, org, title)) or nid in used_notice_ids:
              continue
          period = candidate.get("application_period")
          if not isinstance(period, dict) or not period.get("end"):
              continue
          # Reject future application openings, not only expired deadlines.
          start = period.get('start')
          if not isinstance(start, str) or type(period.get('start_date_only')) is not bool:
              continue
          # A date-only end has no verified cutoff clock; a timestamp does.
          end = period['end']
          if not isinstance(end, str):
              continue
          try:
              slot_at = datetime.fromisoformat(slot)
              if slot_at.utcoffset() is None:
                  continue
              if period['start_date_only']:
                  opening = date.fromisoformat(start)
                  if slot_at.astimezone(ZoneInfo('Asia/Seoul')).date() <= opening:
                      continue  # Opening-day clock not verified
              else:
                  opening = datetime.fromisoformat(start)
                  if opening.utcoffset() is None or slot_at < opening:
                      continue
              if period.get('date_only') is True:
                  end_date = date.fromisoformat(end)
                  if slot_at.astimezone(ZoneInfo('Asia/Seoul')).date() >= end_date:
                      continue  # Exact cutoff unknown on deadline day
                  deadline = end_date.isoformat() + ' (마감 시각 원문 확인)'
              elif period.get('date_only') is False:
                  parsed = datetime.fromisoformat(end)
                  if parsed.utcoffset() is None or slot_at >= parsed:
                      continue
                  deadline = parsed.strftime('%Y-%m-%d %H:%M %z')
              else:
                  continue
          except ValueError:
              continue
          # Reject untraceable period evidence before producing a review packet.
          # This is a provenance gate, not semantic official-source approval.
          evidence = candidate.get('application_evidence')
          source_ref = candidate.get('application_source_ref')
          if not isinstance(evidence, str) or len(evidence.strip()) < 8:
              continue
          if not isinstance(source_ref, str) or not source_ref.strip():
              continue
          # Candidate identity must remain traceable to immutable source snapshots.
          hashes = (candidate.get("source_post_sha256"), candidate.get("source_detail_sha256"))
          if any(not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h) for h in hashes):
              continue
          if period.get('evidence') != evidence or period.get('source_ref') != source_ref:
              continue
          # No invented headcount, requirements, or exact cutoff time.
          body = (f"{org} 채용 공고를 확인해 보세요.\n\n"
                  f"모집 공고: {title}\n"
                  f"고용형태: {candidate.get('employment') or '공식 공고 확인 필요'}\n"
                  f"접수 마감: {deadline}\n\n"
                  "지원 자격과 모집 인원은 공식 공고문에서 확인해 주세요.\n\n"
                  "자세한 사항은 프로필링크 확인")
          # V5 normally permits at most 300 characters; never auto-claim an exception.
          # Long institution/notice names must be reviewed, never truncated silently.
          if len(body) > 300:
              continue
          drafts.append({
              "notice_id": nid, "suggested_slot": slot, "draft_text": body,
              "official_url_for_private_review": candidate.get("official_url"),
              "source_post_sha256": candidate.get("source_post_sha256"),
              "source_detail_sha256": candidate.get("source_detail_sha256"),
              "application_evidence_for_review": candidate.get("application_evidence"),
              "application_source_ref": candidate.get("application_source_ref"),
              "source_snapshot_checked_at": candidate.get("source_snapshot_checked_at"),
              "recruiting_unit_for_review": {
                  "title": candidate.get("recruiting_unit_title"),
                  "count": candidate.get("recruiting_unit_count"),
                  "scope": candidate.get("recruiting_unit_scope"),
                  "verification_status": "not_verified",
              },
              "selection_review_reasons": candidate.get("selection_review_reasons", []),
              "official_detail_fields_for_review": candidate.get("official_detail_fields_for_review", {}),
              "required_review": {
                  "official_notice_and_attachments": "not_verified",
                  "recruiting_unit_and_headcount": "not_verified",
                  "employment_type": "not_verified",
                  "eligibility_and_restrictions": "not_verified",
                  "application_window": "not_verified",
                  "profile_target": "not_verified",
                  "v5_copy_and_image": "not_verified",
                  "publisher_validate_entry": "not_run",
              },
              "status": "unreviewed", "requires_official_source_review": True,
              "approved_for_queue": False, "meta_posted": False,
          })
          used_notice_ids.add(nid)
          slot_drafts += 1
          if slot_drafts >= 3:
              break
    covered = {draft["suggested_slot"] for draft in drafts}
    return {"schema_version": 1, "status": "review_required",
            "approved_for_queue": False, "drafts": drafts,
            "official_source_alternatives": [
                {"notice_id": candidate["notice_id"], "status": "unreviewed",
                 "official_url_for_private_review": candidate.get("official_url"),
                 "source_post_sha256": candidate.get("source_post_sha256"),
                 "source_detail_sha256": candidate.get("source_detail_sha256"),
                 "suggested_slot": None}
                for candidate in candidates if isinstance(candidate, dict)
                and isinstance(candidate.get("notice_id"), str)
                and candidate["notice_id"] not in used_notice_ids] + [
                {"notice_id": candidate["notice_id"], "status": "unreviewed",
                 "official_url_for_private_review": candidate.get("official_url_for_private_review"),
                 "source_post_sha256": candidate.get("source_post_sha256"),
                 "source_detail_sha256": candidate.get("source_detail_sha256"),
                 "suggested_slot": None}
                for candidate in alternatives if isinstance(candidate, dict)
                and isinstance(candidate.get("notice_id"), str)
                and candidate["notice_id"] not in used_notice_ids
                and candidate.get("status") == "unreviewed"
                and candidate.get("approved_for_queue") is False
                and candidate.get("meta_posted") is False
                and candidate.get("suggested_slot") is None],
            "slot_coverage": {
                "requested_slots": slots,
                "draft_slots": [slot for slot in slots if slot in covered],
                "no_draft_slots": [slot for slot in slots if slot not in covered],
                "approved_slots": [],
                "reason": "OFFICIAL_REVIEW_AND_PUBLISHER_VALIDATION_REQUIRED",
            }}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="threads-writer-handoff.json")
    parser.add_argument("--output", default="threads-unreviewed-drafts.json")
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = build_drafts(data)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Unreviewed drafts prepared: {len(result['drafts'])}; approved: 0; posted: 0")


if __name__ == "__main__":
    main()
