import os
import sys
import json
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from passlib.hash import pbkdf2_sha256
import secrets
import time
import re
import base64
from datetime import timedelta
from urllib.parse import quote

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- CONFIG ---
app = Flask(__name__)
# Increase max content length to 10MB to handle image uploads better on Vercel
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
try:
    from .security import install_security, allowed_origins
except ImportError:
    from security import install_security, allowed_origins
app.config['ALLOWED_ORIGINS'] = allowed_origins(os.getenv('FRONTEND_URL', ''), os.getenv('ALLOWED_ORIGINS', ''))
CORS(app, resources={r'/api/*': {'origins': app.config['ALLOWED_ORIGINS']}},
     allow_headers=['Authorization', 'Content-Type', 'Cache-Control', 'Pragma'],
     methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
install_security(app)
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=15)
app.config['JWT_TOKEN_LOCATION'] = ['headers']

class VercelPathMiddleware:
    """WSGI middleware to restore original request path from Vercel rewrite parameter"""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        query_string = environ.get('QUERY_STRING', '')
        if '__path=' in query_string:
            import urllib.parse
            params = urllib.parse.parse_qs(query_string)
            if '__path' in params and params['__path'][0]:
                orig_path = params['__path'][0]
                if not orig_path.startswith('/'):
                    orig_path = '/' + orig_path
                environ['PATH_INFO'] = orig_path
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PUBLIC_DIR = os.path.join(ROOT_DIR, 'public')

DEBUG = os.getenv('DEBUG', '').strip() == '1'

def get_clean_env(key):
    val = os.environ.get(key) or os.getenv(key) or ""
    # Remove all whitespace, newlines, and quotes that might have been pasted by accident
    return val.strip().replace("\n", "").replace("\r", "").replace(" ", "").replace("'", "").replace('"', "")

_jwt_secret = get_clean_env("JWT_SECRET_KEY")
if not _jwt_secret:
    raise RuntimeError('JWT_SECRET_KEY must be configured before starting the application.')
app.config["JWT_SECRET_KEY"] = _jwt_secret
jwt = JWTManager(app)

SUPABASE_URL = get_clean_env('SUPABASE_URL')
SUPABASE_KEY = get_clean_env('SUPABASE_KEY')



def public_user(user):
    """Only account fields intended for display can leave authentication routes."""
    return {key: user[key] for key in ('id', 'name', 'email', 'role', 'is_verified') if key in user}


PUBLIC_ROOM_FIELDS = {'id', 'name', 'room_number', 'type', 'price_per_night', 'capacity', 'sqm', 'description', 'amenities', 'image_url', 'image_url_2', 'image_url_3', 'image_url_4', 'image_url_5', 'is_available', 'room_status', 'emoji', 'created_at'}
PUBLIC_SERVICE_FIELDS = {'id', 'name', 'category', 'price', 'stock_quantity', 'description', 'is_active', 'image_url', 'emoji', 'created_at'}


def public_record(row, fields):
    return {key: value for key, value in row.items() if key in fields}


# --- HELPERS ---
def supabase_req(endpoint, method='GET', data=None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase request aborted: SUPABASE_URL or SUPABASE_KEY is missing from environment.")
        return None
    # Re-clean and validate URL every time
    url_base = SUPABASE_URL.strip().replace(" ", "").replace("'", "").replace('"', "")
    if not url_base.startswith("http"):
        url_base = f"https://{url_base}"
    url_base = url_base.rstrip('/')
    
    try:
        url = f"{url_base}/rest/v1/{endpoint}"
        
        headers = {
            'apikey': SUPABASE_KEY.strip(),
            'Authorization': f'Bearer {SUPABASE_KEY.strip()}',
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache'
        }
        
        # Only add return=representation for write operations
        if method in ['POST', 'PATCH']:
            headers['Prefer'] = 'return=representation'
        
        # Use a session with retries for better stability
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=5)
        session.mount('https://', adapter)
        
        if DEBUG:
            print(f"Supabase API Call: {method} {endpoint.split('?')[0]}")
        
        if method == 'GET':
            res = session.get(url, headers=headers, timeout=15)
        elif method == 'POST':
            res = session.post(url, headers=headers, json=data, timeout=15)
        elif method == 'PATCH':
            res = session.patch(url, headers=headers, json=data, timeout=15)
        elif method == 'DELETE':
            res = session.delete(url, headers=headers, timeout=15)
        else:
            return None

        if DEBUG:
            print(f"Supabase Status: {res.status_code}")

        res.raise_for_status()
        return res.json() if res.text else []

    except Exception as e:
        if DEBUG:
            print(f"Supabase request error: {method} {type(e).__name__}")
        # If DNS fails, try to log the IP for debugging
        try:
            host = url_base.split("//")[-1].split("/")[0]
            if DEBUG:
                print(f"DNS Debug: Final attempt to resolve '{host}'...")
            import socket
            ip = socket.gethostbyname(host)
            if DEBUG:
                print(f"DNS Debug: Success! IP is {ip}")
        except:
            if DEBUG:
                print("DNS Debug: ALL resolution methods failed.")

        return None


