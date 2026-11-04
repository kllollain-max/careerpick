"""Package only the SupportPick public files. No API calls or deployment."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ('index.html', 'privacy.html', 'about.html', 'icon.svg', 'careerpick-base.css',
          'styles.css', 'data.js', 'core.js', 'app.js')

class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href', 'src') and value and not urlsplit(value).scheme and not value.startswith('#'):
                target = (ROOT / urlsplit(value).path).resolve()
                if value == './':
                    target = ROOT / 'index.html'
                if not target.is_file() or not target.is_relative_to(ROOT):
                    raise ValueError('Missing or unsafe local asset: ' + value)

def build(destination):
    output = Path(destination).resolve()
    if output == ROOT or ROOT.is_relative_to(output) or (output.is_relative_to(ROOT) and output != ROOT / 'dist'):
        raise ValueError('Use dist/ or an output directory outside the source folder.')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty; existing files are preserved.')
    output.mkdir(parents=True, exist_ok=True)
    payload = json.loads((ROOT / 'data.json').read_text())
    embedded = (ROOT / 'data.js').read_text().strip().removeprefix('window.SUPPORTPICK_DATA = ').removesuffix(';')
    if json.loads(embedded) != payload:
        raise ValueError('data.json and data.js differ')
    if len({p['id'] for p in payload['items']}) != len(payload['items']):
        raise ValueError('Duplicate benefit ID')
    for name in PUBLIC:
        source = ROOT / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Unsafe source: ' + name)
        text = source.read_text()
        if name.endswith('.html'):
            Links().feed(text)
            if not re.search(r'<meta name="robots" content="noindex,nofollow">', text):
                raise ValueError('Preview indexing protection missing')
        shutil.copyfile(source, output / name)
    (output / '.nojekyll').write_text('')
    return {'publicFiles': len(PUBLIC) + 1, 'benefits': len(payload['items']), 'published': False,
            'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
