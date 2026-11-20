import unittest
from unittest.mock import Mock, patch
from api.index import app


class GoogleAccountModesTest(unittest.TestCase):
    def setUp(self):
        self.client=app.test_client()
        app.config['SECURITY_RATE_LIMIT_ENABLED']=False
        app.extensions['security_rate_buckets'].clear()
        self.identity={'email':'new@example.com','name':'Google Guest','email_verified':True,'sub':'qa-google'}

    def tearDown(self):
        app.config['SECURITY_RATE_LIMIT_ENABLED']=True
        app.extensions['security_rate_buckets'].clear()

    def google_responses(self):
        return [Mock(ok=True,json=lambda:{'aud':'qa-client'}),Mock(ok=True,json=lambda:self.identity)]

    @patch('api.index.get_clean_env',return_value='qa-client')
    @patch('api.index.requests.get')
    @patch('api.index.supabase_req')
    def test_unknown_google_login_never_creates_account(self,db,get,env):
        for extra in [{},{'mode':'login'}]:
            get.side_effect=self.google_responses();db.return_value=[];db.reset_mock()
            response=self.client.post('/api/auth/google',json={'access_token':'qa',**extra})
            self.assertEqual(response.status_code,404)
            self.assertEqual(response.json['code'],'GOOGLE_REGISTRATION_REQUIRED')
            self.assertNotIn('token',response.json);self.assertEqual(db.call_count,1)

    @patch('api.index.get_clean_env',return_value='qa-client')
    @patch('api.index.requests.get')
    @patch('api.index.supabase_req')
    def test_register_creates_guest_from_verified_identity(self,db,get,env):
        get.side_effect=self.google_responses()
        db.side_effect=[[],[{'id':7,'name':'Google Guest','email':'new@example.com','role':'guest','is_verified':True}]]
        response=self.client.post('/api/auth/google',json={'access_token':'qa','mode':'register','role':'staff','email':'spoof@example.com'})
        self.assertEqual(response.status_code,200);self.assertIn('token',response.json)
        created=db.call_args.kwargs['data'];self.assertEqual(created['role'],'guest');self.assertEqual(created['email'],'new@example.com')
        self.assertTrue(created['is_verified']);self.assertNotIn('password',response.json['user'])

    @patch('api.index.get_clean_env',return_value='qa-client')
    @patch('api.index.requests.get')
    @patch('api.index.supabase_req')
    def test_existing_account_uses_login_not_registration(self,db,get,env):
        db.return_value=[{'id':7,'name':'Google Guest','email':'new@example.com','role':'guest','is_verified':True}]
        get.side_effect=self.google_responses()
        response=self.client.post('/api/auth/google',json={'access_token':'qa','mode':'register'})
        self.assertEqual(response.status_code,409);self.assertEqual(response.json['code'],'GOOGLE_ACCOUNT_EXISTS')
        self.assertNotIn('token',response.json);self.assertEqual(db.call_count,1)
        get.side_effect=self.google_responses()
        self.assertEqual(self.client.post('/api/auth/google',json={'access_token':'qa','mode':'login'}).status_code,200)

    @patch('api.index.supabase_req')
    def test_invalid_mode_never_accesses_database(self,db):
        self.assertEqual(self.client.post('/api/auth/google',json={'access_token':'qa','mode':'staff'}).status_code,400)
        db.assert_not_called()