def _get_user_from_request():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    received_token = auth_header.split(' ')[1]
    user_id = None
    try:
        from flask_jwt_extended import verify_jwt_in_request
        verify_jwt_in_request()
        user_id = get_jwt_identity()
    except Exception:
        return None

    if user_id is None:
        return None

    try:
        user_id_int = int(user_id)
    except Exception:
        return None

    if user_id_int <= 0:
        return None
    users = supabase_req(f'users?id=eq.{user_id_int}&select=id,name,email,role,is_verified')
    if not users:
        return None
    return users[0]

# --- ROUTES ---
def internal_error(error):
    app.logger.warning("Request failed (%s)", type(error).__name__)
    return jsonify(error="The request could not be completed. Please try again."), 500

@app.after_request
def add_header(response):
    # FORCE NO CACHE - ensures staff updates reflect immediately
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/api/health')
def health():
    return jsonify({'status': 'online'})

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email_value = data.get('email')
        email = email_value.strip().lower() if isinstance(email_value, str) else ''
        password = data.get('password')

        if not email or len(email) > 254 or not isinstance(password, str) or not 1 <= len(password) <= 256:
            return jsonify({"error": "Invalid email or password."}), 401

        users = supabase_req(f'users?email=eq.{quote(email, safe="")}&select=*')
        
        if not users:
            return jsonify({"error": "Invalid email or password."}), 401
        
        user = users[0]
        stored_pw = user.get('password')
        
        # Never authenticate a plaintext or malformed stored password.
        is_valid = False
        try:
            is_valid = pbkdf2_sha256.verify(password, stored_pw)
        except:
            is_valid = False
            
        if not is_valid:
            return jsonify({"error": "Invalid email or password."}), 401

        token = create_access_token(identity=str(user.get('id')))
        return jsonify({"token": token, "user": public_user(user)}), 200
    except Exception as e:
        return internal_error(e)


@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json() or {}
        name = data.get('name', '')
        email = data.get('email', '')
        if not isinstance(name, str) or not isinstance(email, str):
            return jsonify(error='Enter a valid name and email.'), 400
        name, email = name.strip(), email.strip().lower()
        password = data.get('password')

        if not 1 <= len(name) <= 100 or not re.fullmatch(r'[^\s@&?#]+@[^\s@&?#]+\.[^\s@&?#]+', email) or len(email) > 254 or not isinstance(password, str) or not 12 <= len(password) <= 256:
            return jsonify(error='Enter a valid name, email, and a password with 12 to 256 characters.'), 400

        # check existing
        existing = supabase_req(f'users?email=eq.{quote(email, safe="")}&select=id&limit=1')
        if existing is None:
            return jsonify(error='Registration is temporarily unavailable.'), 503
        if existing:
            return jsonify({"error": "Email is already registered."}), 409

        hashed_pw = pbkdf2_sha256.using(rounds=600000).hash(password)
        user_data = {
            'name': name,
            'email': email,
            'password': hashed_pw,
            'role': 'guest',
            'is_verified': True
        }

        created = supabase_req('users', method='POST', data=user_data)
        if not isinstance(created, list) or not created:
            return jsonify(error='Could not create your account. Please try again.'), 503
        user = created[0]
        user.pop('password', None)

        return jsonify({"message": "Account created! You can now sign in.", "user": public_user(user)}), 201
    except Exception as e:
        return internal_error(e)


