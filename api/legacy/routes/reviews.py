"""
routes/reviews.py
GET  /api/reviews?room_id=<id>  – fetch reviews + avg rating for a room
POST /api/reviews               – submit a review (JWT required)
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from .. import supabase_client

reviews_bp = Blueprint("reviews", __name__)


# ── GET REVIEWS FOR A ROOM ────────────────────────────────────────────────────
@reviews_bp.route("", methods=["GET"])
def get_reviews():
    room_id = request.args.get("room_id", type=int)
    if not room_id:
        return jsonify({"error": "room_id query parameter is required."}), 400

    reviews = supabase_client.get_reviews_by_room(room_id) or []

    total = len(reviews)
    average = round(sum(r.get("rating", 0) for r in reviews) / total, 1) if total else 0

    return jsonify({
        "reviews": reviews,
        "average_rating": average,
        "total_reviews": total,
    }), 200


# ── SUBMIT A REVIEW ───────────────────────────────────────────────────────────
@reviews_bp.route("", methods=["POST"])
@jwt_required()
def submit_review():
    user_id = get_jwt_identity()
    user = supabase_client.get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json()
    room_id = data.get("room_id")
    booking_id = data.get("booking_id")
    rating = data.get("rating")
    review_txt = data.get("review", "")

    # --- basic validation ---
    if not room_id or not booking_id or not rating:
        return jsonify({"error": "room_id, booking_id, and rating are required."}), 400

    if not isinstance(rating, int) or not (1 <= rating <= 5):
        return jsonify({"error": "rating must be an integer between 1 and 5."}), 400

    # --- verify the booking belongs to this user and is completed ---
    booking = supabase_client.get_booking_by_id(booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404
    if int(booking.get("user_id")) != int(user_id):
        return jsonify({"error": "You can only review your own bookings."}), 403
    if booking.get("room_id") != room_id:
        return jsonify({"error": "Booking does not match the specified room."}), 400
    if booking.get("status") != "completed":
        return jsonify({"error": "You can only review completed stays."}), 400

    # --- prevent duplicate reviews ---
    existing = supabase_client.get_review_by_booking(booking_id)
    if existing:
        return jsonify({"error": "You have already reviewed this booking."}), 409

    review_data = {
        "user_id": user_id,
        "room_id": room_id,
        "booking_id": booking_id,
        "rating": rating,
        "review": review_txt,
    }

    result = supabase_client.create_review(review_data)

    return jsonify({
        "message": "Review submitted successfully!",
        "review": result[0] if result else review_data,
    }), 201