"""API endpoints — missing logging and input validation."""


# BUG: No logging at all — impossible to debug in production
def handle_request(method: str, path: str, body: dict, user_db: dict) -> dict:
    """Route and handle an API request."""
    if path == "/users":
        if method == "GET":
            return {"status": 200, "data": list(user_db.values())}
        elif method == "POST":
            # BUG: No input validation — accepts anything
            username = body.get("username")
            email = body.get("email")
            user_db[username] = {"username": username, "email": email}
            return {"status": 201, "data": user_db[username]}
    elif path.startswith("/users/"):
        user_id = path.split("/")[-1]
        if method == "GET":
            user = user_db.get(user_id)
            if user:
                return {"status": 200, "data": user}
            return {"status": 404, "error": "Not found"}
        elif method == "DELETE":
            # BUG: No authorization check — anyone can delete any user
            if user_id in user_db:
                del user_db[user_id]
                return {"status": 204}
            return {"status": 404, "error": "Not found"}

    return {"status": 404, "error": "Unknown endpoint"}


def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
