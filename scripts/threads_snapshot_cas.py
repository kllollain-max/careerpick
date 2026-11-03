"""Backend-neutral snapshot merging with conditional writes.

Backend.read() -> (version, dict); backend.compare_and_swap(version, dict)
returns bool. Backend must durably and atomically implement the contract.
No production backend is configured here.
"""
import copy


def put_snapshot(backend, post_id, milestone, snapshot, max_attempts=5):
    if not isinstance(post_id, str) or not post_id.isdigit() or milestone not in ('24h', '72h', '7d'):
        raise ValueError('invalid snapshot key')
    if not isinstance(snapshot, dict) or snapshot.get('post_id') != post_id or not isinstance(snapshot.get('metrics'), dict):
        raise ValueError('invalid snapshot')
    key = post_id + ':' + milestone
    for _ in range(max_attempts):
        version, state = backend.read()
        if not isinstance(state, dict) or not isinstance(state.get('posts'), dict):
            raise ValueError('invalid existing state')
        if key in state['posts']:
            return False
        updated = copy.deepcopy(state)
        updated['posts'][key] = copy.deepcopy(snapshot)
        if backend.compare_and_swap(version, updated):
            return True
    raise RuntimeError('snapshot CAS conflict; retry without overwriting')
