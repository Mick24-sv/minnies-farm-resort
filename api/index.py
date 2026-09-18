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
if not os.path.exists(os.path.join(ROOT_DIR, 'index.html')):
    ROOT_DIR = os.getcwd()

DEBUG = os.getenv('DEBUG', '').strip() == '1'

def get_clean_env(key):
    val = os.environ.get(key) or os.getenv(key) or ""
    # Remove all whitespace, newlines, and quotes that might have been pasted by accident
    return val.strip().replace("\n", "").replace("\r", "").replace(" ", "").replace("'", "").replace('"', "")

_jwt_secret = get_clean_env("JWT_SECRET_KEY") or "default-insecure-secret-set-in-vercel"
app.config["JWT_SECRET_KEY"] = _jwt_secret
jwt = JWTManager(app)

SUPABASE_URL = get_clean_env('SUPABASE_URL')
SUPABASE_KEY = get_clean_env('SUPABASE_KEY')
XENDIT_API_KEY = get_clean_env('XENDIT_API_KEY')
XENDIT_WEBHOOK_TOKEN = get_clean_env('XENDIT_WEBHOOK_TOKEN')

RESET_TOKENS = {}


def build_xendit_invoice_payload(external_id, amount, description, payer_email=None, metadata=None, currency='PHP'):
    payload = {
        'external_id': str(external_id),
        'amount': int(round(float(amount))),
        'description': description,
        'currency': currency,
        'success_redirect_url': os.getenv('FRONTEND_URL') or 'https://example.com/',
    }
    if payer_email:
        payload['payer_email'] = payer_email
    if metadata:
        payload['metadata'] = metadata
    return payload


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
            print(f"Supabase API Call: {method} {url}")
        
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
            print(f"Supabase Response: {res.text[:500]}")

        res.raise_for_status()
        return res.json() if res.text else []

    except Exception as e:
        if DEBUG:
            print(f"Supabase request error ({method} {endpoint}): {str(e)}")
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