@app.route('/api/auth/google', methods=['POST'])
def google_login():
    try:
        data = request.get_json(silent=True) or {}
        access_token = data.get('access_token')
        if not isinstance(access_token, str) or not access_token or len(access_token) > 4096:
            return jsonify({'error': 'A valid Google sign-in token is required.'}), 401
        expected_client = get_clean_env('GOOGLE_CLIENT_ID') or '549203417668-bl1k05ionrenlhnukkui7b6hka24rbbe.apps.googleusercontent.com'
        # Identity must come from Google, never from email/name sent by the browser.
        try:
            token_info = requests.get('https://oauth2.googleapis.com/tokeninfo', params={'access_token': access_token}, timeout=8)
            if not token_info.ok or token_info.json().get('aud') != expected_client:
                return jsonify(error='Google sign-in could not be verified.'), 401
            response = requests.get('https://www.googleapis.com/oauth2/v3/userinfo',
                                    headers={'Authorization': 'Bearer ' + access_token}, timeout=8)
            if not response.ok:
                return jsonify({'error': 'Google sign-in could not be verified.'}), 401
            identity = response.json()
        except (requests.RequestException, ValueError):
            return jsonify({'error': 'Google sign-in is temporarily unavailable.'}), 503
        if identity.get('email_verified') is not True or not identity.get('email') or not identity.get('sub'):
            return jsonify({'error': 'A verified Google email is required.'}), 401
        email = str(identity['email']).strip().lower()
        name = identity.get('name') or email.split('@')[0]

        users = supabase_req(f'users?email=eq.{quote(email, safe="")}&select=id,name,email,role,is_verified')
        if users is None:
            return jsonify(error='Google sign-in is temporarily unavailable.'), 503
        user = users[0] if users else None

        if not user:
            user_data = {
                'name': name,
                'email': email,
                'password': pbkdf2_sha256.using(rounds=600000).hash(secrets.token_urlsafe(32)),
                'role': 'guest',
                'is_verified': True
            }
            user = supabase_req('users', method='POST', data=user_data)
            if isinstance(user, list): user = user[0]

        token = create_access_token(identity=str(user.get('id')))
        return jsonify({'token': token, 'user': public_user(user)}), 200
    except Exception as e:
        return internal_error(e)

@app.route('/api/rooms', methods=['GET', 'POST'])
def handle_rooms():
    try:
        if request.method == 'POST':
            user = _get_user_from_request()
            if not user or user.get('role') != 'staff':
                return jsonify({"error": "Staff access required."}), 403
        if request.method == 'POST':
            data = request.get_json()
            room_fields = {'room_number', 'name', 'type', 'price_per_night', 'capacity', 'sqm', 'description', 'amenities', 'image_url', 'image_url_2', 'image_url_3', 'image_url_4', 'image_url_5', 'room_status', 'is_available'}
            data = {key: value for key, value in data.items() if key in room_fields}
            # Handle amenities if it's a list
            if 'amenities' in data and isinstance(data['amenities'], list):
                data['amenities'] = ", ".join(data['amenities'])
            result = supabase_req('rooms', method='POST', data=data)
            return jsonify({"message": "Room created successfully", "room": result}), 201
            
        # GET logic
        rooms = supabase_req('rooms?select=*')
        if rooms and isinstance(rooms, list):
            for room in rooms:
                # FORCE AMENITIES TO BE A CLEAN LIST OF WORDS
                raw = room.get('amenities', '')
                if not raw:
                    room['amenities'] = []
                elif isinstance(raw, str):
                    # Handle comma separated strings or JSON strings
                    if raw.startswith('[') and raw.endswith(']'):
                         try: room['amenities'] = json.loads(raw)
                         except: room['amenities'] = [a.strip() for a in raw.strip('[]').split(',') if a.strip()]
                    else:
                         room['amenities'] = [a.strip() for a in raw.split(',') if a.strip()]
                elif not isinstance(raw, list):
                    room['amenities'] = []
        return jsonify({"rooms": [public_record(row, PUBLIC_ROOM_FIELDS) for row in (rooms or [])]}), 200
    except Exception as e:
        return internal_error(e)

