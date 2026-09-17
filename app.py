import os
import sys
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv

# Create app first so health check is available immediately
app = Flask(__name__)

# HEALTH CHECK - This should always work
@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "message": "Root app is alive",
        "env_check": {
            "supabase_url": bool(os.getenv('SUPABASE_URL')),
            "supabase_key": bool(os.getenv('SUPABASE_KEY'))
        }
    })

# Add api directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

# Load environment
if not os.getenv('VERCEL'):
    load_dotenv()

def initialize_app(app):
    # Config
    _jwt_secret = os.getenv("JWT_SECRET_KEY")
    if not _jwt_secret:
        raise RuntimeError("JWT_SECRET_KEY environment variable is required")
    app.config["JWT_SECRET_KEY"] = _jwt_secret
    
    # Skip filesystem operations completely on Vercel (read-only filesystem)
    if not os.getenv('VERCEL'):
        try:
            app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "uploads")
            if not os.path.exists(app.config["UPLOAD_FOLDER"]):
                os.makedirs(app.config["UPLOAD_FOLDER"])
        except Exception as e:
            print(f"Upload folder setup failed: {e}")
            app.config["UPLOAD_FOLDER"] = "/tmp"

    # Initialize extensions safely
    try:
        from api.extensions import bcrypt
        bcrypt.init_app(app)
    except Exception as e:
        print(f"Extension error: {e}")

    JWTManager(app)
    CORS(app, supports_credentials=True)

    # Register blueprints safely
    try:
        from api.routes.auth import auth_bp
        from api.routes.rooms import rooms_bp
        from api.routes.bookings import bookings_bp
        from api.routes.services import services_bp
        from api.routes.reviews import reviews_bp

        app.register_blueprint(auth_bp, url_prefix="/api/auth")
        app.register_blueprint(rooms_bp, url_prefix="/api/rooms")
        app.register_blueprint(bookings_bp, url_prefix="/api/bookings")
        app.register_blueprint(services_bp, url_prefix="/api/services")
        app.register_blueprint(reviews_bp, url_prefix="/api/reviews")
    except Exception as e:
        print(f"Blueprint error: {e}")

initialize_app(app)
handler = app

if __name__ == "__main__":
    app.run(debug=True, port=5000)