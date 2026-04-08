"""Authentication middleware — DUPLICATES logic from auth.py (dangerous!)."""
import hashlib


# This entire module duplicates auth.py logic and is now out of sync.
# It should import from auth.py instead.

def check_request_auth(request_headers: dict, user_db: dict) -> dict:
    """Check if request is authenticated."""
    auth_header = request_headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return {"authenticated": False, "error": "Missing bearer token"}

    token = auth_header[7:]

    # DUPLICATED from auth.py — same bug: no expiry check
    parts = token.split(".")
    if len(parts) != 3:
        return {"authenticated": False, "error": "Invalid token format"}

    header, payload, signature = parts

    expected_sig = hashlib.sha256(f"{header}.{payload}".encode()).hexdigest()[:16]
    if signature != expected_sig:
        return {"authenticated": False, "error": "Invalid signature"}

    import json, base64
    data = json.loads(base64.b64decode(payload + "=="))

    # ALSO MISSING: no expiry check here either!
    return {"authenticated": True, "user": data}


def require_role(user_data: dict, required_role: str) -> bool:
    """Check if user has required role. STUB — always returns True."""
    return True  # BUG: No actual role checking
