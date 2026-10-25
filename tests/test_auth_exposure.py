import unittest
from unittest.mock import patch, Mock
from flask_jwt_extended import create_access_token
from passlib.hash import pbkdf2_sha256
from api import index as entry


class AuthExposureTest(unittest.TestCase):
    def setUp(self):
        self.client = entry.app.test_client()
        self.user = {'id': 12, 'name': 'Test Guest', 'email': 'guest@example.com', 'role': 'guest',
                     'password': pbkdf2_sha256.hash('Password123'), 'reset_token': 'private-test-value'}
        settings = patch.dict('os.environ', {'SENDGRID_API_KEY': ''})
        settings.start(); self.addCleanup(settings.stop)
        debug = patch.dict(entry.app.config, {'DEBUG': False})
        debug.start(); self.addCleanup(debug.stop)
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network'))
        network.start(); self.addCleanup(network.stop)
        database = patch.object(entry, 'supabase_req', return_value=[self.user.copy()])
        self.database = database.start(); self.addCleanup(database.stop)

    def assert_public(self, result):
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('password', result.json['user'])
        self.assertNotIn('reset_token', result.json['user'])

    def test_password_login_does_not_disclose_hash(self):
        self.assert_public(self.client.post('/api/auth/login', json={'email': 'guest@example.com', 'password': 'Password123'}))

    def test_account_details_do_not_disclose_hash(self):
        with entry.app.app_context():
            token = create_access_token(identity='12')
        self.assert_public(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token}))

    def test_browser_cannot_forge_google_identity(self):
        result = self.client.post('/api/auth/google', json={'email': 'staff@example.com', 'google_id': 'guessed-id'})
        self.assertEqual(result.status_code, 401)
        self.database.assert_not_called()

    def test_google_token_identity_overrides_browser_email(self):
        response = Mock(ok=True)
        response.json.return_value = {'sub': 'verified-id', 'email': 'guest@example.com', 'email_verified': True, 'name': 'Guest'}
        with patch('requests.get', return_value=response):
            result = self.client.post('/api/auth/google', json={'access_token': 'test-token', 'email': 'staff@example.com'})
        self.assert_public(result)
        self.assertNotIn('staff@example.com', self.database.call_args.args[0])

    def test_google_unverified_email_is_rejected(self):
        response = Mock(ok=True)
        response.json.return_value = {'sub': 'verified-id', 'email': 'guest@example.com', 'email_verified': False}
        with patch('requests.get', return_value=response):
            result = self.client.post('/api/auth/google', json={'access_token': 'test-token'})
        self.assertEqual(result.status_code, 401)
        self.database.assert_not_called()

    def test_missing_password_cannot_authenticate_null_password_account(self):
        self.user['password'] = None
        result = self.client.post('/api/auth/login', json={'email': 'guest@example.com'})
        self.assertEqual(result.status_code, 401)
        self.database.assert_not_called()


if __name__ == '__main__':
    unittest.main()
