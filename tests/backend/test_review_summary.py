import unittest
from unittest.mock import Mock, patch
from api.services.reviews import rating_summary
from api.index import app


class ReviewSummaryTest(unittest.TestCase):
    @patch('api.services.reviews.requests.head')
    def test_weighted_average_and_exact_room_counts(self, head):
        counts = {5: 2, 4: 2, 3: 1, 2: 0, 1: 0}
        def response(url, *, params, headers, timeout):
            self.assertEqual(params['room_id'], 'eq.17')
            self.assertEqual(headers['Prefer'], 'count=exact')
            return Mock(ok=True, headers={'Content-Range': '*/' + str(counts[int(params['rating'][3:])])})
        head.side_effect = response
        result = rating_summary('https://example.invalid', 'dummy', 17)
        self.assertEqual(result['total_reviews'], 5)
        self.assertEqual(result['average_rating'], 4.2)
        self.assertEqual(result['rating_breakdown']['5'], 2)
        self.assertEqual(head.call_count, 5)

    @patch('api.services.reviews.requests.head', return_value=Mock(ok=True, headers={'Content-Range': '*/0'}))
    def test_no_reviews_is_zero_not_sample_rating(self, head):
        result = rating_summary('https://example.invalid', 'dummy', 2)
        self.assertEqual(result['total_reviews'], 0)
        self.assertEqual(result['average_rating'], 0)
        self.assertEqual(sum(result['rating_breakdown'].values()), 0)

    @patch('api.services.reviews.requests.head', return_value=Mock(ok=False))
    def test_failed_count_request_is_not_empty_data(self, head):
        with self.assertRaises(RuntimeError):
            rating_summary('https://example.invalid', 'dummy', 2)

    @patch('api.index.rating_summary')
    @patch('api.index.supabase_req')
    def test_api_summary_includes_more_than_display_page(self, db, summary):
        db.return_value = [{'id': 1, 'room_id': 17, 'rating': 5, 'comment': 'A review'}]
        summary.return_value = {'average_rating': 4.2, 'total_reviews': 1200, 'rating_breakdown': {'5': 600, '4': 240, '3': 360, '2': 0, '1': 0}}
        response = app.test_client().get('/api/reviews?room_id=17')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['total_reviews'], 1200)
        self.assertEqual(len(response.json['reviews']), 1)
        summary.assert_called_once()

    @patch('api.index.supabase_req', return_value=None)
    def test_failed_review_list_returns_503(self, db):
        self.assertEqual(app.test_client().get('/api/reviews?room_id=17').status_code, 503)


if __name__ == '__main__':
    unittest.main()
