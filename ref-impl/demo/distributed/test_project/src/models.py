"""SQLAlchemy models — User model is incomplete."""


class User:
    """User model — missing email uniqueness and proper validation."""

    def __init__(self, user_id: str, username: str, email: str, password_hash: str):
        self.user_id = user_id
        self.username = username
        self.email = email  # BUG: No uniqueness constraint
        self.password_hash = password_hash
        # BUG: Missing created_at, updated_at, is_active, last_login fields

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
        }


class Session:
    """Session model."""

    def __init__(self, session_id: str, user_id: str, token: str):
        self.session_id = session_id
        self.user_id = user_id
        self.token = token
        self.is_active = True

    def invalidate(self):
        self.is_active = False
