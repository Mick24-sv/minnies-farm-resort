import unittest
from unittest.mock import Mock
from flask import Flask
from api.services.history_visibility import annotate_history, install_history_routes
from api.services.booking_payments import BookingError


class HistoryVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.user={'id':7,'role':'guest'}
        self.rpc=Mock(return_value={'hidden':True})
        app=Flask(__name__)
        @app.errorhandler(BookingError)
        def error(e): return {'error':str(e)},e.status
        install_history_routes(app,self.rpc,lambda:self.user,lambda fn:fn,BookingError)
        self.client=app.test_client()

    def test_actor_comes_from_session_not_body(self):
        for kind in ['booking','service']:
            response=self.client.post(f'/api/history/{kind}/1',json={'hidden':True,'user_id':99})
            self.assertEqual(response.status_code,200)
            self.assertEqual(self.rpc.call_args.args[1],{'p_actor_id':7,'p_kind':kind,'p_entity_id':1,'p_hidden':True})

    def test_reject_invalid_inputs_and_staff(self):
        for payload in [{'hidden':'false'},{'hidden':1},{},[]]:
            self.assertEqual(self.client.post('/api/history/booking/1',json=payload).status_code,400)
        self.user['role']='staff'
        self.assertEqual(self.client.post('/api/history/service/1',json={'hidden':True}).status_code,403)
        self.rpc.assert_not_called()

    def test_guest_annotation_is_scoped_and_staff_records_unchanged(self):
        rows=[{'id':1},{'id':2}];db=Mock(return_value=[{'entity_id':1}])
        annotated=annotate_history(rows,self.user,'booking',db)
        self.assertTrue(annotated[0]['hidden_from_history']);self.assertFalse(annotated[1]['hidden_from_history'])
        self.assertIn('user_id=eq.7&entity_kind=eq.booking',db.call_args.args[0])
        db.reset_mock();self.user['role']='staff'
        self.assertEqual(annotate_history(rows,self.user,'booking',db),rows);db.assert_not_called()
