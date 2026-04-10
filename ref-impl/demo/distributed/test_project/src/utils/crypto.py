"""Cryptographic utilities — shares token logic with auth.py."""
import hashlib
import secrets
import hmac


def hash_password(password: str) -> str:
    """Hash a password. BUG: Uses plain SHA-256 instead of bcrypt/argon2."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash. BUG: Not constant-time."""
    return hash_password(password) == stored_hash  # Should use hmac.compare_digest


def generate_token_id() -> str:
    """Generate a random token identifier."""
    return secrets.token_hex(16)


def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison (exists but unused!)."""
    return hmac.compare_digest(a.encode(), b.encode())
