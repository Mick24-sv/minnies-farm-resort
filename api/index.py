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
CORS(app)

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
        from flask_jwt_extended import decode_token
        decoded = decode_token(received_token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        try:
            user_id = get_jwt_identity()
        except Exception:
            user_id = None

    if user_id is None:
        return None

    try:
        user_id_int = int(user_id)
    except Exception:
        return None

    users = supabase_req(f'users?id=eq.{user_id_int}&select=*')
    if not users:
        return None
    return users[0]

# --- ROUTES ---
@app.after_request
def add_header(response):
    # FORCE NO CACHE - ensures staff updates reflect immediately
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/api/health')
def health():
    return jsonify({
        "status": "online",
        "supabase_connected": bool(SUPABASE_URL and SUPABASE_KEY),
        "jwt_configured": bool(os.getenv("JWT_SECRET_KEY")),
        "env_check": {
            "SUPABASE_URL": "configured" if bool(SUPABASE_URL) else "missing",
            "SUPABASE_KEY": "configured" if bool(SUPABASE_KEY) else "missing",
            "JWT_SECRET_KEY": "configured" if bool(os.getenv("JWT_SECRET_KEY")) else "missing"
        }
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password')

        if not email or not isinstance(password, str) or not password:
            return jsonify({"error": "Invalid email or password."}), 401

        users = supabase_req(f'users?email=eq.{quote(email, safe="")}&select=*')
        
        if not users:
            return jsonify({"error": "Invalid email or password."}), 401
        
        user = users[0]
        stored_pw = user.get('password')
        
        # Check password (handles both hashed and plain)
        is_valid = False
        try:
            is_valid = pbkdf2_sha256.verify(password, stored_pw)
        except:
            is_valid = (password == stored_pw)
            
        if not is_valid:
            return jsonify({"error": "Invalid email or password."}), 401

        token = create_access_token(identity=str(user.get('id')))
        return jsonify({"token": token, "user": public_user(user)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = data.get('password')

        if not name or not email or not password:
            return jsonify({"error": "'name', 'email', and 'password' are required."}), 400

        # check existing
        existing = supabase_req(f'users?email=eq.{email}&select=id&limit=1')
        if existing:
            return jsonify({"error": "Email is already registered."}), 409

        hashed_pw = pbkdf2_sha256.hash(password)
        user_data = {
            'name': name,
            'email': email,
            'password': hashed_pw,
            'role': 'guest',
            'is_verified': True
        }

        created = supabase_req('users', method='POST', data=user_data)
        user = created[0] if isinstance(created, list) and created else user_data
        user.pop('password', None)

        return jsonify({"message": "Account created! You can now sign in.", "user": public_user(user)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/google', methods=['POST'])
def google_login():
    try:
        data = request.get_json(silent=True) or {}
        access_token = data.get('access_token')
        if not isinstance(access_token, str) or not access_token or len(access_token) > 4096:
            return jsonify({'error': 'A valid Google sign-in token is required.'}), 401
        # Identity must come from Google, never from email/name sent by the browser.
        try:
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

        users = supabase_req(f'users?email=eq.{email}&select=*')
        user = users[0] if users else None

        if not user:
            user_data = {
                'name': name,
                'email': email,
                'password': pbkdf2_sha256.hash(secrets.token_urlsafe(32)),
                'role': 'guest',
                'is_verified': True
            }
            user = supabase_req('users', method='POST', data=user_data)
            if isinstance(user, list): user = user[0]

        token = create_access_token(identity=str(user.get('id')))
        return jsonify({'token': token, 'user': public_user(user)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rooms', methods=['GET', 'POST'])
def handle_rooms():
    try:
        if request.method == 'POST':
            user = _get_user_from_request()
            if not user or user.get('role') != 'staff':
                return jsonify({"error": "Staff access required."}), 403
        if request.method == 'POST':
            data = request.get_json()
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
        return jsonify({"rooms": rooms or []}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/services', methods=['GET', 'POST'])
def handle_services():
    try:
        if request.method == 'POST':
            user = _get_user_from_request()
            if not user or user.get('role') != 'staff':
                return jsonify({"error": "Staff access required."}), 403
            data = request.get_json()
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
            
        return jsonify({"services": services if services is not None else []}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            return jsonify({"message": "Review added", "review": inserted}), 201
            
        room_id = request.args.get('room_id')
        endpoints_to_try = []
        endpoints_to_try.append('reviews?select=*,users(name)&order=created_at.desc')
        endpoints_to_try.append('reviews?select=*&order=created_at.desc')
        endpoints_to_try.append('reviews?select=*')

        rows = []
        last_err = None
        for base in endpoints_to_try:
            endpoint = base
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
            print(f"Error fetching reviews after fallbacks: {last_err}", flush=True)

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
                **r,
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
        return jsonify({"error": str(e)}), 500

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
        return jsonify({"error": str(e)}), 500

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
            return jsonify({"room": room}), 200
        return jsonify({"error": "Room not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        return jsonify({"service": service[0] if service else None}), 200
    except Exception as e:
        print(f"Service update error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/rooms/upload-image', methods=['POST'])
def upload_image():
    try:
        data = request.get_json()
        base64_image = data.get('image')
        
        if not base64_image:
            return jsonify({"error": "No image data provided"}), 400
            
        # In a real app, we would upload this to Supabase Storage.
        # For now, we return the base64 string directly as the image URL 
        # so it displays instantly on the dashboard/rooms page.
        return jsonify({
            "message": "Image uploaded successfully!",
            "image_url": base64_image
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    app.run(debug=True)
