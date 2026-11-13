from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import unittest
from flask import Flask

from api.services.booking_times import validate_booking_times, PHT
from api.services.booking_payments import install_booking_routes


class BookingTimesTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
        self.data = {'check_in_date': '2026-11-15', 'check_out_date': '2026-11-16',
                     'check_in_time': '14:30', 'check_out_time': '09:15'}
        self.env = {'BOOKING_TIMES_ENABLED': '1'}
        self.actor = {'id': 7, 'role': 'guest'}
        self.queries = []
        def query(endpoint, **kwargs):
            self.queries.append(endpoint)
            return []
        self.app = Flask(__name__)
        install_booking_routes(self.app, query, lambda: self.actor, lambda key: self.env.get(key, ''))
        self.client = self.app.test_client()
        start = datetime.now(PHT).date() + timedelta(days=7)
        self.payload = {**self.data, 'room_id': 1, 'num_guests': 2, 'request_key': 'qa-times',
                        'check_in_date': start.isoformat(), 'check_out_date': (start + timedelta(days=1)).isoformat()}

    def test_minute_precision_and_philippine_time(self):
        self.assertEqual(validate_booking_times(self.data, now=self.now), ('14:30', '09:15'))

    def test_invalid_and_missing_clock_values_rejected(self):
        for value in ['', None, '24:00', '12:60', '2:30 PM', '14:30:01', 930]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_booking_times({**self.data, 'check_in_time': value}, now=self.now)

    def test_same_day_and_past_online_arrival_rejected(self):
        with self.assertRaises(ValueError):
            validate_booking_times({**self.data, 'check_out_date': '2026-11-15'}, now=self.now)
        past = {**self.data, 'check_in_date': '2026-11-14', 'check_in_time': '07:00'}
        with self.assertRaises(ValueError):
            validate_booking_times(past, now=self.now)
        self.assertEqual(validate_booking_times(past, source='walk_in', now=self.now)[0], '07:00')

    @patch('api.services.booking_payments.requests.post')
    def test_new_times_are_sent_to_atomic_wrapper(self, rpc):
        rpc.return_value = Mock(ok=True, content=b'{}', json=lambda: {'id':1,'total_price':2000,'check_in_time':'14:30:00','check_out_time':'09:15:00'})
        response = self.client.post('/api/bookings', json=self.payload)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(rpc.call_args.args[0].endswith('/resort_create_booking_with_times'))
        values = rpc.call_args.kwargs['json']['p_payload']
        self.assertEqual(values['p_check_in_time'], '14:30')
        self.assertEqual(values['p_check_out_time'], '09:15')
        self.assertEqual(values['p_actor_id'], 7)
        self.assertEqual(response.json['booking']['check_in_time'], '14:30:00')

    @patch('api.services.booking_payments.requests.post')
    def test_missing_times_do_not_create_booking_when_enabled(self, rpc):
        self.assertEqual(self.client.post('/api/bookings', json={**self.payload,'check_in_time':''}).status_code, 400)
        rpc.assert_not_called()

    @patch('api.services.booking_payments.requests.post')
    def test_disabled_feature_never_silently_drops_selected_times(self, rpc):
        self.env['BOOKING_TIMES_ENABLED'] = '0'
        self.assertEqual(self.client.post('/api/bookings', json=self.payload).status_code, 503)
        rpc.assert_not_called()

    @patch('api.services.booking_payments.requests.post')
    def test_legacy_date_only_flow_kept_until_activation(self, rpc):
        self.env['BOOKING_TIMES_ENABLED'] = '0'
        payload = {key:value for key,value in self.payload.items() if key not in ('check_in_time','check_out_time')}
        rpc.return_value = Mock(ok=True, content=b'{}', json=lambda: {'id':1,'total_price':2000})
        self.assertEqual(self.client.post('/api/bookings', json=payload).status_code, 201)
        self.assertTrue(rpc.call_args.args[0].endswith('/resort_create_booking'))

    @patch('api.services.booking_payments.requests.post')
    def test_times_are_in_list_projection_only_after_activation(self, rpc):
        rpc.return_value=Mock(ok=True,content=b'null',json=lambda:None)
        self.client.get('/api/bookings')
        self.assertIn('check_in_time,check_out_time',self.queries[-1])
        self.env['BOOKING_TIMES_ENABLED']='0'
        self.client.get('/api/bookings')
        self.assertNotIn('check_in_time',self.queries[-1])

    def test_customer_cannot_create_staff_walkin(self):
        response=self.client.post('/api/bookings',json={**self.payload,'booking_source':'walk_in','payment_received':True})
        self.assertEqual(response.status_code,403)


if __name__=='__main__':
    unittest.main()
