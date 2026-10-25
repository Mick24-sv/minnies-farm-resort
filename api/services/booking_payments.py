"""Authenticated booking and manual-payment workflow. Money changes use SQL RPCs."""
import base64
import re
from decimal import Decimal, InvalidOperation

import requests
from flask import jsonify, request


class BookingError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


ERRORS = {
    'BOOKING_UNAUTHORIZED': ('Please sign in again.', 401),
    'BOOKING_FORBIDDEN': ('You do not have access to this action.', 403),
    'BOOKING_NOT_FOUND': ('The room or reservation could not be found.', 404),
    'BOOKING_ROOM_UNAVAILABLE': ('This room is not available for those dates or guest count.', 409),
    'BOOKING_PAYMENT_CLOSED': ('This reservation is no longer accepting payment submissions.', 409),
    'BOOKING_DEPOSIT_TOO_SMALL': ('Record the full required deposit before confirming this reservation.', 409),
    'BOOKING_BALANCE_DUE': ('Collect the outstanding balance before completing this stay.', 409),
    'BOOKING_DUPLICATE_PAYMENT': ('That transaction reference has already been recorded.', 409),
    'BOOKING_KEY_CONFLICT': ('This request was already used with different details. Reopen the form.', 409),
    'BOOKING_INVALID': ('Check the dates, guest count, amount, and payment details.', 400),
    'BOOKING_TOTAL_CHANGED': ('The room rate changed. Refresh the room details and verify the amount collected.', 409),
    'SERVICE_NOT_FOUND': ('Service request not found.', 404),
    'SERVICE_UNAVAILABLE': ('This service is unavailable or has insufficient stock.', 409),
    'SERVICE_FULL_PAYMENT_REQUIRED': ('Record the full service payment before confirming or completing it.', 409),
}


def payment_config(env):
    accounts = []
    name, number = env('PAYMENT_GCASH_NAME'), env('PAYMENT_GCASH_NUMBER')
    if name and re.fullmatch(r'09\d{9}', number or '') and 'registered account' not in name.lower():
        accounts.append({'method': 'gcash', 'label': 'GCash', 'name': name, 'number': number})
    bank, owner, account = (env('PAYMENT_BANK_NAME'), env('PAYMENT_BANK_ACCOUNT_NAME'), env('PAYMENT_BANK_ACCOUNT_NUMBER'))
    if bank and owner and account and not any('YOUR_' in value for value in (bank, owner, account)):
        accounts.append({'method': 'bank_transfer', 'label': bank, 'name': owner, 'number': account})
    return {'configured': bool(accounts), 'accounts': accounts, 'deposit_percent': 50, 'hold_hours': 3}


def decorate_booking(row, include_proof=False):
    item = dict(row)
    item['reference_code'] = f"MFR-{item['id']}"
    total = Decimal(str(item.get('total_price') or 0))
    paid = Decimal(str(item.get('amount_paid') or 0))
    deposit = Decimal(str(item.get('deposit_required') or 0))
    item['balance_due'] = float(max(total - paid, Decimal(0)))
    item['deposit_due'] = float(max(deposit - paid, Decimal(0)))
    if not include_proof:
        item.pop('payment_proof', None)
    return item


