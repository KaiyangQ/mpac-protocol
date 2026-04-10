"""Authentication module — has several known bugs for testing."""
import hashlib
import time


# BUG: Tokens are never checked for expiry
def validate_token(token: str) -> dict:
    """Validate a bearer token and return user info."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")

    header, payload, signature = parts

    expected_sig = hashlib.sha256(f"{header}.{payload}".encode()).hexdigest()[:16]
    if signature != expected_sig:
        raise ValueError("Invalid signature")

    # BUG: We decode payload but NEVER check if token is expired!
    import json, base64
    data = json.loads(base64.b64decode(payload + "=="))
    return data  # Should check data['exp'] < time.time()


# BUG: Timing side-channel — early return reveals if username exists
def authenticate(username: str, password: str, user_db: dict) -> bool:
    """Authenticate user against database."""
    if username not in user_db:
        return False  # BUG: immediate return leaks username existence

    stored_hash = user_db[username]["password_hash"]
    input_hash = hashlib.sha256(password.encode()).hexdigest()

    return stored_hash == input_hash  # BUG: not constant-time comparison


def create_token(user_id: str, username: str, ttl_seconds: int = 3600) -> str:
    """Create a new bearer token."""
    import json, base64
    header = base64.b64encode(json.dumps({"alg": "sha256"}).encode()).decode().rstrip("=")
    payload = base64.b64encode(json.dumps({
        "user_id": user_id, "username": username,
        "exp": int(time.time()) + ttl_seconds,
    }).encode()).decode().rstrip("=")
    signature = hashlib.sha256(f"{header}.{payload}".encode()).hexdigest()[:16]
    return f"{header}.{payload}.{signature}"
