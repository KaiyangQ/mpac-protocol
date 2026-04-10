"""Utility functions — has performance and security issues."""
import hashlib
import hmac


def hash_password(password: str) -> str:
    """Hash a password. BUG: No salt — vulnerable to rainbow tables."""
    return hashlib.sha256(password.encode()).hexdigest()


# BUG: This constant_time_compare exists but auth.py uses == instead
def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())


def sanitize_input(value: str) -> str:
    """Sanitize user input. BUG: Only strips whitespace, doesn't escape HTML."""
    return value.strip()


# BUG: Inefficient — reads entire file into memory for large files
def count_lines(filepath: str) -> int:
    """Count lines in a file."""
    with open(filepath, "r") as f:
        return len(f.readlines())  # Should use sum(1 for _ in f) for large files
