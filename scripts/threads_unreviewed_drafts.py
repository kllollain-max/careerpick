#!/usr/bin/env python3
"""Prepare unapproved Threads copy from the existing candidate handoff.

This is a writing aid, NOT official review, queue approval, or a publisher.
No network access, GitHub writes, or Meta requests.
"""
import argparse
import json
from pathlib import Path


def build_drafts(handoff):
    if handoff.get("automatic_approval") is not False or handoff.get("meta_posted") is not False:
        raise ValueError("UNSAFE_HANDOFF")
    slots = handoff.get("missing_slots", [])
    candidates = handoff.get("candidates", [])
    if not isinstance(slots, list) or not isinstance(candidates, list):
        raise ValueError("INVALID_HANDOFF")
    drafts = []
    for slot, candidate in zip(slots, candidates):
        if not isinstance(candidate, dict):
            continue
        nid, org, title = (candidate.get(key) for key in ("notice_id", "org", "title"))
        if not all(isinstance(x, str) and x.strip() for x in (nid, org, title)):
            continue
        period = candidate.get("application_period")
        if not isinstance(period, dict) or not period.get("end"):
            continue
        # No invented headcount, requirements, or exact cutoff time.
        body = (f"{org} 채용 공고를 확인해 보세요.\n\n"
                f"모집 공고: {title}\n"
                f"고용형태: {candidate.get('employment') or '공식 공고 확인 필요'}\n"
                f"접수 마감: {period['end']} (정확한 시각은 원문 확인)\n\n"
                "지원 자격과 모집 인원은 공식 공고문에서 확인해 주세요.\n\n"
                "자세한 사항은 프로필링크 확인")
        drafts.append({
            "notice_id": nid, "suggested_slot": slot, "draft_text": body,
            "official_url_for_private_review": candidate.get("official_url"),
            "source_post_sha256": candidate.get("source_post_sha256"),
            "source_detail_sha256": candidate.get("source_detail_sha256"),
            "status": "unreviewed", "requires_official_source_review": True,
            "approved_for_queue": False, "meta_posted": False,
        })
    return {"schema_version": 1, "status": "review_required",
            "approved_for_queue": False, "drafts": drafts}


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