def install_booking_routes(app, query, get_user, env):
    def db(endpoint, **kwargs):
        result = query(endpoint, **kwargs)
        if result is None:
            raise BookingError('Booking data is temporarily unavailable. Please try again.', 503)
        return result

    def rpc(name, payload=None):
        try:
            key = env('SUPABASE_KEY')
            response = requests.post(
                env('SUPABASE_URL').rstrip('/') + '/rest/v1/rpc/' + name,
                headers={'apikey': key, 'Authorization': 'Bearer ' + key},
                json=payload or {}, timeout=20,
            )
        except requests.RequestException:
            raise BookingError('Could not connect. Please retry the same request.', 503)
        if not response.ok:
            try:
                message = response.json().get('message', '')
            except ValueError:
                message = ''
            for code, (text, status) in ERRORS.items():
                if code in message:
                    raise BookingError(text, status)
            raise BookingError('Could not save this change. Please check the payment setup or try again.', 503)
        return response.json() if response.content else None

    def actor(staff=False):
        user = get_user()
        if not user:
            raise BookingError('Please sign in to continue.', 401)
        if staff and user.get('role') != 'staff':
            raise BookingError('Only staff can record or verify payments.', 403)
        return user

    def owned_booking(booking_id, user):
        rows = db(f'bookings?id=eq.{booking_id}&select=*')
        if not rows:
            raise BookingError('Reservation not found.', 404)
        row = rows[0]
        if user.get('role') != 'staff' and str(row.get('user_id')) != str(user['id']):
            raise BookingError('You cannot access this reservation.', 403)
        return row

    def handled(fn):
        from functools import wraps
        @wraps(fn)
        def run(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except BookingError as exc:
                return jsonify({'error': str(exc)}), exc.status
            except (ValueError, TypeError, KeyError, InvalidOperation):
                return jsonify({'error': 'Check the information entered and try again.'}), 400
            except Exception:
                app.logger.exception('Booking operation failed')
                return jsonify({'error': 'Could not complete this request. Please try again.'}), 500
        return run

    @app.get('/api/payment-options')
    def get_payment_options():
        return jsonify(payment_config(env))

    @app.route('/api/bookings', methods=['GET', 'POST'])
    @handled
    def bookings_with_payments():
        user = actor()
        if request.method == 'GET':
            rpc('resort_expire_holds')
            # Keep proof images out of list responses (including large staff lists).
            fields = 'id,user_id,room_id,check_in,check_out,guest_count,total_price,status,created_at,booking_source,walk_in_guest_name,guest_phone,deposit_required,amount_paid,payment_status,payment_due_at,payment_review_status,submitted_payment_method,submitted_payment_reference,payment_submitted_at,payment_review_note'
            endpoint = f'bookings?select={fields}&order=created_at.desc'
            if user.get('role') != 'staff':
                endpoint += f'&user_id=eq.{int(user["id"])}'
            rows = db(endpoint)
            return jsonify({'bookings': [decorate_booking(row) for row in rows]})
        data = request.get_json() or {}
        source = data.get('booking_source', 'online')
        if source == 'walk_in':
            actor(staff=True)
            if data.get('payment_received') is not True:
                raise BookingError('Confirm the full payment was received at the counter.')
        elif source != 'online':
            raise BookingError('Invalid booking source.')
        elif not payment_config(env)['configured']:
            raise BookingError('Online deposit booking is not set up yet. Please contact the resort.', 503)
        result = rpc('resort_create_booking', {
            'p_actor_id': int(user['id']), 'p_room_id': int(data['room_id']),
            'p_check_in': data['check_in_date'], 'p_check_out': data['check_out_date'],
            'p_guests': int(data['num_guests']), 'p_source': source,
            'p_guest_name': str(data.get('guest_name', ''))[:150],
            'p_guest_phone': str(data.get('guest_phone', ''))[:40],
            'p_request_key': data.get('request_key'),
            'p_method': data.get('payment_method'), 'p_reference': str(data.get('payment_reference') or '')[:120],
            'p_expected_total': data.get('expected_total'),
        })
        return jsonify({'booking': decorate_booking(result), 'message': 'Reservation created.'}), 201

    @app.get('/api/bookings/<int:booking_id>')
    @handled
    def booking_payment_details(booking_id):
        user = actor()
        rpc('resort_expire_holds')
        row = owned_booking(booking_id, user)
        payments = db(f'booking_payments?booking_id=eq.{booking_id}&select=id,amount,method,reference,created_at&order=created_at.asc')
        return jsonify({'booking': decorate_booking(row, include_proof=True), 'payments': payments})

    @app.post('/api/bookings/<int:booking_id>/payment-submission')
    @handled
    def submit_deposit_reference(booking_id):
        user = actor()
        owned_booking(booking_id, user)
        data = request.get_json() or {}
        proof = data.get('proof') or None
        if proof:
            if not isinstance(proof, str) or not re.fullmatch(r'data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]+', proof):
                raise BookingError('Use a JPG, PNG or WebP payment screenshot.')
            if len(proof) > 2800000 or len(base64.b64decode(proof.split(',', 1)[1], validate=True)) > 2*1024*1024:
                raise BookingError('The payment screenshot must be at most 2 MB.')
        row = rpc('resort_submit_payment', {'p_actor_id': int(user['id']), 'p_booking_id': booking_id,
                  'p_method': data.get('method'), 'p_reference': str(data.get('reference') or '')[:120], 'p_proof': proof})
        return jsonify({'booking': decorate_booking(row), 'message': 'Payment submitted for staff verification.'})

    @app.post('/api/bookings/<int:booking_id>/payments')
    @handled
    def record_verified_payment(booking_id):
        user = actor(staff=True)
        owned_booking(booking_id, user)
        data = request.get_json() or {}
        if data.get('verified') is not True:
            raise BookingError('Verify that funds were received before recording a payment.')
        amount = Decimal(str(data.get('amount', '')))
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('.01')):
            raise BookingError('Enter a positive amount with at most two decimal places.')
        row = rpc('resort_record_payment', {'p_actor_id': int(user['id']), 'p_booking_id': booking_id,
                  'p_amount': float(amount), 'p_method': data.get('method'),
                  'p_reference': str(data.get('reference') or '')[:120], 'p_request_key': data.get('request_key')})
        return jsonify({'booking': decorate_booking(row), 'message': 'Payment recorded.'})

    @app.post('/api/bookings/<int:booking_id>/payment-rejection')
    @handled
    def reject_deposit(booking_id):
        user = actor(staff=True)
        row = rpc('resort_reject_payment', {'p_actor_id': int(user['id']), 'p_booking_id': booking_id,
                  'p_note': str((request.get_json() or {}).get('note') or '')[:500]})
        return jsonify({'booking': decorate_booking(row)})

    @app.put('/api/bookings/<int:booking_id>/status')
    @handled
    def change_reservation_status(booking_id):
        user = actor(staff=True)
        row = rpc('resort_change_booking', {'p_actor_id': int(user['id']), 'p_booking_id': booking_id,
                  'p_status': (request.get_json() or {}).get('status')})
        return jsonify({'booking': decorate_booking(row)})

    @app.delete('/api/bookings/<int:booking_id>')
    @handled
    def cancel_preserving_payments(booking_id):
        user = actor()
        row = rpc('resort_change_booking', {'p_actor_id': int(user['id']), 'p_booking_id': booking_id,
                  'p_status': 'cancelled'})
        return jsonify({'booking': decorate_booking(row), 'message': 'Reservation cancelled. Payment history retained; contact staff about any refund.'})

    try:
        from .service_payments import install_service_payment_routes
    except ImportError:
        from service_payments import install_service_payment_routes
    install_service_payment_routes(app, db, rpc, actor, handled, env)
    try:
        from .notifications import install_notification_routes
    except ImportError:
        from notifications import install_notification_routes
    install_notification_routes(app, rpc, actor, handled)
    return rpc
