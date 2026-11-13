import base64
import os
import unittest
from unittest.mock import Mock, patch

from passlib.hash import pbkdf2_sha256
from api.index import app, create_access_token


class SecurityTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config['SECURITY_RATE_LIMIT_ENABLED'] = False
        app.extensions['security_rate_buckets'].clear()
        self.email = patch.dict(os.environ, {'SENDGRID_API_KEY': '', 'FROM_EMAIL': ''})
        self.email.start()
        with app.app_context():
            self.token = create_access_token(identity='7')
        self.headers = {'Authorization': 'Bearer ' + self.token}
        self.guest = {'id': 7, 'name': 'QA Guest', 'email': 'qa@example.com', 'role': 'guest'}

    def tearDown(self):
        app.config['SECURITY_RATE_LIMIT_ENABLED'] = True
        app.extensions['security_rate_buckets'].clear()
        self.email.stop()

    def test_health_does_not_advertise_configuration(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.json, {'status': 'online'})
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')

    def test_headers_apply_to_html_and_api(self):
        for path in ['/', '/api/health']:
            response = self.client.get(path)
            self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
            response.close()

    def test_private_files_not_served(self):
        for path in ['/.env', '/.git/config', '/api/index.py', '/api/security.py', '/assets/../../.env']:
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_cross_origin_mutation_and_cors(self):
        response = self.client.post('/api/auth/login', json={}, headers={'Origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)
        allowed = self.client.options('/api/auth/login', headers={'Origin': 'http://localhost:5000', 'Access-Control-Request-Method': 'POST'})
        self.assertEqual(allowed.headers['Access-Control-Allow-Origin'], 'http://localhost:5000')

    def test_json_types_and_size(self):
        for payload in [[], 'text', 3]:
            self.assertEqual(self.client.post('/api/auth/login', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/api/auth/login', data='not json', content_type='text/plain').status_code, 415)
        self.assertEqual(self.client.post('/api/auth/login', json={'password': 'x' * 17000}).status_code, 413)

    @patch('api.index.supabase_req')
    def test_plaintext_password_rejected(self, db):
        db.return_value = [{**self.guest, 'password': 'plaintext-password'}]
        response = self.client.post('/api/auth/login', json={'email': 'qa@example.com', 'password': 'plaintext-password'})
        self.assertEqual(response.status_code, 401)

    @patch('api.index.supabase_req')
    def test_hashed_password_login_hides_hash(self, db):
        db.return_value = [{**self.guest, 'password': pbkdf2_sha256.hash('valid-password-123')}]
        response = self.client.post('/api/auth/login', json={'email': 'qa@example.com', 'password': 'valid-password-123'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('password', response.json['user'])
        self.assertIn('token', response.json)

    @patch('api.index.supabase_req')
    def test_registration_validation_and_fixed_role(self, db):
        response = self.client.post('/api/auth/register', json={'name': 'QA', 'email': 'qa@example.com', 'password': 'short'})
        self.assertEqual(response.status_code, 400)
        db.assert_not_called()
        db.side_effect = [[], [{**self.guest, 'password': 'hash'}]]
        response = self.client.post('/api/auth/register', json={'name': 'QA', 'email': 'qa@example.com', 'password': 'valid-password-123', 'role': 'staff'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(db.call_args.kwargs['data']['role'], 'guest')

    @patch('api.index.supabase_req', side_effect=RuntimeError('SECRET_DATABASE_CONNECTION_DETAILS'))
    def test_internal_error_is_generic(self, db):
        response = self.client.post('/api/auth/login', json={'email': 'qa@example.com', 'password': 'password'})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('SECRET', response.get_data(as_text=True))

    def test_login_rate_limit(self):
        app.config['SECURITY_RATE_LIMIT_ENABLED'] = True
        for _ in range(12):
            self.assertEqual(self.client.post('/api/auth/login', json={}).status_code, 401)
        response = self.client.post('/api/auth/login', json={})
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response.headers)

    @patch('api.index.supabase_req')
    def test_upload_requires_staff_and_rejects_svg(self, db):
        self.assertEqual(self.client.post('/api/rooms/upload-image', json={'image': 'x'}).status_code, 403)
        db.return_value = [self.guest]
        self.assertEqual(self.client.post('/api/rooms/upload-image', json={'image': 'x'}, headers=self.headers).status_code, 403)
        db.return_value = [{**self.guest, 'role': 'staff'}]
        self.assertEqual(self.client.post('/api/rooms/upload-image', json={'image': 'data:image/svg+xml;base64,' + base64.b64encode(b'<svg/>').decode()}, headers=self.headers).status_code, 400)

    @patch('api.index.supabase_req')
    def test_guests_cannot_manage_inventory(self, db):
        db.return_value = [self.guest]
        for method, path in [('post', '/api/rooms'), ('put', '/api/rooms/1'), ('delete', '/api/rooms/1'), ('post', '/api/services'), ('put', '/api/services/1'), ('delete', '/api/services/1')]:
            response = getattr(self.client, method)(path, json={}, headers=self.headers)
            self.assertEqual(response.status_code, 403, path)

    @patch('api.index.supabase_req')
    def test_guests_cannot_record_money(self, db):
        db.return_value = [self.guest]
        for path in ['/api/bookings/1/payments', '/api/services/avails/1/payments']:
            response = self.client.post(path, json={'amount': 100, 'verified': True}, headers=self.headers)
            self.assertEqual(response.status_code, 403)

    @patch('requests.Session.get')
    @patch('requests.post')
    @patch('api.index.supabase_req')
    def test_other_guests_booking_is_private(self, db, rpc, query):
        db.return_value = [self.guest]
        rpc.return_value = Mock(ok=True, content=b'null', json=lambda: None)
        query.return_value = Mock(text='[]', json=lambda: [{'id': 99, 'user_id': 8}], raise_for_status=lambda: None)
        response = self.client.get('/api/bookings/99', headers=self.headers)
        self.assertEqual(response.status_code, 403)

    @patch('api.index.supabase_req')
    def test_review_ownership_and_public_allowlist(self, db):
        db.side_effect = [[self.guest], []]
        response = self.client.post('/api/reviews', json={'room_id': 1, 'booking_id': 9, 'rating': 5}, headers=self.headers)
        self.assertEqual(response.status_code, 403)
        db.side_effect = None
        db.return_value = [{'id': 1, 'room_id': 1, 'rating': 5, 'user_id': 7, 'booking_id': 9, 'users': {'name': 'QA', 'email': 'private@example.com'}, 'private_note': 'private'}]
        response = self.client.get('/api/reviews?room_id=1')
        self.assertEqual(response.status_code, 200)
        for key in ['user_id', 'booking_id', 'users', 'private_note']:
            self.assertNotIn(key, response.json['reviews'][0])
        self.assertEqual(self.client.get('/api/reviews?room_id=1%26select=users(*)').status_code, 400)

    @patch('api.index.requests.get')
    def test_google_rejects_another_oauth_client(self, get):
        get.return_value = Mock(ok=True, json=lambda: {'aud': 'another-client'})
        self.assertEqual(self.client.post('/api/auth/google', json={'access_token': 'qa-invalid'}).status_code, 401)

    @patch('api.index.supabase_req')
    def test_public_room_fields_are_allowlisted(self, db):
        db.return_value = [{'id': 1, 'name': 'Garden Room', 'private_note': 'internal', 'password': 'secret'}]
        response = self.client.get('/api/rooms')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['rooms'], [{'id': 1, 'name': 'Garden Room', 'amenities': []}])

    @patch('api.index.supabase_req')
    def test_invalid_and_refresh_tokens_cannot_authorize_api(self, db):
        from flask_jwt_extended import create_refresh_token
        with app.app_context():
            refresh = create_refresh_token(identity='7')
        for token in ['forged-token', refresh]:
            response = self.client.get('/api/bookings', headers={'Authorization': 'Bearer ' + token})
            self.assertEqual(response.status_code, 401)
        db.assert_not_called()


if __name__ == '__main__':
    unittest.main()