@app.route('/api/services', methods=['GET', 'POST'])
def handle_services():
    try:
        if request.method == 'POST':
            user = _get_user_from_request()
            if not user or user.get('role') != 'staff':
                return jsonify({"error": "Staff access required."}), 403
            data = request.get_json()
            service_fields = {'name', 'category', 'price', 'stock_quantity', 'description', 'is_active', 'image_url'}
            data = {key: value for key, value in data.items() if key in service_fields}
            result = supabase_req('services', method='POST', data=data)
            if result is None:
                return jsonify({"error": "Could not save this service. Please try again."}), 500
            return jsonify({"message": "Service created", "service": result}), 201
            
        # GET logic
        staff_param = request.args.get('staff', 'false').lower()
        user = _get_user_from_request() if staff_param == 'true' else None
        is_staff = bool(user and user.get('role') == 'staff')
        
        if is_staff:
            # Staff sees everything
            services = supabase_req('services?select=*&order=id.asc')
        else:
            # Guests ONLY see active services
            # 1. Try standard Boolean filter
            services = supabase_req('services?is_active=eq.true&select=*&order=id.asc')
            
            # 2. If empty, try Integer filter (1)
            if not services:
                services = supabase_req('services?is_active=eq.1&select=*&order=id.asc')
            
            # 3. FINAL CATCH-ALL: Fetch all and filter in Python
            # This is the most reliable way if Supabase is being picky about data types
            if not services:
                print("DEBUG: Standard filters failed, using Python fallback", flush=True)
                all_services = supabase_req('services?select=*&order=id.asc')
                if all_services:
                    services = [
                        s for s in all_services 
                        if s.get('is_active') is True 
                        or str(s.get('is_active')).lower() in ['true', '1', 't', 'yes']
                    ]
            
            print(f"DEBUG: Guest view - active services found: {len(services) if services else 0}", flush=True)
            
        return jsonify({"services": [public_record(row, PUBLIC_SERVICE_FIELDS) for row in (services or [])]}), 200
    except Exception as e:
        return internal_error(e)

import random
import string

# --- HELPERS ---
def generate_ref():
    chars = string.ascii_uppercase + string.digits
    return "MFR-" + "".join(random.choices(chars, k=6))

# Booking/payment routes use authenticated actors and transactional SQL functions.
try:
    from .services.booking_payments import install_booking_routes
except ImportError:
    from services.booking_payments import install_booking_routes
def get_booking_env(key):
    if not key.startswith('PAYMENT_'):
        return get_clean_env(key)
    value = os.getenv(key, '')
    # Werkzeug's reloader can inherit old .env values from its parent process.
    # Reload only public receiving details in local debug mode, preserving names.
    if app.debug:
        from dotenv import dotenv_values
        local_values = dotenv_values(os.path.join(ROOT_DIR, '.env'))
        if key in local_values:
            value = local_values[key] or ''
    return str(value).strip()


booking_rpc = install_booking_routes(app, supabase_req, _get_user_from_request, get_booking_env)
try:
    from .services.email_delivery import install_email_delivery
except ImportError:
    from services.email_delivery import install_email_delivery
def get_email_env(key):
    # The local reloader can inherit old (including empty) values from its parent.
    # Production continues to use the deployment's environment variables.
    value = os.getenv(key, '')
    if app.debug:
        from dotenv import dotenv_values
        local_values = dotenv_values(os.path.join(ROOT_DIR, '.env'))
        if key in local_values:
            value = local_values[key] or ''
    return str(value).strip()

install_email_delivery(app, booking_rpc, supabase_req, get_email_env)

