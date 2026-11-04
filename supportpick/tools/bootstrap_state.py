"""Restore the shipped baseline only after byte and snapshot verification."""
import hashlib,json,shutil,tempfile,zipfile
from pathlib import Path
from refresh import read_current
ROOT=Path(__file__).resolve().parents[1]
def ensure_bootstrap(destination):
    destination=Path(destination)
    if (destination/'current.json').exists():return
    metadata=ROOT/'bootstrap.json';archive=ROOT/'bootstrap-state.zip'
    if not metadata.exists() or not archive.exists():return
    expected=json.loads(metadata.read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected['archiveSha256']:raise ValueError('bootstrap_hash_mismatch')
    with tempfile.TemporaryDirectory(dir=destination.parent if destination.parent.exists() else ROOT) as tmp:
        staged=Path(tmp)/'state';staged.mkdir()
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist())>300*1024*1024:raise ValueError('bootstrap_size_limit')
            for i in z.infolist():
                p=Path(i.filename)
                if p.is_absolute() or '..' in p.parts or (i.external_attr>>16)&0o170000==0o120000:raise ValueError('unsafe_bootstrap_member')
            z.extractall(staged)
        pointer,_=read_current(staged)
        if not pointer or pointer['generation']!=expected['generation'] or pointer['count']!=expected['count']:raise ValueError('bootstrap_identity_mismatch')
        if destination.exists() and any(destination.iterdir()):raise ValueError('bootstrap_destination_not_empty')
        destination.mkdir(parents=True,exist_ok=True);shutil.copytree(staged,destination,dirs_exist_ok=True)
if __name__=='__main__':ensure_bootstrap(ROOT/'collection-state')
