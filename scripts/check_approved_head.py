"""Reject a stale checkout before it can replace newer public editorial links."""
import argparse
import re
import subprocess

def check(approved):
    if not re.fullmatch(r'[0-9a-f]{40}', approved): raise ValueError('invalid_approved_sha')
    checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if checkout != approved: raise ValueError('approved_checkout_mismatch')
    refs = subprocess.check_output(['git', 'ls-remote', '--exit-code', 'origin', 'refs/heads/main'], text=True, timeout=30).splitlines()
    if len(refs) != 1: raise ValueError('current_main_unverified')
    head, name = refs[0].split()
    if name != 'refs/heads/main' or head != approved:
        raise ValueError('main_advanced_rebuild_latest_source_without_overwriting_new_links')
    return head

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-sha', required=True)
    print('Verified current main:', check(parser.parse_args().approved_sha))