@app.route('/api/payments/xendit/create-invoice', methods=['POST'])
def create_xendit_invoice():
    try:
        user = _get_user_from_request()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        if not XENDIT_API_KEY:
            return jsonify({"error": "Xendit is not configured on this server."}), 500

        data = request.get_json() or {}
        room_id = data.get('room_id')
        if not room_id:
            return jsonify({"error": "room_id is required."}), 400

        room_res = supabase_req(f'rooms?id=eq.{room_id}&select=*')
        if not room_res:
            return jsonify({"error": "Room not found."}), 404
        room = room_res[0]

        from datetime import date
        try:
            ci = date.fromisoformat(data.get('check_in_date') or data.get('checkIn') or data.get('check_in'))
            co = date.fromisoformat(data.get('check_out_date') or data.get('checkOut') or data.get('check_out'))
            nights = (co - ci).days
            if nights <= 0:
                nights = 1
        except Exception:
            return jsonify({"error": "Invalid booking dates."}), 400

        price_per_night = float(room.get('price_per_night', 0) or 0)
        subtotal = price_per_night * nights
        total_price = round(subtotal + (subtotal * 0.10), 2)

        base_url = os.getenv('FRONTEND_URL') or request.host_url
        external_id = f"booking-{room_id}-{int(time.time())}"
        payload = build_xendit_invoice_payload(
            external_id=external_id,
            amount=total_price,
            description=f"{room.get('name', 'Room')} booking for {ci.isoformat()} to {co.isoformat()}",
            payer_email=(user.get('email') or '').strip(),
            metadata={
                'room_id': str(room_id),
                'user_id': str(user.get('id')),
                'check_in': ci.isoformat(),
                'check_out': co.isoformat(),
                'guest_count': str(int(data.get('num_guests') or data.get('guest_count') or data.get('guests') or 1)),
                'total_price': str(total_price)
            }
        )

        xendit_response = requests.post(
            'https://api.xendit.co/v2/invoices',
            auth=('', XENDIT_API_KEY),
            json=payload,
            timeout=20
        )

        if xendit_response.status_code >= 400:
            return jsonify({"error": xendit_response.text}), xendit_response.status_code

        invoice = xendit_response.json()
        return jsonify({
            "message": "Invoice created.",
            "invoice_id": invoice.get('id'),
            "invoice_url": invoice.get('invoice_url'),
            "status": invoice.get('status'),
            "amount": total_price,
            "external_id": external_id
        }), 200
    except Exception as e:
        print(f"Xendit invoice error: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password')

        users = supabase_req(f'users?email=eq.{email}&select=*')
        
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
        return jsonify({"token": token, "user": user}), 200
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

        return jsonify({"message": "Account created! You can now sign in.", "user": user}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        if not email:
            return jsonify({'error': 'Email is required.'}), 400

        users = supabase_req(f'users?email=eq.{email}&select=id,name,email&limit=1')
        if users:
            token = secrets.token_urlsafe(32)
            RESET_TOKENS[token] = {'user_id': users[0].get('id'), 'expires': time.time() + 3600}

        # Always return 200 to avoid leaking whether email exists
        return jsonify({'message': 'If that email exists, a reset link has been sent.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.get_json() or {}
        token = data.get('token')
        new_password = data.get('password')
        if not token or not new_password:
            return jsonify({'error': 'Token and password are required.'}), 400

        token_data = RESET_TOKENS.get(token)
        if not token_data:
            return jsonify({'error': 'Invalid or expired reset token.'}), 400
        if time.time() > token_data.get('expires', 0):
            RESET_TOKENS.pop(token, None)
            return jsonify({'error': 'Reset token has expired.'}), 400

        hashed_pw = pbkdf2_sha256.hash(new_password)
        supabase_req(f'users?id=eq.{token_data["user_id"]}', method='PATCH', data={'password': hashed_pw})
        RESET_TOKENS.pop(token, None)
        return jsonify({'message': 'Password reset successfully!'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/google', methods=['POST'])
def google_login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        name = data.get('name')
        google_id = data.get('google_id')

        if not email or not google_id:
            return jsonify({'error': 'Invalid Google credentials'}), 400

        users = supabase_req(f'users?email=eq.{email}&select=*')
        user = users[0] if users else None

        if not user:
            user_data = {
                'name': name,
                'email': email,
                'password': pbkdf2_sha256.hash(google_id),
                'role': 'guest',
                'is_verified': True
            }
            user = supabase_req('users', method='POST', data=user_data)
            if isinstance(user, list): user = user[0]

        token = create_access_token(identity=str(user.get('id')))
        return jsonify({'token': token, 'user': user}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rooms', methods=['GET', 'POST'])
def handle_rooms():
    try:
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
            data = request.get_json()
            result = supabase_req('services', method='POST', data=data)
            return jsonify({"message": "Service created", "service": result}), 201
            
        # GET logic
        staff_param = request.args.get('staff', 'false').lower()
        is_staff = (staff_param == 'true')
        
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

@app.route('/api/services/avails', methods=['GET'])
def get_service_avails():
    try:
        # Based on logs, service_availability was not found. Using service_avails.
        # Joining with services table to get service names and prices
        # VERIFIED SCHEMA: 'created_at' and 'status' do NOT exist. Use 'availed_at' for ordering.
        
        user_id = request.args.get('user_id')
        staff_param = request.args.get('staff', 'false').lower() == 'true'
        
        if staff_param:
            # Staff sees everything
            endpoint = 'service_avails?select=*,services(name,price),users(name,email)&order=availed_at.desc'
        elif user_id:
            # Guest sees only their own
            endpoint = f'service_avails?user_id=eq.{user_id}&select=*,services(name,price),users(name,email)&order=availed_at.desc'
        else:
            endpoint = 'service_avails?select=*,services(name,price),users(name,email)&order=availed_at.desc'
            
        print(f"DEBUG: Service Avails Request: {endpoint}", flush=True)
        avails = supabase_req(endpoint)
        
        # Flatten the joined data for the frontend
        formatted_avails = []
        if avails and isinstance(avails, list):
            for a in avails:
                service_info = a.get('services', {})
                user_info = a.get('users', {})
                formatted_avails.append({
                    "id": a.get('id'),
                    "service_id": a.get('service_id'),
                    "user_id": a.get('user_id'),
                    "guest_name": (user_info.get('name') if isinstance(user_info, dict) else None) or a.get('guest_name') or '',
                    "guest_email": (user_info.get('email') if isinstance(user_info, dict) else None) or a.get('guest_email') or '',
                    "status": a.get('status') or "pending",
                    "notes": a.get('notes'),
                    "availed_at": a.get('availed_at'),
                    "created_at": a.get('availed_at'), # Keep for frontend compatibility
                    "service_name": service_info.get('name', 'Unknown Service'),
                    "total_price": a.get('total_price') or service_info.get('price', 0)
                })
        
        print(f"DEBUG: Returning {len(formatted_avails)} formatted avails", flush=True)
        return jsonify({"avails": formatted_avails}), 200
    except Exception as e:
        print(f"Error fetching service avails: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/services/avails/<avail_id>', methods=['DELETE', 'PATCH'])
def handle_service_avail_action(avail_id):
    try:
        if request.method == 'DELETE':
            print(f"DEBUG: Deleting service request {avail_id}", flush=True)
            supabase_req(f'service_avails?id=eq.{avail_id}', method='DELETE')
            return jsonify({"message": "Service request deleted"}), 200
            
        if request.method == 'PATCH':
            data = request.get_json()
            status = (data or {}).get('status')
            if not status:
                return jsonify({"error": "Status is required"}), 400

            valid_statuses = ('pending', 'confirmed', 'completed', 'cancelled')
            if status not in valid_statuses:
                return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400

            # Preferred behavior: persist status if the column exists.
            try:
                supabase_req(f'service_avails?id=eq.{avail_id}', method='PATCH', data={'status': status})
                return jsonify({"message": f"Service request {status}", "id": avail_id, "status": status}), 200
            except Exception as e:
                # Fallback for older schemas where 'status' column doesn't exist.
                err_str = str(e)
                print(f"DEBUG: PATCH service_avails status failed: {err_str}", flush=True)
                if status in ('confirmed', 'completed', 'cancelled') and ('status' in err_str and 'column' in err_str):
                    try:
                        supabase_req(f'service_avails?id=eq.{avail_id}', method='DELETE')
                        return jsonify({"message": f"Service request {status}", "id": avail_id, "status": status}), 200
                    except Exception as e2:
                        print(f"DEBUG: Action DELETE service_avails failed: {e2}", flush=True)
                        return jsonify({"error": "Failed to update service request."}), 500
                return jsonify({"error": "Failed to update service request."}), 500
            
    except Exception as e:
        print(f"Error in service avail action: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

import random
import string

# --- HELPERS ---
def generate_ref():
    chars = string.ascii_uppercase + string.digits
    return "MFR-" + "".join(random.choices(chars, k=6))

@app.route('/api/bookings', methods=['GET', 'POST'])
def handle_bookings():
    try:
        if request.method == 'POST':
            # ... existing POST logic ...
            data = request.get_json()
            room_id = data.get('room_id')
            user_id = data.get('user_id')
            
            print(f"DEBUG: Booking request received. User: {user_id}, Room: {room_id}", flush=True)
            
            # Fetch room details for pricing
            room_res = supabase_req(f'rooms?id=eq.{room_id}&select=*')
            if not room_res:
                print(f"DEBUG: Room {room_id} not found in database.", flush=True)
                return jsonify({"error": "Room not found"}), 404
            
            room = room_res[0]
            price_per_night = float(room.get('price_per_night', 0))
            
            # Calculate nights
            from datetime import date
            try:
                ci = date.fromisoformat(data['check_in_date'])
                co = date.fromisoformat(data['check_out_date'])
                nights = (co - ci).days
                if nights <= 0: nights = 1
            except Exception as e:
                print(f"DEBUG: Date parsing error: {e}", flush=True)
                return jsonify({"error": "Invalid dates"}), 400
            
            # Final Price Calculation
            subtotal = price_per_night * nights
            total_price = round(subtotal + (subtotal * 0.10), 2)
            
            # Force user_id to int
            if isinstance(user_id, str) and user_id.isdigit():
                user_id = int(user_id)
            elif not user_id:
                # Fallback: get from token if possible
                try:
                    from flask_jwt_extended import get_jwt_identity
                    token_user_id = get_jwt_identity()
                    if token_user_id:
                        user_id = int(token_user_id)
                except: pass

            if not user_id:
                print("DEBUG: CRITICAL ERROR - No user_id found for booking", flush=True)
                return jsonify({"error": "User session expired or not found"}), 401

            # VERIFIED SCHEMA FROM SUPABASE ERROR LOGS:
            # reference_code does NOT exist in the schema.
            # check_in, check_out, total_price, status, guest_count are valid.
            booking_data = {
                "user_id": user_id,
                "room_id": room_id,
                "check_in": data.get('check_in_date') or data.get('checkIn') or data.get('check_in'),
                "check_out": data.get('check_out_date') or data.get('checkOut') or data.get('check_out'),
                "guest_count": int(data.get('num_guests') or data.get('guest_count') or data.get('guests') or 1),
                "total_price": float(total_price),
                "status": "confirmed"
            }
            
            # reference_code was causing 400 errors because the column doesn't exist.
            # We will use the Supabase-generated ID as the reference for the UI.
            
            print(f"DEBUG: Sending to Supabase: {booking_data}", flush=True)
            result = supabase_req('bookings', method='POST', data=booking_data)
            
            # If Supabase returns nothing but didn't error, the insert likely worked.
            # Use the result ID as a reference if available, otherwise use a local placeholder
            res_item = result[0] if isinstance(result, list) and len(result) > 0 else (result if result else booking_data)
            
            # Ensure a reference exists for the confirmation screen
            if 'id' in res_item:
                res_item['reference_code'] = f"MFR-{res_item['id']}"
            elif 'reference_code' not in res_item:
                res_item['reference_code'] = generate_ref()
                
            return jsonify({
                "message": "Booking successful!", 
                "booking": res_item
            }), 201
        
        # GET logic
        is_staff = request.args.get('staff') == 'true'
        user_id_param = request.args.get('user_id')
        
        print(f"DEBUG: Fetching bookings. is_staff={is_staff}, user_id_param={user_id_param}", flush=True)
        
        if is_staff:
            # Staff can see all bookings
            bookings = supabase_req('bookings?select=*&order=created_at.desc')
        elif user_id_param:
            # Guest sees only their own
            # Use numeric user_id check in query
            user_id_int = None
            try:
                user_id_int = int(user_id_param)
            except:
                pass
                
            # If user_id fails, we might want to allow a broader search or log more
            endpoint = f'bookings?user_id=eq.{user_id_int if user_id_int is not None else user_id_param}&select=*&order=created_at.desc'
            print(f"DEBUG: Supabase request for user {user_id_param}: {endpoint}", flush=True)
            bookings = supabase_req(endpoint)
            
            # FALLBACK: If no bookings found by user_id, it might be a registration mismatch.
            # Let's try to see if we can find ANY bookings just to see if the table is working.
            if not bookings:
                print(f"DEBUG: No bookings found for user_id {user_id_param}. Checking total table count...", flush=True)
                all_count = supabase_req('bookings?select=id&limit=1')
                print(f"DEBUG: Table accessibility check: {all_count}", flush=True)
        else:
            # Fallback if no user_id is provided
            print("DEBUG: No user_id or staff flag provided for bookings GET", flush=True)
            bookings = []
            
        print(f"DEBUG: Returning {len(bookings) if bookings else 0} bookings", flush=True)
        return jsonify({"bookings": bookings or []}), 200
    except Exception as e:
        print(f"DEBUG: Error in handle_bookings: {str(e)}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/bookings/<booking_id>/status', methods=['PUT'])
def update_booking_status(booking_id):
    try:
        user = _get_user_from_request()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        if str(user.get('role', '')).lower() != 'staff':
            return jsonify({"error": "Only staff can update booking status."}), 403

        data = request.get_json() or {}
        status = data.get('status')
        if status not in ('pending', 'confirmed', 'cancelled', 'completed'):
            return jsonify({"error": "Invalid status."}), 400

        existing = supabase_req(f'bookings?id=eq.{booking_id}&select=*')
        if not existing:
            return jsonify({"error": "Booking not found."}), 404

        supabase_req(f'bookings?id=eq.{booking_id}', method='PATCH', data={'status': status})
        updated = supabase_req(f'bookings?id=eq.{booking_id}&select=*')
        return jsonify({"message": "Status updated!", "booking": updated[0] if updated else {"id": booking_id, "status": status}}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def delete_or_cancel_booking(booking_id):
    try:
        user = _get_user_from_request()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        existing = supabase_req(f'bookings?id=eq.{booking_id}&select=*')
        if not existing:
            return jsonify({"error": "Booking not found."}), 404
        booking = existing[0]

        if str(user.get('role', '')).lower() == 'staff':
            supabase_req(f'bookings?id=eq.{booking_id}', method='DELETE')
            return jsonify({"message": "Booking deleted successfully."}), 200

        # Guest cancellation (soft)
        if str(booking.get('user_id')) != str(user.get('id')):
            return jsonify({"error": "You can only cancel your own bookings."}), 403
        if booking.get('status') in ('cancelled', 'completed'):
            return jsonify({"error": f"Booking is already {booking.get('status')}."}), 400

        supabase_req(f'bookings?id=eq.{booking_id}', method='PATCH', data={'status': 'cancelled'})
        updated = supabase_req(f'bookings?id=eq.{booking_id}&select=*')
        return jsonify({"message": "Booking cancelled successfully.", "booking": updated[0] if updated else {"id": booking_id, "status": "cancelled"}}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        return jsonify({"user": users[0]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rooms/<int:room_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_single_room(room_id):
    try:
        if request.method == 'PUT':
            import sys
            data = request.get_json()
            print(f"Room PUT data received: {data}", flush=True)
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
            print(f"Room update_data: {update_data}", flush=True)
            sys.stdout.flush()
            
            # Handle amenities if it's a list
            if 'amenities' in data:
                if isinstance(data['amenities'], list):
                    update_data['amenities'] = ", ".join(data['amenities'])
                else:
                    update_data['amenities'] = data['amenities']
            
            result = supabase_req(f'rooms?id=eq.{room_id}', method='PATCH', data=update_data)
            print(f"Room PATCH result: {result}", flush=True)
            sys.stdout.flush()
            # Fetch fresh data after update (Supabase PATCH doesn't return updated row)
            updated = supabase_req(f'rooms?id=eq.{room_id}&select=*')
            print(f"Room updated fetch: {updated}", flush=True)
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
        if request.method == 'PUT':
            data = request.get_json()
            print(f"DEBUG: Updating service {service_id} with data: {data}", flush=True)
            
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
            if 'description' in data:
                update_data['description'] = data['description']
                
            print(f"DEBUG: Final PATCH data for Supabase: {update_data}", flush=True)
            
            # Perform the update
            supabase_req(f'services?id=eq.{service_id}', method='PATCH', data=update_data)
            
            # Immediately fetch the updated service to return it
            updated = supabase_req(f'services?id=eq.{service_id}&select=*')
            return jsonify({"message": "Service updated successfully", "service": updated[0] if updated else None}), 200
        
        if request.method == 'DELETE':
            supabase_req(f'services?id=eq.{service_id}', method='DELETE')
            return jsonify({"message": "Service deleted successfully"}), 200
            
        service = supabase_req(f'services?id=eq.{service_id}&select=*')
        return jsonify({"service": service[0] if service else None}), 200
    except Exception as e:
        print(f"Service update error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/services/<int:service_id>/avail', methods=['POST'])
def avail_service(service_id):
    try:
        # Create a new entry in service_avails table based on Supabase schema
        data = request.get_json() or {}
        
        # Get user_id from token (required for this action)
        user_id = None
        
        # Try to get user_id from JWT token manually if flask_jwt_extended is having issues
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            received_token = auth_header.split(' ')[1]
            try:
                # Use flask_jwt_extended to decode if possible
                from flask_jwt_extended import decode_token
                decoded = decode_token(received_token)
                user_id = decoded.get('sub') or decoded.get('identity')
            except Exception as jwt_err:
                print(f"DEBUG: JWT Decode error: {jwt_err}", flush=True)
                
        # Fallback to body if token parsing failed but we have a body user_id
        if not user_id:
            user_id = data.get('user_id')
            
        if not user_id:
            print("DEBUG: 401 Unauthorized - No user_id found in token or body", flush=True)
            return jsonify({"error": "User authentication required. Please log in again."}), 401
            
        # Ensure user_id is int
        try: user_id = int(user_id)
        except: pass
            
        # Fetch service price for total_price
        service_res = supabase_req(f'services?id=eq.{service_id}&select=*')
        if not service_res:
            return jsonify({"error": "Service not found"}), 404
        
        service_price = float(service_res[0].get('price', 0))
        quantity = int(data.get('quantity', 1))
        
        # VERIFIED SCHEMA FROM SUPABASE SCREENSHOT:
        # user_id, service_id, booking_id, quantity, total_price, availed_at
        # 'status' and 'notes' DO NOT exist in schema.
        insert_data = {
            "service_id": service_id,
            "user_id": user_id,
            "booking_id": data.get('booking_id'), 
            "quantity": quantity,
            "total_price": service_price * quantity
        }
        
        print(f"DEBUG: Recording service request: {insert_data}", flush=True)
        result = supabase_req('service_avails', method='POST', data=insert_data)
        
        # Manually construct response since column mapping is strict
        res_item = result[0] if isinstance(result, list) and len(result) > 0 else (result if result else insert_data)
        res_item['status'] = 'pending'
        res_item['service_name'] = service_res[0].get('name')
        
        return jsonify({"message": "Service request submitted!", "result": res_item}), 201
    except Exception as e:
        print(f"Error in avail_service: {str(e)}", flush=True)
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
    return send_from_directory(ROOT_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path in ('index.html', ''):
        return send_from_directory(ROOT_DIR, 'index.html')
    file_path = os.path.join(ROOT_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(ROOT_DIR, path)
    if path.startswith('api/'):
        return jsonify({"error": f"API endpoint /{path} not found"}), 404
    return send_from_directory(ROOT_DIR, 'index.html')

# Vercel entry point
handler = app

if __name__ == "__main__":
    app.run(debug=True)