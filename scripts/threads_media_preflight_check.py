"""Read-only CI acceptance of the current media forecast, without fixed dates."""
import argparse
import json


def check_report(report):
    slots = report.get('future_slots')
    approved = report.get('approved_future_slots')
    invalid = report.get('invalid_ready_entries')
    if not isinstance(slots, list) or not slots or not isinstance(approved, list) or not isinstance(invalid, list):
        raise ValueError('MEDIA_REPORT_SCHEMA')
    if invalid:
        raise ValueError('INVALID_REVIEWED_MEDIA_FORECAST')
    if any(slot not in slots for slot in approved):
        raise ValueError('APPROVAL_OUTSIDE_CURRENT_HORIZON')
    if report.get('next_slot_missing') is not False or slots[0] not in approved:
        raise ValueError('NEXT_REVIEWED_SLOT_NOT_VALIDATED')
    return slots[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    with open(args.report, encoding='utf-8') as stream:
        report = json.load(stream)
    print('SAFE_MEDIA_FORECAST_VERIFIED', check_report(report))


if __name__ == '__main__':
    main()
