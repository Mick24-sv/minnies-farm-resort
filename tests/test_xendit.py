import unittest

try:
    from api import index
except Exception:
    index = None


class TestXenditHelpers(unittest.TestCase):
    def test_build_xendit_invoice_payload(self):
        self.assertIsNotNone(index)
        payload = index.build_xendit_invoice_payload(
            external_id='booking-123',
            amount=2500,
            description='Room booking test'
        )
        self.assertEqual(payload['external_id'], 'booking-123')
        self.assertEqual(payload['amount'], 2500)
        self.assertEqual(payload['currency'], 'PHP')
        self.assertIn('description', payload)


if __name__ == '__main__':
    unittest.main()
