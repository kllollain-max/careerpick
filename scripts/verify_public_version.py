"""Bounded public version check, no credentials, no mutation."""
import hashlib
import time
import urllib.request
from pathlib import Path
BASE='https://kllollain-max.github.io/careerpick/'

def verify(root=Path('.')):
    for attempt in range(4):
        try:
            names=['gojobs.json','alio.json','alio-detail.json','operations-status.json','data/civil-service/2026.json']
            if (root/'exam-status.json').exists():names.append('exam-status.json')
            for name in names:
                req=urllib.request.Request(BASE+name+'?verify='+str(time.time_ns()),headers={'Cache-Control':'no-cache'})
                with urllib.request.urlopen(req,timeout=20) as r:
                    body=r.read(20_000_001)
                assert len(body)<=20_000_000
                assert hashlib.sha256(body).digest()==hashlib.sha256((root/name).read_bytes()).digest()
            print('Public snapshot hashes verified')
            return
        except Exception:
            if attempt==3:raise RuntimeError('public_version_not_verified') from None
            time.sleep(10)
if __name__=='__main__':verify()
