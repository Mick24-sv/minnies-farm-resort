"""SendGrid transport and a database-backed outbox; no background threads."""
import hashlib
import secrets
from html import escape
from urllib.parse import urlsplit, urlunsplit, urlencode, quote

import requests
from flask import jsonify, request
from passlib.hash import pbkdf2_sha256


def frontend_url(env):
    value = (env('FRONTEND_URL') or '').strip()
    url = urlsplit(value)
    if not url.hostname or url.username or url.password:
        raise ValueError('Configure FRONTEND_URL with the public website URL.')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('FRONTEND_URL must use HTTPS, or HTTP for localhost.')
    return urlunsplit((url.scheme, url.netloc, url.path or '/', '', ''))


def send_message(env, job):
    """Return accepted/retry/failed/uncertain without logging addresses or secrets."""
    payload = {
        'from': {'email': env('FROM_EMAIL'), 'name': "Minnie's Farm Resort"},
        'personalizations': [{'to': [{'email': job['recipient']}]}],
        'subject': job['subject'],
        'content': [{'type': 'text/plain', 'value': job['body_text']},
                    {'type': 'text/html', 'value': job['body_html']}],
        'tracking_settings': {'click_tracking': {'enable': False, 'enable_text': False},
                              'open_tracking': {'enable': False}},
        'custom_args': {'resort_email_id': str(job['id'])},
    }
    try:
        response = requests.post('https://api.sendgrid.com/v3/mail/send',
                                 headers={'Authorization': 'Bearer ' + env('SENDGRID_API_KEY')},
                                 json=payload, timeout=5)
    except requests.RequestException:
        # A timeout can happen after acceptance. Avoid an automatic duplicate.
        return 'uncertain', 'Network error: delivery acceptance unknown.'
    if response.status_code == 202:
        return 'accepted', ''
    if response.status_code == 429 or response.status_code >= 500:
        return 'retry', 'SendGrid HTTP ' + str(response.status_code)
    return 'failed', 'SendGrid HTTP ' + str(response.status_code)


def render_message(title, message, link):
    return ("<!doctype html><html><body style=\"margin:0;background:#f5f0e8;font-family:Arial,sans-serif;color:#263e30\">"
            "<div style=\"max-width:560px;margin:24px auto;padding:32px;background:white;border-radius:12px\">"
            "<p style=\"color:#91732a\">MINNIE'S FARM RESORT</p><h1 style=\"font-size:24px\">" + escape(title) +
            '</h1><p style="line-height:1.8">' + escape(message) + '</p><p><a style="color:#2d6a5f" href="' +
            escape(link, quote=True) + '">Open the resort website</a></p><p style="font-size:12px;color:#78816f">'
            'This is an automated message. For assistance, contact the resort.</p></div></body></html>')


def install_email_delivery(app, rpc, db, env):
    @app.post('/api/auth/forgot-password')
    def forgot_password_email():
        data = request.get_json(silent=True) or {}
        email = str(data.get('email') or '').strip().lower()
        if not email or len(email) > 254 or '@' not in email:
            return jsonify({'error': 'Enter a valid email address.'}), 400
        # Configuration errors affect every account and can be reported safely.
        try:
            link_base = frontend_url(env)
            if not env('SENDGRID_API_KEY') or not env('FROM_EMAIL'):
                raise ValueError('Email settings are missing.')
        except ValueError:
            app.logger.warning('Password reset email configuration is missing or invalid.')
            return jsonify({'error': 'Password reset email is temporarily unavailable. Please contact the resort.'}), 503
        # Same response for unknown users, cooldowns, or provider failures.
        try:
            rows = db('users?email=eq.' + quote(email, safe='') + '&select=id,email&limit=1')
            if rows:
                token = secrets.token_urlsafe(32)
                link = link_base + '?' + urlencode({'reset_token': token})
                message = 'Use this link to reset your password within one hour. If you did not request this, ignore this email.'
                rpc('resort_request_password_email', {
                    'p_user_id': int(rows[0]['id']), 'p_token_hash': hashlib.sha256(token.encode()).hexdigest(),
                    'p_text': message + '\n\n' + link,
                    'p_html': render_message('Reset your password', message, link),
                })
        except Exception as exc:
            app.logger.warning('Password reset email could not be queued (%s); check the email migration and database connection.', type(exc).__name__)
        return jsonify({'message': 'If that email exists, a reset link has been sent.'})

    @app.post('/api/auth/reset-password')
    def reset_password_email():
        data = request.get_json(silent=True) or {}
        token, password = data.get('token'), data.get('password')
        if not isinstance(token, str) or not 20 <= len(token) <= 200 or not isinstance(password, str) or not 8 <= len(password) <= 256:
            return jsonify({'error': 'Use a valid reset link and a password with 8 to 256 characters.'}), 400
        try:
            changed = rpc('resort_reset_password', {
                'p_token_hash': hashlib.sha256(token.encode()).hexdigest(),
                'p_password_hash': pbkdf2_sha256.hash(password),
            })
            if not changed:
                return jsonify({'error': 'Invalid or expired reset link. Request a new one.'}), 400
            return jsonify({'message': 'Password reset successfully!'}), 200
        except Exception:
            app.logger.warning('Password reset failed; check the email migration.')
            return jsonify({'error': 'Password reset is temporarily unavailable. Please try again.'}), 503

    @app.after_request
    def process_email_queue(response):
        # Requests/polling provide a serverless-compatible worker. Never roll back
        # a successful transaction because its notification could not be emailed.
        relevant = request.path.startswith('/api/') and (request.method == 'POST' or request.path == '/api/notifications')
        if not relevant or response.status_code >= 400 or not env('SENDGRID_API_KEY') or not env('FROM_EMAIL'):
            return response
        try:
            base = frontend_url(env)
            jobs = rpc('resort_claim_email') or []
            for job in jobs:
                if job['kind'] == 'transaction':
                    text = job['body_text']
                    job['body_html'] = render_message(job['subject'], text, base)
                    job['body_text'] = text + '\n\n' + base
                result, error = send_message(env, job)
                rpc('resort_finish_email', {'p_id': job['id'], 'p_lease': job['lease_token'], 'p_result': result, 'p_error': error})
                if result != 'accepted':
                    app.logger.warning('Email job %s: %s (%s)', job['id'], result, error)
        except Exception:
            app.logger.warning('Email queue unavailable; check email settings and the email migration.')
        return response
