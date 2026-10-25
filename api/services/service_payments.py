"""Full-payment service requests and counter sales; shares authenticated RPC transport."""
import base64
import re
from decimal import Decimal

from flask import jsonify, request
try:
    from .booking_payments import BookingError, decorate_booking
except ImportError:
    from booking_payments import BookingError, decorate_booking


def service_receipt(row, include_proof=False):
    item = decorate_booking(row, include_proof)
    item['reference_code'] = f"MFS-{row['id']}"
    item['created_at'] = row.get('availed_at')
    service, user = row.get('services') or {}, row.get('users') or {}
    item['service_name'] = service.get('name') or row.get('service_name', 'Service')
    item['guest_name'] = row.get('guest_name') or user.get('name', '')
    item['guest_email'] = user.get('email', '')
    return item


def install_service_payment_routes(app, db, rpc, actor, handled, env):
    def owned(avail_id, user):
        rows = db(f'service_avails?id=eq.{avail_id}&select=*,services(name,price),users(name,email)')
        if not rows:
            raise BookingError('Service request not found.', 404)
        row = rows[0]
        if user.get('role') != 'staff' and str(row.get('user_id')) != str(user['id']):
            raise BookingError('You cannot access this service request.', 403)
        return row

    @app.before_request
    @handled
    def refresh_service_inventory_holds():
        if request.path == '/api/services' and request.method == 'GET':
            rpc('resort_expire_service_holds')

    def create_request(service_id, source):
        user = actor(staff=source == 'walk_in')
        data = request.get_json() or {}
        if source == 'walk_in' and data.get('payment_received') is not True:
            raise BookingError('Verify that the full payment was received at the counter.')
        row = rpc('resort_create_service_request', {'p_actor_id': int(user['id']), 'p_service_id': int(service_id),
                  'p_quantity': int(data.get('quantity', 1)), 'p_source': source,
                  'p_guest_name': str(data.get('guest_name') or '')[:150], 'p_guest_phone': str(data.get('guest_phone') or '')[:40],
                  'p_request_key': data.get('request_key'), 'p_method': data.get('payment_method'),
                  'p_reference': str(data.get('payment_reference') or '')[:120], 'p_expected_total': data.get('expected_total')})
        return jsonify({'avail': service_receipt(owned(row['id'], user))}), 201

    @app.post('/api/services/<int:service_id>/avail')
    @handled
    def create_online_service_request(service_id):
        return create_request(service_id, 'online')

    @app.post('/api/services/avails/walk-in')
    @handled
    def create_counter_service_request():
        return create_request((request.get_json() or {})['service_id'], 'walk_in')

    @app.get('/api/services/avails')
    @handled
    def list_service_payment_requests():
        user = actor()
        rpc('resort_expire_service_holds')
        fields = 'id,user_id,service_id,quantity,total_price,availed_at,status,request_source,guest_name,guest_phone,deposit_required,amount_paid,payment_status,payment_due_at,payment_review_status,submitted_payment_method,submitted_payment_reference,payment_submitted_at,payment_review_note,requested_payment_method,services(name,price),users(name,email)'
        endpoint = f'service_avails?select={fields}&order=availed_at.desc'
        if user.get('role') != 'staff':
            endpoint += f'&user_id=eq.{int(user["id"])}'
        return jsonify({'avails': [service_receipt(row) for row in db(endpoint)]})

    @app.route('/api/services/avails/<int:avail_id>', methods=['GET','PATCH','DELETE'])
    @handled
    def service_payment_details(avail_id):
        user = actor(staff=request.method == 'PATCH')
        rpc('resort_expire_service_holds')
        row = owned(avail_id, user)
        if request.method != 'GET':
            status = 'cancelled' if request.method == 'DELETE' else (request.get_json() or {}).get('status')
            result = rpc('resort_change_service_request', {'p_actor_id': int(user['id']), 'p_avail_id': avail_id, 'p_status': status})
            return jsonify({'avail': service_receipt(result), 'message': 'Request updated. Payment records retained.'})
        history = db(f'service_payments?avail_id=eq.{avail_id}&select=id,amount,method,reference,created_at&order=created_at.asc')
        return jsonify({'avail': service_receipt(row, True), 'payments': history})

    @app.post('/api/services/avails/<int:avail_id>/payment-submission')
    @handled
    def submit_service_payment(avail_id):
        user = actor()
        owned(avail_id, user)
        data = request.get_json() or {}
        proof = data.get('proof') or None
        if proof and (not isinstance(proof, str) or len(proof)>2800000
            or not re.fullmatch(r'data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]+', proof)
            or len(base64.b64decode(proof.split(',',1)[1], validate=True))>2*1024*1024):
            raise BookingError('Use a JPG, PNG or WebP screenshot up to 2 MB.')
        row = rpc('resort_submit_service_payment', {'p_actor_id': int(user['id']), 'p_avail_id': avail_id,
                  'p_method': data.get('method'), 'p_reference': str(data.get('reference') or '')[:120], 'p_proof': proof})
        return jsonify({'avail': service_receipt(row)})

    @app.post('/api/services/avails/<int:avail_id>/pay-at-counter')
    @handled
    def choose_service_counter_payment(avail_id):
        user = actor()
        owned(avail_id, user)
        row = rpc('resort_choose_service_counter', {'p_actor_id': int(user['id']), 'p_avail_id': avail_id})
        return jsonify({'avail': service_receipt(row), 'message': 'Pay at the counter selected. Payment has not been received.'})

    @app.post('/api/services/avails/<int:avail_id>/payments')
    @handled
    def record_service_payment(avail_id):
        user = actor(staff=True)
        owned(avail_id, user)
        data = request.get_json() or {}
        if data.get('verified') is not True:
            raise BookingError('Verify that funds were received before recording a payment.')
        amount = Decimal(str(data.get('amount','')))
        if not amount.is_finite() or amount<=0 or amount!=amount.quantize(Decimal('.01')):
            raise BookingError('Enter a positive amount with at most two decimal places.')
        row = rpc('resort_record_service_payment', {'p_actor_id': int(user['id']), 'p_avail_id': avail_id,
                  'p_amount': float(amount), 'p_method': data.get('method'), 'p_reference': str(data.get('reference') or '')[:120], 'p_request_key': data.get('request_key')})
        return jsonify({'avail': service_receipt(row)})

    @app.post('/api/services/avails/<int:avail_id>/payment-rejection')
    @handled
    def reject_service_payment(avail_id):
        user = actor(staff=True)
        row = rpc('resort_reject_service_payment', {'p_actor_id': int(user['id']), 'p_avail_id': avail_id, 'p_note': str((request.get_json() or {}).get('note') or '')[:500]})
        return jsonify({'avail': service_receipt(row)})
