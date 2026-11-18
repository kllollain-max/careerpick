"""Read-only ALIO editorial shortlist; does not claim measured search popularity."""
import argparse
import json
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit

def as_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None

def verified_kst_clock(value):
    """Parse only a real, exact official KST timestamp; invalid source data is not proof."""
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00', value):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None

def seat_count(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 1 <= value <= 5000 else None
    if isinstance(value, str) and re.fullmatch(r'\d{1,4}', value.strip()):
        count = int(value.strip())
        return count if 1 <= count <= 5000 else None
    return None

def shortlist(feed, today, limit=30, verified_windows=None, as_of_instant=None,
              verified_duplicate_representatives=None):
    if not isinstance(feed, dict) or not isinstance(feed.get('posts'), list):
        raise ValueError('invalid_feed')
    if not isinstance(today, date) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('invalid_arguments')
    if as_of_instant is not None:
        if (not isinstance(as_of_instant, datetime) or as_of_instant.tzinfo is None
                or as_of_instant.utcoffset() is None
                or as_of_instant.astimezone(ZoneInfo('Asia/Seoul')).date() != today):
            raise ValueError('invalid_as_of_instant')
    selected, rejected, seen = [], {}, set()
    verified_windows = verified_windows or {}
    for p in feed['posts']:
        if not isinstance(p, dict):
            rejected['malformed'] = rejected.get('malformed', 0) + 1
            continue
        identity, title = p.get('id'), p.get('title')
        end = as_date(p.get('due'))
        url = p.get('url', '')
        emp = p.get('emp') if isinstance(p.get('emp'), list) else []
        if not isinstance(identity, str) or not re.fullmatch(r'a\d+', identity) or identity in seen:
            reason = 'duplicate_or_bad_id'
        elif not isinstance(title, str) or not title.strip():
            reason = 'missing_title'
        elif not end:
            reason = 'unknown_deadline'
        elif end < today:
            reason = 'expired'
        elif not isinstance(url, str) or urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'job.alio.go.kr':
            reason = 'unverified_source'
        else:
            reason = None
            start_day_clock_unknown = False
            # Only exact ALIO identity + official posting-end binding can
            # exclude a FUTURE reception. Never treat publication as reception.
            proof = verified_windows.get(identity, {})
            if (isinstance(proof, dict) and p.get('alio') is True
                    and proof.get('organization') == p.get('org')
                    and proof.get('title') == title
                    and proof.get('source_end_date') == str(p.get('due', ''))[:10]
                    and (proof.get('expected_source_seats') is None
                         or proof['expected_source_seats'] == str(p.get('n')))
                    and (not proof.get('source_employment')
                         or proof['source_employment'] == emp)):
                if (proof.get('confirmed_employment') == '계약직'
                        and proof.get('source_employment') == emp):
                    reason = 'official_employment_conflict'
                elif proof.get('application_status_unconfirmed') is True:
                    reason = 'official_current_status_unconfirmed'
                start = proof.get('application_start')
                end_text = proof.get('application_end_date')
                cutoff_clock = verified_kst_clock(proof.get('application_cutoff'))
                start_clock = verified_kst_clock(start)
                start_day = as_date(start) if isinstance(start, str) else None
                end_day = (as_date(end_text) if isinstance(end_text, str)
                           and re.fullmatch(r'\d{4}-\d{2}-\d{2}', end_text) else None)
                if ((start_day and end_day and start_day > end_day)
                        or (start_clock and cutoff_clock and start_clock > cutoff_clock)
                        or (start_day and cutoff_clock and start_day > cutoff_clock.date())
                        or (end_day and cutoff_clock and end_day != cutoff_clock.date())):
                    # Official-window evidence is internally inconsistent.
                    # Never suppress a candidate using ANY part of this proof.
                    start = None
                    end_text = None
                    cutoff_clock = None
                if (isinstance(start, str) and re.fullmatch(
                        r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}\+09:00)?', start)):
                    start_day = as_date(start)
                    if start_day and start_day > today:
                        reason = 'official_reception_not_open'
                    elif (start_day == today and 'T' not in start
                          and as_of_instant is not None):
                        # A date alone cannot certify the opening HOUR.
                        # Keep it in the broad top queue, not the current regular-20 queue.
                        start_day_clock_unknown = True
                    elif (as_of_instant is not None and start_clock is not None
                          and as_of_instant < start_clock):
                        reason = 'official_reception_not_open'
                if (reason is None and isinstance(end_text, str)
                        and re.fullmatch(r'\d{4}-\d{2}-\d{2}', end_text)):
                    end_day = as_date(end_text)
                    if (end_day and end_day < today
                            and (start_day is None or start_day <= end_day)):
                        # A confirmed date-only reception end is authoritative
                        # AFTER the day; do not fabricate a same-day cutoff.
                        reason = 'official_reception_closed_by_date'
                # A verified reception cutoff is different from ALIO's
                # publication end (often 23:59). Apply the clock only when
                # bound to the exact ALIO ID, organization, title and end date.
                if (reason is None and as_of_instant is not None
                        and cutoff_clock is not None
                        and as_of_instant >= cutoff_clock):
                    reason = 'official_reception_closed'
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        seen.add(identity)
        seats = seat_count(p.get('n'))
        permanent = any(isinstance(x, str) and ('정규직' in x and '비정규직' not in x) for x in emp)
        # ALIO's total seats are NOT necessarily regular seats if the notice mixes
        # regular and intern/permanent-contract roles. A mixed notice must never
        # receive the regular-only priority boost before its official split is read.
        regular_only = len(emp) == 1 and isinstance(emp[0], str) and emp[0].strip() == '정규직'
        mixed_regular = permanent and not regular_only
        # Score is editorial triage only, NOT search demand, application eligibility or popularity.
        score = (100 if regular_only else 0) + (min(seats, 100) if seats is not None else 0)
        selected.append({'id': identity, 'title': title.strip(), 'organization': str(p.get('org', '')),
                         'due': end.isoformat(), 'employment': emp, 'reported_seats': seats,
                         'permanent_classified': permanent, 'regular_only_classified': regular_only,
                         'mixed_employment_with_regular': mixed_regular,
                         'triage_score': score, 'official_url': url,
                         'official_start_day_clock_unconfirmed': start_day_clock_unknown})
    selected.sort(key=lambda x: (-x['triage_score'], x['due'], x['id']))
    # A separate 20-row EDITORIAL WORK QUEUE, never a verified list of
    # independent, currently open regular positions. Keep the original
    # cross-employment triage output stable for its existing consumers.
    caution_terms = ('인턴', '체험형', '기간제', '계약직', '위촉직',
                     '개방형직위', '공무직', '비정규직', '파견직')
    priority_sector_terms = ('발전', '전력', '에너지', '철도', '교통',
                             '금융', '은행', '신용보증', '공제', '연금', '물류')
    regular_review, held_regular, verified_duplicate_exclusions = [], [], []
    held_start_day_clock_unknown = []
    # Only a current-source fingerprint verified SAME-notice decision may
    # suppress a duplicate from the editor's regular-only 20-row work queue.
    # Leave the original cross-employment `top` output and public pages intact.
    verified_duplicate_representatives = verified_duplicate_representatives or {}
    # Never hide a regular candidate behind a representative that cannot itself
    # appear in this regular-20 review queue (mixed employment, title HOLD,
    # unknown same-day opening hour, or another duplicate pointing onward).
    # The source-original SHA checks are still the resolver's responsibility.
    eligible_review_representatives = {
        candidate['id'] for candidate in selected
        if candidate['regular_only_classified']
        and not candidate['official_start_day_clock_unconfirmed']
        and not any(term in candidate['title'] for term in caution_terms)
        and verified_duplicate_representatives.get(candidate['id'], candidate['id']) == candidate['id']
    }
    for item in selected:
        if not item['regular_only_classified']:
            continue
        representative = verified_duplicate_representatives.get(item['id'])
        if (isinstance(representative, str) and representative != item['id']
                and representative in eligible_review_representatives):
            verified_duplicate_exclusions.append({
                'id': item['id'], 'representative_id': representative})
            continue
        if item['official_start_day_clock_unconfirmed']:
            held_start_day_clock_unknown.append(item['id'])
            continue
        if any(term in item['title'] for term in caution_terms):
            held_regular.append(item['id'])
            continue
        sector_text = item['organization'] + ' ' + item['title']
        priority_sector = (any(term in sector_text for term in priority_sector_terms)
                           or '금융.보험' in next((str(p.get('desc', '')) for p in feed['posts']
                                                  if isinstance(p, dict) and p.get('id') == item['id']), ''))
        regular_review.append({**item, 'priority_sector_hint': priority_sector,
                               'official_position_and_qualification_review': 'pending',
                               'official_reception_status': 'unverified'})
    regular_review.sort(key=lambda x: (not x['priority_sector_hint'],
                                       -(x['reported_seats'] or 0), x['due'], x['id']))
    return {'as_of': today.isoformat(), 'source': 'ALIO existing validated feed', 'source_rows': len(feed['posts']),
            'eligible_rows': len(selected), 'excluded': rejected, 'top': selected[:limit],
            'regular_review_candidates': regular_review[:min(limit, 20)],
            'regular_review_candidate_rows': len(regular_review),
            'regular_review_verified_duplicate_exclusions': verified_duplicate_exclusions,
            'regular_title_conflict_hold_ids': held_regular,
            'regular_start_day_clock_unconfirmed_hold_ids': held_start_day_clock_unknown,
            'limitations': ['Not a search-volume or actual popularity ranking',
                            'Reported hiring counts are source fields, not independently confirmed headcount',
                            'Mixed-employment notices report total seats, not verified regular-only seats; no regular-only score boost',
                            'Application requirements and current status must be reviewed at the official page',
                            'Known future official reception dates are excluded only on exact notice identity',
                            'Date-only evaluation cannot certify same-day opening or closing hours',
                            'A date-only reception opening TODAY is held from the current regular-20 queue when checking live KST time',
                            'An officially confirmed date-only reception END excludes only from the following calendar date',
                            'Real-time exclusion uses only identity-bound verified opening/cutoff clocks; historical --as-of remains date-only',
                            'Unknown and expired deadlines are never promoted',
                            'Regular review candidates are UNVERIFIED; official duties, eligibility, independent seats and live reception require separate original-source review',
                            'Only exact-current-source dual-original verified same notices are removed from the 20-row review queue, not the all-employment top list',
                            'Title/employment conflicts are held for review, not declared nonregular',
                            'Sector labels are editorial hints, not popularity or eligibility evidence']}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='alio.json')
    parser.add_argument('--output', default='review-only/job-priority-candidates.json')
    parser.add_argument('--as-of', default=None,
                        help='Historical date-only review; omit for current Korea-time cutoff checks')
    args = parser.parse_args()
    now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
    review_date = date.fromisoformat(args.as_of) if args.as_of else now_kst.date()
    # Use already reviewed originals; no network, collector or source JSON writes.
    try:
        from scripts.build_job_pages import (VERIFIED_DUTIES, VERIFIED_APPLICATION_NOTICES,
                                             CONFIRMED_APPLICATION_CUTOFFS)
    except ModuleNotFoundError:
        from build_job_pages import (VERIFIED_DUTIES, VERIFIED_APPLICATION_NOTICES,
                                     CONFIRMED_APPLICATION_CUTOFFS)
    windows = {}
    for pid, proof in {**VERIFIED_DUTIES, **VERIFIED_APPLICATION_NOTICES}.items():
        if not isinstance(proof, dict) or not (proof.get('application_start') or proof.get('application_status_unconfirmed')):
            continue
        official_cutoff = CONFIRMED_APPLICATION_CUTOFFS.get(pid, '')
        source_end = proof.get('source_end_date') or official_cutoff[:10]
        if source_end:
            windows[pid] = {**proof, 'source_end_date': source_end}
            if official_cutoff:
                windows[pid]['application_cutoff'] = official_cutoff
    # The canonical comparison is invalidated by changed/missing source data.
    # Do not infer duplicates merely from a matching institution/title/date.
    try:
        from scripts.notice_review import load as load_notice_reviews
    except ModuleNotFoundError:
        from notice_review import load as load_notice_reviews
    resolved = load_notice_reviews(Path(args.source).resolve().parent)
    verified_duplicates = {
        pid: proof['representative_id'] for pid, proof in resolved.items()
        if proof.get('decision') == 'same_notice'
        and pid != proof.get('representative_id')
        and isinstance(proof.get('representative_id'), str)
    }
    report = shortlist(json.loads(Path(args.source).read_text(encoding='utf-8')),
                       review_date, verified_windows=windows,
                       as_of_instant=now_kst if args.as_of is None else None,
                       verified_duplicate_representatives=verified_duplicates)
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'source_rows': report['source_rows'], 'eligible_rows': report['eligible_rows'],
                      'top_rows': len(report['top']), 'excluded': report['excluded']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
