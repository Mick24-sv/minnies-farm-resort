import unittest
from unittest.mock import Mock, patch
from flask import Flask
from api.services.booking_payments import install_booking_routes


class ReceiptDetailsTest(unittest.TestCase):
    def setUp(self):
        self.user = {'id': 7, 'role': 'guest'}
        self.queries = []
        def query(endpoint, **kwargs):
            self.queries.append(endpoint)
            if endpoint.startswith('bookings?'):
                return [{'id': 1, 'user_id': 7, 'room_id': 2, 'total_price': 2200, 'amount_paid': 1100}]
            if endpoint.startswith('users?'): return [{'name': 'Ana Reyes'}]
            if endpoint.startswith('rooms?'): return [{'name': 'Garden Room'}]
            if endpoint.startswith('booking_payments?'):
                return [{'id': 3, 'amount': 1100, 'method': 'cash', 'created_at': '2026-11-14T01:00:00Z'}]
            return []
        app = Flask(__name__)
        install_booking_routes(app, query, lambda: self.user, lambda key: '')
        self.client = app.test_client()

    @patch('api.services.booking_payments.requests.post')
    def test_owner_receives_real_customer_room_and_verified_payment(self, rpc):
        rpc.return_value = Mock(ok=True,content=b'{}',json=lambda:{})
        response = self.client.get('/api/bookings/1')
        self.assertEqual(response.status_code,200)
        data=response.get_json()
        self.assertEqual(data['booking']['guest_name'],'Ana Reyes')
        self.assertEqual(data['booking']['room_name'],'Garden Room')
        self.assertEqual(data['payments'][0]['amount'],1100)

    @patch('api.services.booking_payments.requests.post')
    def test_other_guest_cannot_access_receipt_identity_or_payments(self, rpc):
        rpc.return_value = Mock(ok=True,content=b'{}',json=lambda:{})
        self.user={'id':8,'role':'guest'}
        self.assertEqual(self.client.get('/api/bookings/1').status_code,403)
        self.assertFalse(any(q.startswith(('users?','booking_payments?')) for q in self.queries))

    def test_signed_out_cannot_access_receipt(self):
        self.user=None
        self.assertEqual(self.client.get('/api/bookings/1').status_code,401)
        self.assertEqual(self.queries,[])
