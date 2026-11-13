from datetime import datetime, timezone
from unittest.mock import patch
import unittest

from api.index import app, create_access_token
from api.services.revenue import revenue_summary


class RevenueTest(unittest.TestCase):
    def test_receipts_use_manila_month_and_centavos(self):
        calls = []
        def query(endpoint):
            calls.append(endpoint)
            if 'offset=0' not in endpoint:
                return []
            if endpoint.startswith('booking_payments?'):
                return [{'id': 1, 'amount': '100.10', 'created_at': '2026-10-31T16:30:00Z'},
                        {'id': 2, 'amount': '0.20', 'created_at': '2026-11-01T00:00:00Z'}]
            return [{'id': 1, 'amount': '50.05', 'created_at': '2026-10-31T15:59:59Z'}]
        result = revenue_summary(query, datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertEqual(len(result['months']), 12)
        self.assertEqual(result['months'][-1]['room_payments'], 100.30)
        self.assertEqual(result['months'][-2]['service_payments'], 50.05)
        self.assertEqual(result['months'][-1]['total'], 100.30)
        self.assertTrue(all('select=id,amount,created_at' in call for call in calls))
        self.assertTrue(any('offset=2' in call for call in calls))

    def test_zero_receipts_and_year_boundary(self):
        result = revenue_summary(lambda endpoint: [], datetime(2026, 1, 5, tzinfo=timezone.utc))
        self.assertEqual(result['months'][0]['month'], '2025-02')
        self.assertEqual(result['months'][-1]['month'], '2026-01')
        self.assertEqual(sum(row['total'] for row in result['months']), 0)

    def test_database_failure_is_not_zero_revenue(self):
        with self.assertRaises(RuntimeError):
            revenue_summary(lambda endpoint: None)

    def test_invalid_receipt_does_not_become_fake_total(self):
        with self.assertRaises(RuntimeError):
            revenue_summary(lambda endpoint: [{'id':1,'amount':'NaN','created_at':'2026-11-01T00:00:00Z'}])

    def test_future_and_out_of_window_receipts_excluded(self):
        def query(endpoint):
            if 'offset=0' not in endpoint:
                return []
            return [{'id':1,'amount':'100','created_at':'2027-01-01T00:00:00Z'},
                    {'id':2,'amount':'100','created_at':'2024-01-01T00:00:00Z'}]
        result = revenue_summary(query, datetime(2026,11,14,tzinfo=timezone.utc))
        self.assertEqual(sum(row['total'] for row in result['months']),0)

    @patch('api.index.supabase_req')
    @patch('api.index.revenue_summary')
    def test_endpoint_staff_only_and_aggregate_response(self, report, db):
        client=app.test_client()
        self.assertEqual(client.get('/api/staff/revenue').status_code,401)
        with app.app_context():
            token=create_access_token(identity='7')
        headers={'Authorization':'Bearer '+token}
        db.return_value=[{'id':7,'role':'guest'}]
        self.assertEqual(client.get('/api/staff/revenue',headers=headers).status_code,403)
        report.assert_not_called()
        db.return_value=[{'id':7,'role':'staff'}]
        report.return_value={'currency':'PHP','months':[]}
        self.assertEqual(client.get('/api/staff/revenue',headers=headers).status_code,200)
        report.side_effect=RuntimeError('private database details')
        response=client.get('/api/staff/revenue',headers=headers)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private database',response.get_data(as_text=True))


if __name__=='__main__':
    unittest.main()
