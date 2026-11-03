"""Strict, offline OneSignal CSV subscription discovery.

Parse only privately obtained CSV bytes in memory. Never print IDs, save
exports, enumerate users via public endpoints, or authorize sending.
"""
import csv
import io
import uuid

MAX_BYTES = 2_000_000
MAX_ROWS = 5000


def parse_subscription_ids(csv_bytes, *, max_rows=MAX_ROWS):
    if not isinstance(csv_bytes, bytes) or len(csv_bytes) > MAX_BYTES:
        raise ValueError("Invalid or oversized private subscription export")
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Invalid CSV encoding") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("Invalid export header")
    field = next((name for name in ("subscription_id", "id") if name in reader.fieldnames), None)
    if field is None:
        raise ValueError("Missing subscription ID column")
    result = []
    seen = set()
    for count, row in enumerate(reader, 1):
        if count > max_rows:
            raise ValueError("Private export exceeds row cap")
        if None in row or not isinstance(row.get(field), str):
            raise ValueError("Malformed private export row")
        raw = row[field].strip()
        if not raw:
            continue
        try:
            sid = str(uuid.UUID(raw))
        except ValueError:
            continue
        if sid not in seen:
            seen.add(sid)
            result.append(sid)
    return result
