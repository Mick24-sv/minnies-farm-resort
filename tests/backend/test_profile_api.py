"""Profile API checks. Database access is mocked; no account records are changed."""
import unittest
from unittest.mock import patch

from api.index import app, create_access_token


class ProfileAPITest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            token = create_access_token(identity='7')
        self.headers = {'Authorization': f'Bearer {token}'}

    def test_requires_authentication(self):
        response = self.client.patch('/api/auth/profile', json={'name': 'Ana Reyes'})
        self.assertEqual(response.status_code, 401)

    @patch('api.index.supabase_req')
    def test_rejects_invalid_or_privileged_fields(self, database):
        for payload in [{}, [], {'name': ''}, {'name': ' '}, {'name': 5},
                        {'name': 'x' * 101}, {'name': 'Ana', 'id': 99},
                        {'name': 'Ana', 'role': 'staff'}, {'name': 'Ana', 'email': 'other@example.com'}]:
            with self.subTest(payload=payload):
                response = self.client.patch('/api/auth/profile', json=payload, headers=self.headers)
                self.assertEqual(response.status_code, 400)
        database.assert_not_called()

    @patch('api.index.supabase_req')
    def test_saves_only_signed_in_user_and_filters_response(self, database):
        database.return_value = [{'id': 7, 'name': 'Ana Reyes', 'email': 'qa@example.com',
                                  'role': 'guest', 'password': 'must-not-leave-server'}]
        response = self.client.patch('/api/auth/profile', json={'name': '  Ana Reyes  '}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        database.assert_called_once_with('users?id=eq.7', method='PATCH', data={'name': 'Ana Reyes'})
        self.assertNotIn('password', response.json['user'])

    @patch('api.index.supabase_req', return_value=None)
    def test_database_failure_returns_error(self, database):
        response = self.client.patch('/api/auth/profile', json={'name': 'Ana'}, headers=self.headers)
        self.assertEqual(response.status_code, 503)


if __name__ == '__main__':
    unittest.main()
