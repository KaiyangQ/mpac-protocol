"""User API endpoints — has N+1 query problem."""


def get_users(user_db: dict) -> list:
    """Get all users. BUG: N+1 query pattern — loads each user separately."""
    results = []
    for user_id in user_db:
        # Simulating N+1: each iteration is a separate "query"
        user = user_db[user_id]
        # Another "query" to get user's sessions
        sessions = _get_user_sessions(user_id)
        results.append({**user, "session_count": len(sessions)})
    return results


def _get_user_sessions(user_id: str) -> list:
    """Simulate fetching sessions for a user (separate query each time)."""
    # In real code this would be a DB call
    return []


def get_user_by_id(user_id: str, user_db: dict) -> dict:
    """Get a single user by ID."""
    if user_id not in user_db:
        raise KeyError(f"User {user_id} not found")
    return user_db[user_id]


def create_user(username: str, email: str, password: str, user_db: dict) -> dict:
    """Create a new user. BUG: No email uniqueness check."""
    import uuid
    from ..utils.crypto import hash_password

    user_id = str(uuid.uuid4())
    user_db[user_id] = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
    }
    return user_db[user_id]