@app.route('/api/reviews', methods=['GET', 'POST'])
def handle_reviews():
    try:
        if request.method == 'POST':
            user = _get_user_from_request()
            if not user:
                return jsonify({"error": "Unauthorized"}), 401

            data = request.get_json() or {}
            room_id = data.get('room_id')
            booking_id = data.get('booking_id')
            rating = data.get('rating')
            review_text = data.get('review')

            if room_id is None or rating is None:
                return jsonify({"error": "room_id and rating are required."}), 400
            if isinstance(room_id, bool) or not str(room_id).isdigit() or int(room_id) <= 0 or isinstance(booking_id, bool) or not str(booking_id).isdigit() or int(booking_id) <= 0:
                return jsonify(error='A valid room and completed booking are required.'), 400
            room_id, booking_id = int(room_id), int(booking_id)
            owned = supabase_req(f'bookings?id=eq.{booking_id}&user_id=eq.{int(user["id"])}&room_id=eq.{room_id}&status=eq.completed&select=id&limit=1')
            if not owned:
                return jsonify(error='You may only review your own completed stay.'), 403
            if review_text is not None and (not isinstance(review_text, str) or len(review_text) > 2000):
                return jsonify(error='Review text must be at most 2000 characters.'), 400

            try:
                rating_int = int(rating)
            except Exception:
                return jsonify({"error": "rating must be an integer."}), 400

            if rating_int < 1 or rating_int > 5:
                return jsonify({"error": "rating must be between 1 and 5."}), 400

            # Prevent duplicate reviews. Prefer booking_id if the schema supports it;
            # otherwise fall back to user_id + room_id.
            if booking_id is not None:
                existing = supabase_req(f'reviews?booking_id=eq.{booking_id}&select=id&limit=1')
                if isinstance(existing, list) and existing:
                    return jsonify({"error": "You already reviewed this booking."}), 409

            try:
                existing_fallback = supabase_req(
                    f'reviews?user_id=eq.{user.get("id")}&room_id=eq.{room_id}&select=id&limit=1'
                )
                if existing_fallback:
                    return jsonify({"error": "You already reviewed this room."}), 409
            except Exception:
                pass

            # Supabase schema (from your screenshot) uses 'comment' not 'review'.
            payload = {
                'room_id': room_id,
                'user_id': user.get('id'),
                'rating': rating_int,
                'comment': review_text
            }

            # Try including booking_id if present; ignore if schema doesn't have it.
            if booking_id is not None:
                payload_with_booking = dict(payload)
                payload_with_booking['booking_id'] = booking_id
            else:
                payload_with_booking = payload

            result = supabase_req('reviews', method='POST', data=payload_with_booking)
            if result is None and booking_id is not None:
                # Supabase returned a 400 like: "Could not find the 'booking_id' column..."
                # supabase_req swallows the exception and returns None, so explicitly retry.
                result = supabase_req('reviews', method='POST', data=payload)

            if result is None:
                return jsonify({"error": "Failed to save review. Please try again."}), 500

            inserted = result[0] if isinstance(result, list) and result else payload
            inserted['guest_name'] = user.get('name')
            inserted['review'] = inserted.get('review') or inserted.get('comment') or ''
            safe_review = {key: inserted.get(key) for key in ('id', 'room_id', 'rating', 'created_at', 'guest_name', 'review')}
            return jsonify({"message": "Review added", "review": safe_review}), 201
            
        room_id = request.args.get('room_id')
        if room_id is not None:
            if not room_id.isdigit() or int(room_id) <= 0:
                return jsonify(error='Invalid room.'), 400
            room_id = int(room_id)
        endpoints_to_try = []
        endpoints_to_try.append('reviews?select=*,users(name)&order=created_at.desc')
        endpoints_to_try.append('reviews?select=*&order=created_at.desc')
        endpoints_to_try.append('reviews?select=*')

        rows = []
        last_err = None
        for base in endpoints_to_try:
            endpoint = base + '&limit=100'
            if room_id:
                endpoint += f'&room_id=eq.{room_id}'
            try:
                rows = supabase_req(endpoint) or []
                last_err = None
                break
            except Exception as e:
                last_err = e
                rows = []

        if last_err is not None:
            app.logger.warning("Review lookup failed (%s)", type(last_err).__name__)

        formatted = []
        total = 0
        sum_rating = 0
        for r in rows if isinstance(rows, list) else []:
            rating_val = r.get('rating')
            try:
                rating_num = float(rating_val) if rating_val is not None else 0
            except Exception:
                rating_num = 0
            sum_rating += rating_num
            total += 1

            user_info = r.get('users', {})
            guest_name = None
            if isinstance(user_info, dict):
                guest_name = user_info.get('name')
            elif isinstance(user_info, list) and user_info:
                guest_name = (user_info[0] or {}).get('name')

            formatted.append({
                'id': r.get('id'), 'room_id': r.get('room_id'),
                'rating': rating_num, 'created_at': r.get('created_at'),
                'guest_name': r.get('guest_name') or guest_name or 'Guest',
                'review': r.get('review') or r.get('comment') or ''
            })

        avg = round((sum_rating / total), 2) if total else 0

        return jsonify({
            "reviews": formatted,
            "average_rating": avg,
            "total_reviews": total
        }), 200
    except Exception as e:
        return internal_error(e)

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    return jsonify({"message": "Logged out"}), 200

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_me():
    try:
        user_id = get_jwt_identity()
        users = supabase_req(f'users?id=eq.{user_id}&select=*')
        if not users:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"user": public_user(users[0])}), 200
    except Exception as e:
        return internal_error(e)

