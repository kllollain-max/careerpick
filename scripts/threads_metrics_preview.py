"""Parse real Threads insights responses, without making requests or posting.

Unavailable or omitted values are represented by None, never inferred as zero.
API permissions, metric support and collection require independent verification.
"""
from datetime import datetime, timezone

METRICS = ('views', 'likes', 'replies', 'reposts', 'quotes')


def parse_insights(payload, post_id, captured_at=None):
    if not isinstance(post_id, str) or not post_id.isdigit():
        raise ValueError('valid post ID required')
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise ValueError('expected API data list')
    values = dict.fromkeys(METRICS)
    for metric in payload['data']:
        if not isinstance(metric, dict) or metric.get('name') not in values:
            continue
        entries = metric.get('values')
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            continue
        value = entries[0].get('value')
        if type(value) is int and value >= 0:
            values[metric['name']] = value
    return {'post_id': post_id, 'captured_at': captured_at or datetime.now(timezone.utc).isoformat(),
            'metrics': values, 'site_visits': None, 'profile_visits': None,
            'link_clicks': None, 'followers_gained': None}


def collect_post_insights(post_id, access_token, opener=None):
    """Read only: explicitly invoked by a caller, never by the publisher.

    Exceptions intentionally propagate. Do not log the request or credentials.
    Unsupported metrics/permissions may cause an API error; no zero fallback.
    """
    import json
    import urllib.parse
    import urllib.request
    if not isinstance(post_id, str) or not post_id.isdigit() or not access_token:
        raise ValueError('valid post ID and token required')
    query = urllib.parse.urlencode({'metric': ','.join(METRICS)})
    request = urllib.request.Request(
        'https://graph.threads.net/v1.0/' + post_id + '/insights?' + query,
        headers={'Authorization': 'Bearer ' + access_token, 'Accept': 'application/json'})
    from scripts.threads_http import read_response
    with read_response(request, timeout=15, opener=opener) as response:
        payload = json.load(response)
    return parse_insights(payload, post_id)


def select_milestones(published_at, snapshots):
    """Select the earliest actual snapshot at/after each milestone.

    Missing snapshots remain None; values are cumulative and never fabricated.
    """
    from datetime import timedelta
    if not isinstance(published_at, datetime) or published_at.tzinfo is None:
        raise ValueError('published_at must be timezone-aware')
    parsed = []
    for snap in snapshots:
        try:
            when = datetime.fromisoformat(snap['captured_at'])
        except (KeyError, TypeError, ValueError):
            continue
        if when.tzinfo is not None and when >= published_at:
            parsed.append((when, snap))
    parsed.sort(key=lambda item: item[0])
    result = {}
    for label, delta in (('24h', timedelta(hours=24)), ('72h', timedelta(hours=72)), ('7d', timedelta(days=7))):
        threshold = published_at + delta
        # Don't label much later snapshots as measurements near the milestone.
        deadline = threshold + timedelta(hours=12)
        result[label] = next((snap for when, snap in parsed if threshold <= when <= deadline), None)
    return result
