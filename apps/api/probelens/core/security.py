from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from probelens.config import get_settings

SESSION_COOKIE = "orbit_session"
ALGORITHM = "HS256"

def _pw_bytes(password: str) -> bytes:
    return password.encode()[:72]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt(rounds=10)).decode()

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode())
    except ValueError:
        return False

def create_session_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

def decode_session_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return int(sub) if sub and str(sub).isdigit() else None