@app.route('/api/auth/profile', methods=['PATCH'])
@jwt_required()
def update_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'name'}:
        return jsonify({'error': 'Only a profile name can be updated.'}), 400
    name = data.get('name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        return jsonify({'error': 'Name must contain 1 to 100 characters.'}), 400
    user_id = quote(str(get_jwt_identity()), safe='')
    try:
        updated = supabase_req(f'users?id=eq.{user_id}', method='PATCH', data={'name': name.strip()})
        if not isinstance(updated, list) or not updated:
            return jsonify({'error': 'Could not save your profile. Please try again.'}), 503
        return jsonify({'user': public_user(updated[0])}), 200
    except Exception:
        return jsonify({'error': 'Could not save your profile. Please try again.'}), 503


@app.route('/api/rooms/<int:room_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_single_room(room_id):
    try:
        if request.method in ('PUT', 'DELETE'):
            user = _get_user_from_request()
            if not user or user.get('role') != 'staff':
                return jsonify({"error": "Staff access required."}), 403
        if request.method == 'PUT':
            import sys
            data = request.get_json()
            sys.stdout.flush()
            
            if not data:
                return jsonify({"error": "No data received"}), 400
                
            # Strict mapping to ensure everything saves
            room_status = data.get('room_status', 'available')
            update_data = {
                "name": data.get('name'),
                "type": data.get('type'),
                "room_number": data.get('room_number'),
                "capacity": int(data.get('capacity', 2)) if data.get('capacity') else 2,
                "price_per_night": float(data.get('price_per_night', 0)) if data.get('price_per_night') else 0,
                "description": data.get('description'),
                "sqm": int(data.get('sqm', 0)) if data.get('sqm') else None,
                "room_status": room_status,
                "is_available": room_status == 'available',  # Sync is_available with room_status
                "image_url": data.get('image_url'),
                "image_url_2": data.get('image_url_2'),
                "image_url_3": data.get('image_url_3'),
                "image_url_4": data.get('image_url_4'),
                "image_url_5": data.get('image_url_5')
            }
            sys.stdout.flush()
            
            # Handle amenities if it's a list
            if 'amenities' in data:
                if isinstance(data['amenities'], list):
                    update_data['amenities'] = ", ".join(data['amenities'])
                else:
                    update_data['amenities'] = data['amenities']
            
            result = supabase_req(f'rooms?id=eq.{room_id}', method='PATCH', data=update_data)
            sys.stdout.flush()
            # Fetch fresh data after update (Supabase PATCH doesn't return updated row)
            updated = supabase_req(f'rooms?id=eq.{room_id}&select=*')
            sys.stdout.flush()
            return jsonify({"message": "Room updated successfully", "room": updated[0] if updated else result}), 200
        
        if request.method == 'DELETE':
            supabase_req(f'rooms?id=eq.{room_id}', method='DELETE')
            return jsonify({"message": "Room deleted"}), 200
            
        # Fix: ensure we return room object, not list
        res = supabase_req(f'rooms?id=eq.{room_id}&select=*')
        if res and isinstance(res, list) and len(res) > 0:
            room = res[0]
            raw_amenities = room.get('amenities', '')
            if isinstance(raw_amenities, str):
                room['amenities'] = [a.strip() for a in raw_amenities.split(',') if a.strip()]
            return jsonify({"room": public_record(room, PUBLIC_ROOM_FIELDS)}), 200
        return jsonify({"error": "Room not found"}), 404
    except Exception as e:
        return internal_error(e)

@app.route('/api/services/<int:service_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_single_service(service_id):
    try:
        if request.method in ('PUT', 'DELETE'):
            user = _get_user_from_request()
            if not user or user.get('role') != 'staff':
                return jsonify({"error": "Staff access required."}), 403
        if request.method == 'PUT':
            data = request.get_json()
            
            # Ensure we only send valid fields to Supabase
            update_data = {}
            if 'is_active' in data:
                # Force strictly to boolean if it's not already
                val = data['is_active']
                if isinstance(val, str):
                    update_data['is_active'] = val.lower() == 'true'
                else:
                    update_data['is_active'] = bool(val)
            
            if 'stock_quantity' in data:
                update_data['stock_quantity'] = int(data['stock_quantity'])
            if 'price' in data:
                update_data['price'] = float(data['price'])
            if 'name' in data:
                update_data['name'] = data['name']
            if 'category' in data:
                update_data['category'] = data['category']
            if 'image_url' in data:
                update_data['image_url'] = data['image_url'] or None
            if 'description' in data:
                update_data['description'] = data['description']
                
            
            # Perform the update
            result = supabase_req(f'services?id=eq.{service_id}', method='PATCH', data=update_data)
            if result is None:
                return jsonify({"error": "Could not save this service. Please try again."}), 500
            
            # Immediately fetch the updated service to return it
            updated = supabase_req(f'services?id=eq.{service_id}&select=*')
            return jsonify({"message": "Service updated successfully", "service": updated[0] if updated else None}), 200
        
        if request.method == 'DELETE':
            result = supabase_req(f'services?id=eq.{service_id}', method='PATCH', data={'is_active': False})
            if result is None:
                return jsonify({"error": "Could not hide this service. Please try again."}), 500
            return jsonify({"message": "Service hidden. Request and payment history retained."}), 200
            
        service = supabase_req(f'services?id=eq.{service_id}&select=*')
        if service and service[0].get('is_active') not in (True, 1, 'true', '1'):
            viewer = _get_user_from_request()
            if not viewer or viewer.get('role') != 'staff':
                return jsonify(error='Service not found.'), 404
        return jsonify({"service": public_record(service[0], PUBLIC_SERVICE_FIELDS) if service else None}), 200
    except Exception as e:
        app.logger.warning("Service update failed (%s)", type(e).__name__)
        return internal_error(e)

@app.route('/api/rooms/upload-image', methods=['POST'])
def upload_image():
    try:
        user = _get_user_from_request()
        if not user or user.get('role') != 'staff':
            return jsonify(error='Staff access required.'), 403
        data = request.get_json()
        base64_image = data.get('image')
        
        if not base64_image:
            return jsonify({"error": "No image data provided"}), 400
        if not isinstance(base64_image, str) or len(base64_image) > 2800000 or not re.fullmatch(r'data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]+', base64_image):
            return jsonify(error='Use a JPG, PNG or WebP image up to 2 MB.'), 400
        raw = base64.b64decode(base64_image.split(',', 1)[1], validate=True)
        if len(raw) > 2 * 1024 * 1024 or not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG\r\n\x1a\n') or (raw.startswith(b'RIFF') and raw[8:12] == b'WEBP')):
            return jsonify(error='Invalid image.'), 400
            
        # In a real app, we would upload this to Supabase Storage.
        # For now, we return the base64 string directly as the image URL 
        # so it displays instantly on the dashboard/rooms page.
        return jsonify({
            "message": "Image uploaded successfully!",
            "image_url": base64_image
        }), 200
    except Exception as e:
        return internal_error(e)

# --- FRONTEND STATIC & SPA FALLBACK ROUTES ---
@app.route('/')
@app.route('/index.html')
def serve_index():
    return send_from_directory(PUBLIC_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path in ('index.html', ''):
        return send_from_directory(PUBLIC_DIR, 'index.html')
    if path.startswith('.') or path.endswith(('.py', '.sql', '.env')):
        return jsonify({"error": "Not found"}), 404
    if path == 'privacy.html':
        return send_from_directory(PUBLIC_DIR, path)
    if path.startswith('assets/'):
        return send_from_directory(os.path.join(PUBLIC_DIR, 'assets'), path[len('assets/'):])
    if path.startswith('api/'):
        return jsonify({"error": f"API endpoint /{path} not found"}), 404
    return send_from_directory(PUBLIC_DIR, 'index.html')

# Vercel entry point
handler = app

if __name__ == "__main__":
    app.run(debug=False, host='127.0.0.1')
