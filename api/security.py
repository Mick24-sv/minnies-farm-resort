"""HTTP hardening and bounded, per-worker abuse protection (no database writes)."""
from collections import OrderedDict
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from flask import jsonify, request

SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    # Vue's current CDN runtime compiles templates. Do not pretend this is a strict script CSP.
    'Content-Security-Policy': "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
}


def install_security(app):
    buckets = OrderedDict()
    lock = Lock()
    app.extensions['security_rate_buckets'] = buckets

    @app.before_request
    def guard_api_requests():
        if not request.path.startswith('/api/'):
            return None
        if request.method == 'OPTIONS':
            return None
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = request.headers.get('Origin')
            allowed = app.config['ALLOWED_ORIGINS']
            if origin and origin not in allowed and origin != request.host_url.rstrip('/'):
                return jsonify(error='This origin is not allowed.'), 403
            if request.path.startswith('/api/auth/') and (request.content_length or 0) > 16384:
                return jsonify(error='Request is too large.'), 413
            if request.content_length:
                if not request.is_json:
                    return jsonify(error='Send a JSON object.'), 415
                if not isinstance(request.get_json(silent=True), dict):
                    return jsonify(error='Send a valid JSON object.'), 400
        # Per-process protection only. Production also needs shared/edge rate limits.
        if app.config.get('SECURITY_RATE_LIMIT_ENABLED', True):
            limit = 12 if request.path.startswith('/api/auth/') and request.method == 'POST' else 240
            key = (request.remote_addr or 'unknown', 'auth' if limit == 12 else 'api')
            now = monotonic()
            with lock:
                start, count = buckets.pop(key, (now, 0))
                if now - start >= 60:
                    start, count = now, 0
                buckets[key] = (start, count + 1)
                while len(buckets) > 4096:
                    buckets.popitem(last=False)
            if count >= limit:
                response = jsonify(error='Too many requests. Please try again shortly.')
                response.headers['Retry-After'] = str(max(1, int(60 - (now - start))))
                return response, 429

    @app.after_request
    def protect_response(response):
        response.headers.update(SECURITY_HEADERS)
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, no-store'
            if response.status_code >= 500:
                response.set_data(app.json.dumps({'error': 'The request could not be completed. Please try again.'}))
                response.content_type = 'application/json'
        return response


def allowed_origins(frontend_url, extra=''):
    origins = {'http://localhost:5000', 'http://127.0.0.1:5000'}
    for value in [frontend_url, *extra.split(',')]:
        parsed = urlsplit(value.strip())
        if parsed.scheme in ('http', 'https') and parsed.netloc and not parsed.username and not parsed.password:
            origins.add(f'{parsed.scheme}://{parsed.netloc}')
    return sorted(origins)
