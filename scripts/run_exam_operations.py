"""Independent MPM source candidate; preserve last valid calendar on any error."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mpm_exam
from scripts.build_additional_api_candidate import display_records
from scripts.run_operations import stamp
ROOT=Path(__file__).resolve().parents[1]
PATH='data/civil-service/2026.json'

def run(root=ROOT,client_factory=mpm_exam.Client):
    output=root/'exam-operation-output';output.mkdir(exist_ok=True)
    original=(root/PATH).read_bytes()
    report=dict(source='mpm_exam',started_at=stamp(),status='failed_preserved',changed=False,dataset_year=2026)
    try:
        result=client_factory(os.environ.get('MPM_EXAM_KEY','')).collect()
        records=display_records(result['records'])
        mpm_exam.validate_records(records,expected_count=result['verification']['total_rows'])
        old=json.loads(original)
        # Normalized records are the semantic comparison, not fetch timestamps.
        previous=display_records(old['records'])
        changed=previous!=records
        candidate=dict(source=mpm_exam.DATASET_NAME,source_url=mpm_exam.SOURCE_URL,retrieved_at=stamp() if changed else old['retrieved_at'],count=len(records),records=records)
        target=output/PATH;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n')
        report.update(status='changed' if changed else 'unchanged',changed=changed,before=len(previous),after=len(records),verified_at=stamp(),snapshot_at=candidate['retrieved_at'],requests=result['verification'].get('requests'),authentication_verified=True)
    except Exception as e:
        report['error_type']=type(e).__name__
    if report['status'] in ('changed','unchanged'):
        (output/'exam-status.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    report['original_preserved']=(root/PATH).read_bytes()==original
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False));return report
if __name__=='__main__':
    r=run();sys.exit(0 if r['status'] in ('changed','unchanged') else 1)
