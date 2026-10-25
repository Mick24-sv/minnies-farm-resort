"""
routes/bookings.py
GET    /api/bookings        – guest: own bookings | staff: all bookings
GET    /api/bookings/<id>   – get single booking
POST   /api/bookings        – create booking (guests only)
PUT    /api/bookings/<id>   – update dates   (guest owner only)
DELETE /api/bookings/<id>   – cancel/delete booking (guest owner or staff)
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import date, datetime
from .. import supabase_client
import random, string

bookings_bp = Blueprint("bookings", __name__)

RESORT_FEE_RATE = 0.10   # 10 % resort fee


def _generate_ref():
    chars = string.ascii_uppercase + string.digits
    return "MFR-" + "".join(random.choices(chars, k=6))


def _calc_nights(ci, co):
    if isinstance(ci, str):
        ci = date.fromisoformat(ci)
    if isinstance(co, str):
        co = date.fromisoformat(co)
    return (co - ci).days


def _check_conflict(room_id, ci, co, exclude_booking_id=None):
    conflicts = supabase_client.check_booking_conflict(room_id, ci, co, exclude_booking_id)
    return conflicts and len(conflicts) > 0


# ── GET BOOKINGS ──────────────────────────────────────────────────────────────
@bookings_bp.route("", methods=["GET"])
@jwt_required()
def get_bookings():
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "User not found."}), 404

    if user.get("role") == "staff":
        bookings = supabase_client.get_bookings() or []
    else:
        bookings = supabase_client.get_bookings_by_user(user_id) or []

    return jsonify({"bookings": bookings}), 200


# ── GET SINGLE BOOKING ────────────────────────────────────────────────────────
@bookings_bp.route("/<booking_id>", methods=["GET"])
@jwt_required()
def get_booking(booking_id):
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)
    booking = supabase_client.get_booking_by_id(booking_id)

    if not user:
        return jsonify({"error": "User not found."}), 404
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    if user.get("role") == "guest" and booking.get("user_id") != int(user_id):
        return jsonify({"error": "Access denied."}), 403

    return jsonify({"booking": booking}), 200


# ── CREATE BOOKING (guests only) ──────────────────────────────────────────────
@bookings_bp.route("", methods=["POST"])
@jwt_required()
def create_booking():
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.get("role") != "guest":
        return jsonify({"error": "Only guests can make bookings."}), 403

    data = request.get_json()
    required = ["room_id", "check_in_date", "check_out_date", "num_guests"]
    for field in required:
        if data.get(field) is None:
            return jsonify({"error": f"'{field}' is required."}), 400

    try:
        ci = date.fromisoformat(data["check_in_date"])
        co = date.fromisoformat(data["check_out_date"])
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if ci < date.today():
        return jsonify({"error": "check_in_date cannot be in the past."}), 400
    if co <= ci:
        return jsonify({"error": "check_out_date must be after check_in_date."}), 400

    room = supabase_client.get_room_by_id(data["room_id"])
    if not room:
        return jsonify({"error": "Room not found."}), 404

    if int(data["num_guests"]) > room.get("capacity", 0):
        return jsonify({"error": f"Room capacity is {room.get('capacity')} guests max."}), 400

    if _check_conflict(room.get("id"), data["check_in_date"], data["check_out_date"]):
        return jsonify({"error": "Room is already booked for the selected dates."}), 409

    nights = _calc_nights(ci, co)
    subtotal = float(room.get("price_per_night", 0)) * nights
    resort_fee = round(subtotal * RESORT_FEE_RATE, 2)
    total_price = round(subtotal + resort_fee, 2)

    ref = _generate_ref()

    booking_data = {
        "user_id": int(user_id),
        "room_id": room.get("id"),
        "check_in_date": data["check_in_date"],
        "check_out_date": data["check_out_date"],
        "num_guests": int(data["num_guests"]),
        "total_price": total_price,
        "status": "confirmed",
        "reference_code": ref,
    }

    result = supabase_client.create_booking(booking_data)

    return jsonify({
        "message": "Booking confirmed!",
        "booking": result[0] if result else booking_data,
    }), 201


# ── UPDATE BOOKING (change dates) ─────────────────────────────────────────────
@bookings_bp.route("/<booking_id>", methods=["PUT"])
@jwt_required()
def update_booking(booking_id):
    user_id = get_jwt_identity()
    booking = supabase_client.get_booking_by_id(booking_id)

    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    if booking.get("user_id") != int(user_id):
        return jsonify({"error": "You can only modify your own bookings."}), 403
    if booking.get("status") != "confirmed":
        return jsonify({"error": "Only confirmed bookings can be modified."}), 400

    data = request.get_json()

    try:
        ci = date.fromisoformat(data.get("check_in_date", booking.get("check_in_date")))
        co = date.fromisoformat(data.get("check_out_date", booking.get("check_out_date")))
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if ci < date.today():
        return jsonify({"error": "check_in_date cannot be in the past."}), 400
    if co <= ci:
        return jsonify({"error": "check_out_date must be after check_in_date."}), 400

    ci_str = ci.isoformat() if isinstance(ci, date) else str(ci)
    co_str = co.isoformat() if isinstance(co, date) else str(co)

    if _check_conflict(booking.get("room_id"), ci_str, co_str, exclude_booking_id=booking_id):
        return jsonify({"error": "Room is already booked for those dates."}), 409

    room = supabase_client.get_room_by_id(booking.get("room_id"))
    nights = _calc_nights(ci, co)
    subtotal = float(room.get("price_per_night", 0)) * nights
    resort_fee = round(subtotal * RESORT_FEE_RATE, 2)

    update_data = {
        "check_in_date": ci_str,
        "check_out_date": co_str,
        "num_guests": data.get("num_guests", booking.get("num_guests")),
        "total_price": round(subtotal + resort_fee, 2)
    }

    result = supabase_client.update_booking(booking_id, update_data)

    return jsonify({"message": "Booking updated successfully!", "booking": result[0] if result else update_data}), 200


# ── DELETE / CANCEL BOOKING ───────────────────────────────────────────────────
@bookings_bp.route("/<booking_id>", methods=["DELETE"])
@jwt_required()
def cancel_booking(booking_id):
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)
    booking = supabase_client.get_booking_by_id(booking_id)

    if not user:
        return jsonify({"error": "User not found."}), 404
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    if user.get("role") == "staff":
        # Staff: hard-delete the booking record entirely
        # Also delete any associated review first (foreign key)
        review = supabase_client.get_review_by_booking(booking_id)
        if review:
            supabase_client.supabase_request(f'reviews?id=eq.{review.get("id")}', method='DELETE')
        supabase_client.delete_booking(booking_id)
        return jsonify({"message": "Booking deleted successfully."}), 200
    else:
        # Guest: can only cancel their own, and only if not already done
        if booking.get("user_id") != int(user_id):
            return jsonify({"error": "You can only cancel your own bookings."}), 403
        if booking.get("status") in ("cancelled", "completed"):
            return jsonify({"error": f"Booking is already {booking.get('status')}."}), 400
        update_data = {"status": "cancelled"}
        result = supabase_client.update_booking(booking_id, update_data)
        return jsonify({"message": "Booking cancelled successfully.", "booking": result[0] if result else update_data}), 200


# ── UPDATE BOOKING STATUS (staff only) ───────────────────────────────────────
@bookings_bp.route("/<booking_id>/status", methods=["PUT"])
@jwt_required()
def update_booking_status(booking_id):
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.get("role") != "staff":
        return jsonify({"error": "Only staff can update booking status."}), 403

    data = request.get_json()
    status = data.get("status")

    if status not in ("pending", "confirmed", "cancelled", "completed"):
        return jsonify({"error": "Invalid status."}), 400

    booking = supabase_client.get_booking_by_id(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    result = supabase_client.update_booking(booking_id, {"status": status})

    return jsonify({"message": "Status updated!", "booking": result[0] if result else {"status": status}}), 200