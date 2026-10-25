"""Verify reorganized files, package imports, and unchanged public URLs offline."""
import ast
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('src', 'href') and value and value.startswith('assets/'):
                self.paths.append(value.split('?', 1)[0])


class ProjectLayoutTest(unittest.TestCase):
    def setUp(self):
        # Any unexpected database or email request fails this test.
        blocker = patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network request'))
        blocker.start()
        self.addCleanup(blocker.stop)
        from api.index import app
        self.client = app.test_client()

    def test_existing_public_urls_still_serve_exact_files(self):
        for url, filename in [('/', 'index.html'), ('/index.html', 'index.html'),
                              ('/privacy.html', 'privacy.html'),
                              ('/assets/js/app.js', 'assets/js/app.js'),
                              ('/assets/css/style.css', 'assets/css/style.css')]:
            with self.client.get(url) as response:
                self.assertEqual(response.status_code, 200, url)
                self.assertEqual(response.data, (ROOT / 'public' / filename).read_bytes(), url)

    def test_html_asset_references_resolve(self):
        for page in ('index.html', 'privacy.html'):
            parser = Assets()
            parser.feed((ROOT / 'public' / page).read_text(encoding='utf-8'))
            for asset in parser.paths:
                self.assertTrue((ROOT / 'public' / asset).is_file(), asset)

    def test_secrets_and_backend_source_stay_private(self):
        for path in ('/.env', '/.git/config', '/api/index.py', '/api/services/email_delivery.py', '/assets/../../.env'):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 404, path)

    def test_vercel_and_backend_entrypoint(self):
        config = json.loads((ROOT / 'vercel.json').read_text())
        self.assertEqual(config['outputDirectory'], 'public')
        self.assertIn('api/index.py', config['functions'])
        with self.client.get('/api/health') as response:
            self.assertEqual(response.status_code, 200)
        with self.client.get('/api?__path=/api/health') as response:
            self.assertEqual(response.status_code, 200)

    def test_active_modules_compile_and_keep_relative_imports(self):
        for path in (ROOT / 'api' / 'services').glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'))
        from api.services.email_delivery import install_email_delivery
        from api.services.booking_payments import install_booking_routes
        self.assertTrue(callable(install_email_delivery))
        self.assertTrue(callable(install_booking_routes))


if __name__ == '__main__':
    unittest.main()
