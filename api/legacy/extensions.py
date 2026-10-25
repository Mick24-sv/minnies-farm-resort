from flask_jwt_extended import JWTManager
from passlib.hash import pbkdf2_sha256

jwt = JWTManager()

class PasswordHasher:
    @staticmethod
    def generate_password_hash(password):
        return pbkdf2_sha256.hash(password)
    
    @staticmethod
    def check_password_hash(hash, password):
        try:
            return pbkdf2_sha256.verify(password, hash)
        except Exception:
            return False
    
    def init_app(self, app):
        pass

bcrypt = PasswordHasher()
