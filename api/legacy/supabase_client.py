"""
Supabase REST API Client for database operations
Uses HTTP requests instead of direct PostgreSQL connection
"""
import os
import urllib.request
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

def get_headers():
    """Get Supabase API headers"""
    if not SUPABASE_KEY:
        logger.error("SUPABASE_KEY is missing from environment!")
    return {
        'apikey': SUPABASE_KEY or "",
        'Authorization': f'Bearer {SUPABASE_KEY}' if SUPABASE_KEY else "",
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def supabase_request(endpoint, method='GET', data=None, params=None):
    """Make a request to Supabase REST API"""
    if not SUPABASE_URL:
        logger.error("Cannot make request: SUPABASE_URL is not set")
        return None
        
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{endpoint}"
    
    if params:
        query = '&'.join([f"{k}={v}" for k, v in params.items()])
        url = f"{url}&{query}" if '?' in url else f"{url}?{query}"
    
    headers = get_headers()
    req_data = json.dumps(data).encode('utf-8') if data else None
    
    logger.info(f"Supabase Request: {method} {url}")
    
    req = urllib.request.Request(
        url,
        data=req_data,
        headers=headers,
        method=method
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 204:
                return None
            res_body = response.read().decode('utf-8')
            return json.loads(res_body) if res_body else None
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8')
        logger.error(f"Supabase HTTP Error {e.code}: {error_msg}")
        if e.code == 404:
            return None
        if e.code == 409:
            return None
        raise Exception(f"Supabase API Error: {error_msg}")
    except Exception as e:
        logger.error(f"Supabase Request failed: {str(e)}")
        raise

# User operations
def get_users():
    return supabase_request('users?select=*')

def get_user_by_email(email):
    result = supabase_request(f'users?email=eq.{email}&select=*')
    return result[0] if result else None

def get_user_by_id(user_id):
    result = supabase_request(f'users?id=eq.{user_id}&select=*')
    return result[0] if result else None

def create_user(user_data):
    return supabase_request('users', method='POST', data=user_data)

def update_user(user_id, user_data):
    return supabase_request(f'users?id=eq.{user_id}', method='PATCH', data=user_data)

# Room operations
def get_rooms():
    return supabase_request('rooms?select=*')

def get_room_by_id(room_id):
    result = supabase_request(f'rooms?id=eq.{room_id}&select=*')
    return result[0] if result else None

def create_room(room_data):
    return supabase_request('rooms', method='POST', data=room_data)

def update_room(room_id, room_data):
    return supabase_request(f'rooms?id=eq.{room_id}', method='PATCH', data=room_data)

def delete_room(room_id):
    return supabase_request(f'rooms?id=eq.{room_id}', method='DELETE')

# Service operations
def get_services():
    return supabase_request('services?select=*')

def get_service_by_id(service_id):
    result = supabase_request(f'services?id=eq.{service_id}&select=*')
    return result[0] if result else None

def create_service(service_data):
    return supabase_request('services', method='POST', data=service_data)

def update_service(service_id, service_data):
    return supabase_request(f'services?id=eq.{service_id}', method='PATCH', data=service_data)

def delete_service(service_id):
    return supabase_request(f'services?id=eq.{service_id}', method='DELETE')

# Booking operations
def get_bookings():
    return supabase_request('bookings?select=*')

def get_bookings_by_user(user_id):
    return supabase_request(f'bookings?user_id=eq.{user_id}&select=*')

def get_booking_by_id(booking_id):
    result = supabase_request(f'bookings?id=eq.{booking_id}&select=*')
    return result[0] if result else None

def create_booking(booking_data):
    return supabase_request('bookings', method='POST', data=booking_data)

def update_booking(booking_id, booking_data):
    return supabase_request(f'bookings?id=eq.{booking_id}', method='PATCH', data=booking_data)

def delete_booking(booking_id):
    return supabase_request(f'bookings?id=eq.{booking_id}', method='DELETE')

def check_booking_conflict(room_id, check_in, check_out, exclude_id=None):
    """Check if there are conflicting bookings for a room"""
    query = f'bookings?room_id=eq.{room_id}&status=in.(confirmed,pending)&check_in_date=lt.{check_out}&check_out_date=gt.{check_in}&select=*'
    if exclude_id:
        query += f'&id=neq.{exclude_id}'
    return supabase_request(query)

# Review operations
def get_reviews_by_room(room_id):
    return supabase_request(f'reviews?room_id=eq.{room_id}&select=*&order=created_at.desc')

def get_review_by_id(review_id):
    result = supabase_request(f'reviews?id=eq.{review_id}&select=*')
    return result[0] if result else None

def get_review_by_booking(booking_id):
    result = supabase_request(f'reviews?booking_id=eq.{booking_id}&select=*')
    return result[0] if result else None

def create_review(review_data):
    return supabase_request('reviews', method='POST', data=review_data)

# Service Avail operations
def get_service_avails():
    return supabase_request('service_avails?select=*&order=created_at.desc')

def get_service_avails_by_user(user_id):
    return supabase_request(f'service_avails?user_id=eq.{user_id}&select=*&order=created_at.desc')

def get_service_avail_by_id(avail_id):
    result = supabase_request(f'service_avails?id=eq.{avail_id}&select=*')
    return result[0] if result else None

def create_service_avail(avail_data):
    return supabase_request('service_avails', method='POST', data=avail_data)

def update_service_avail(avail_id, avail_data):
    return supabase_request(f'service_avails?id=eq.{avail_id}', method='PATCH', data=avail_data)

def delete_service_avail(avail_id):
    return supabase_request(f'service_avails?id=eq.{avail_id}', method='DELETE')
