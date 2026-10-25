"""
routes/services.py
GET  /api/services              – list all active services
GET  /api/services/<id>         – get single service
POST /api/services              – create service  (staff only)
PUT  /api/services/<id>         – update service  (staff only)
DELETE /api/services/<id>       – deactivate service (staff only)
POST /api/services/<id>/avail   – guest avails a service
GET  /api/services/avails       – get avail records (staff: all, guest: own)
PUT  /api/services/avails/<id>/status – update avail status (staff only)
DELETE /api/services/avails/<id> – delete avail record (staff only)
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from .. import supabase_client
from datetime import date

services_bp = Blueprint("services", __name__)


def require_staff():
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)
    if not user or user.get('role') != "staff":
        return None, (jsonify({"error": "Staff access required."}), 403)
    return user, None


# ── GET ALL SERVICES ──────────────────────────────────────────────────────────
@services_bp.route("", methods=["GET"])
def get_services():
    try:
        is_staff = False
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id:
                user = supabase_client.get_user_by_id(user_id)
                if user and user.get('role') == 'staff':
                    is_staff = True
        except Exception:
            pass

        all_services = supabase_client.get_services()
        if not is_staff:
            all_services = [s for s in all_services if s.get('is_active')]
            
        return jsonify({"services": all_services}), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET SINGLE SERVICE ────────────────────────────────────────────────────────
@services_bp.route("/<int:service_id>", methods=["GET"])
def get_service(service_id):
    service = supabase_client.get_service_by_id(service_id)
    if not service:
        return jsonify({"error": "Service not found"}), 404
    return jsonify({"service": service}), 200


# ── CREATE SERVICE (staff only) ───────────────────────────────────────────────
@services_bp.route("", methods=["POST"])
@jwt_required()
def create_service():
    _, err = require_staff()
    if err:
        return err

    data = request.get_json()
    if not data.get("name") or data.get("price") is None:
        return jsonify({"error": "'name' and 'price' are required."}), 400

    service_data = {
        "name": data["name"],
        "description": data.get("description", ""),
        "price": float(data["price"]),
        "category": data.get("category", "day_service"),
        "stock_quantity": int(data.get("stock_quantity", -1)),
        "is_active": data.get("is_active", True),
        "image_url": data.get("image_url") or None,
    }
    
    result = supabase_client.create_service(service_data)
    return jsonify({"message": "Service created!", "service": result}), 201


# ── UPDATE SERVICE (staff only) ───────────────────────────────────────────────
@services_bp.route("/<int:service_id>", methods=["PUT"])
@jwt_required()
def update_service(service_id):
    _, err = require_staff()
    if err:
        return err

    data = request.get_json()
    result = supabase_client.update_service(service_id, data)
    return jsonify({"message": "Service updated!", "service": result}), 200


# ── DEACTIVATE SERVICE (staff only) ───────────────────────────────────────────
@services_bp.route("/<int:service_id>", methods=["DELETE"])
@jwt_required()
def delete_service(service_id):
    _, err = require_staff()
    if err:
        return err

    data = {"is_active": False}
    supabase_client.update_service(service_id, data)
    return jsonify({"message": "Service deactivated."}), 200


# ── AVAIL A SERVICE ───────────────────────────────────────────────────────────
@services_bp.route("/<int:service_id>/avail", methods=["POST"])
def avail_service(service_id):
    """
    Guests can avail while logged in.
    Walk-in guests (no token) can also avail — user_id will be None.
    """
    service = supabase_client.get_service_by_id(service_id)
    if not service:
        return jsonify({"error": "Service not found"}), 404
    if not service.get('is_active'):
        return jsonify({"error": "This service is currently unavailable."}), 400

    data = request.get_json() or {}

    # Optionally get logged-in user
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        pass

    quantity   = int(data.get("quantity", 1))
    avail_date = data.get("avail_date", date.today().isoformat())

    try:
        # Validate date format
        date.fromisoformat(avail_date)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    total_price = float(service.get('price', 0)) * quantity

    avail_data = {
        "user_id": int(user_id) if user_id else None,
        "service_id": service_id,
        "quantity": quantity,
        "total_price": total_price,
        "avail_date": avail_date,
        "status": "confirmed",
    }

    result = supabase_client.create_service_avail(avail_data)

    return jsonify({
        "message": f"'{service.get('name')}' availed successfully!",
        "avail": result[0] if result else avail_data,
        "total_price": total_price,
    }), 201


# ── GET AVAIL RECORDS ─────────────────────────────────────────────────────────
@services_bp.route("/avails", methods=["GET"])
@jwt_required()
def get_avails():
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.get('role') == "staff":
        avails = supabase_client.get_service_avails() or []
    else:
        avails = supabase_client.get_service_avails_by_user(user_id) or []

    # Enrich with user and service names
    result = []
    for a in avails:
        d = dict(a)
        guest_id = a.get('user_id')
        if guest_id:
            guest = supabase_client.get_user_by_id(guest_id)
            d['guest_name'] = guest.get('name') if guest else 'Unknown'
        else:
            d['guest_name'] = 'Walk-in'

        service_id = a.get('service_id')
        if service_id:
            service = supabase_client.get_service_by_id(service_id)
            d['service_name'] = service.get('name') if service else 'Unknown'
        else:
            d['service_name'] = 'Unknown'
        result.append(d)

    return jsonify({"avails": result}), 200


# ── UPDATE AVAIL STATUS (staff only) ─────────────────────────────────────────────
@services_bp.route("/avails/<int:avail_id>/status", methods=["PUT"])
@jwt_required()
def update_avail_status(avail_id):
    _, err = require_staff()
    if err:
        return err

    avail = supabase_client.get_service_avail_by_id(avail_id)
    if not avail:
        return jsonify({"error": "Service avail not found"}), 404

    data = request.get_json()

    if not data or 'status' not in data:
        return jsonify({"error": "Status is required"}), 400

    valid_statuses = ['pending', 'confirmed', 'completed', 'cancelled']
    if data['status'] not in valid_statuses:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400

    result = supabase_client.update_service_avail(avail_id, {'status': data['status']})

    return jsonify({
        "message": "Service avail status updated successfully.",
        "avail": result[0] if result else {'status': data['status']}
    }), 200

# ── DELETE AVAIL RECORD (staff only) ─────────────────────────────────────────────
@services_bp.route("/avails/<int:avail_id>", methods=["DELETE"])
@jwt_required()
def delete_avail(avail_id):
    _, err = require_staff()
    if err:
        return err

    avail = supabase_client.get_service_avail_by_id(avail_id)
    if not avail:
        return jsonify({"error": "Service avail not found"}), 404

    supabase_client.delete_service_avail(avail_id)
    return jsonify({"message": "Service avail record deleted."}), 200
