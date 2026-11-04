"""Offline inventory and fail-closed advertising preparation; no network or ads.

Run after build_public_site.py. Human review is intentionally a separate state.
"""
import hashlib
import json
import re
from pathlib import Path
from html.parser import HTMLParser

BASE='https://kllollain-max.github.io/careerpick/'
ROOT=Path(__file__).resolve().parents[1]
AD_REQUEST=re.compile(r'(?:pagead\d*\.googlesyndication\.com|googleads\.g\.doubleclick\.net|adsbygoogle)',re.I)


def placement_candidate(page_type, screen, content_state, human_reviewed=False):
    """Candidate only. This cannot load scripts, create a slot or issue a request.

    Review mode has no activation path, including same-URL app screens.
    """
    return {
        'candidate': page_type=='guide' and screen=='article' and content_state=='ready' and human_reviewed is True,
        'ad_request_allowed': False,
        'reason': 'owner_activation_approval_and_consent_implementation_required',
    }


class Inventory(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonical=[];self.og=[];self.links=[];self.title=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='title':self.in_title=True
        if tag=='link' and a.get('rel')=='canonical':self.canonical.append(a.get('href',''))
        if tag=='meta' and a.get('property')=='og:url':self.og.append(a.get('content',''))
        if tag=='a':self.links.append(a.get('href',''))
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,d):
        if self.in_title:self.title.append(d)


def inspect(output):
    rows=[];failures=[]
    for p in sorted(list(output.rglob('*.html'))):
        rel=p.relative_to(output).as_posix();s=p.read_text();t=Inventory();t.feed(s)
        kind=('job' if rel.startswith('jobs/') else 'guide_index' if rel=='guides/index.html' else 'guide' if rel.startswith('guides/') else 'organization' if rel.startswith('org-') else 'policy' if rel in ['about.html','privacy.html','contact.html'] else 'app' if rel=='index.html' else 'collection_or_tool')
        expected=BASE+(rel[:-10] if rel.endswith('index.html') else rel)
        if t.canonical!=[expected]:failures.append(rel+': canonical mismatch')
        if any(x!=expected for x in t.og):failures.append(rel+': og:url mismatch')
        if AD_REQUEST.search(s):failures.append(rel+': advertising request/slot marker')
        if not all(any(h.endswith('/'+name) or h==name for h in t.links) for name in ['about.html','privacy.html','contact.html']):failures.append(rel+': missing policy links')
        rows.append({'path':rel,'url':expected,'template':kind,'title':''.join(t.title),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'human_review':'pending','advertising':'disabled'})
    return {'html_count':len(rows),'ad_requests_enabled':False,'human_review_complete':False,'failures':failures,'pages':rows}


def main():
    report=inspect(ROOT/'dist')
    (ROOT/'build-publisher-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='pages'},ensure_ascii=False,indent=2))
    if report['failures']:raise SystemExit(1)

if __name__=='__main__':main()
