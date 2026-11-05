import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'check_public_readiness.py'
spec = importlib.util.spec_from_file_location('hostaudit', SCRIPT)
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class HostAuditTests(unittest.TestCase):
    def fixture(self, project='supportpick', mismatch=False, changing=False, robots=b'User-agent: *\nAllow: /'):
        base = audit.HOST + project + '/'
        paths = ['', 'about.html', 'privacy.html', 'contact.html']
        paths += ['terms.html', 'benefits/149200000026/', 'benefits/105100000001/'] if project == 'supportpick' else ['jobs/a1.html', 'guides/example.html']
        urls = [base + p for p in paths]
        bodies = {u: ('<link rel="canonical" href="'+u+'"><h1>안내</h1>').encode() for u in urls}
        manifest = {'sourceRevision': 'a'*40, 'generation': 'test-1', 'benefits': 2,
                    'files': {(u[len(base):] or 'index.html') + ('index.html' if u[len(base):].endswith('/') else ''):
                              hashlib.sha256(v).hexdigest() for u, v in bodies.items()}}
        if mismatch: manifest['files']['privacy.html'] = 'wrong'
        bodies.update({audit.HOST: b'<meta name="google-adsense-account" content="ca-pub-1234567890123456">',
                       audit.HOST + 'ads.txt': b'google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0',
                       audit.HOST + 'robots.txt': robots,
                       base + 'sitemap.xml': ('<urlset xmlns="'+audit.NS['s']+'">'+''.join('<url><loc>'+u+'</loc></url>' for u in urls)+'</urlset>').encode(),
                       base + 'site-manifest.json': json.dumps(manifest).encode()})
        calls = []
        def loader(url):
            calls.append(url)
            raw = bodies[url]
            if changing and url.endswith('site-manifest.json') and calls.count(url) == 2: raw += b' '
            return {'status': 200, 'sha256': hashlib.sha256(raw).hexdigest()}, raw
        return loader, calls, bodies

    def test_both_projects_use_host_registration_and_host_robots(self):
        for project in ['careerpick', 'supportpick']:
            load, calls, _ = self.fixture(project)
            result = audit.run(project, load)
            self.assertEqual(result['errors'], [])
            self.assertEqual(result['unverified'], [])
            self.assertFalse(result['independentPathRegistration'])
            self.assertNotIn(audit.HOST + project + '/robots.txt', calls)

    def test_root_publisher_mismatch_fails(self):
        load, _, bodies = self.fixture()
        bodies[audit.HOST + 'ads.txt'] = b'google.com, pub-9999999999999999, DIRECT, f08c47fec0942fa0'
        self.assertIn('host_ads_txt_publisher_mismatch', audit.run('supportpick', load)['errors'])

    def test_public_manifest_hash_mismatch_fails(self):
        load, _, _ = self.fixture(mismatch=True)
        self.assertIn('public_manifest_hash_mismatch: privacy.html', audit.run('supportpick', load)['errors'])

    def test_deployment_during_check_is_unverified(self):
        load, _, _ = self.fixture(changing=True)
        self.assertIn('public_release_changed_during_audit', audit.run('supportpick', load)['unverified'])

    def test_ad_crawler_specific_block_is_detected(self):
        load, _, _ = self.fixture(robots=b'User-agent: Mediapartners-Google\nDisallow: /supportpick/')
        self.assertTrue(any('robots_disallow: Mediapartners-Google' in e for e in audit.run('supportpick', load)['errors']))

    def test_http_failure_cannot_become_pass(self):
        load, _, _ = self.fixture()
        def fail(url):
            return ({'status': 404}, b'') if url.endswith('privacy.html') else load(url)
        self.assertTrue(any('privacy.html: 404' in e for e in audit.run('supportpick', fail)['errors']))

    def test_none_alias_does_not_confuse_preview_directive(self):
        self.assertTrue(audit.blocked(['NONE']))
        self.assertFalse(audit.blocked(['max-image-preview:none']))
