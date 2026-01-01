from ..services import *
import random, binascii, secrets, string


def generate_code(length=6):
    """Generate a random alphanumeric game code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def generate_token(prefix, length=32):
    """Generate a random token."""
    return prefix + binascii.hexlify(secrets.token_bytes(length)).decode("utf-8")


def verify_token(token: str, auth_type: str) -> str | None:
    """
    Returns player object if user_type is player otherwise game object if user_type is admin
    """
    token_components = token.split("-")
    try:
        if auth_type != token_components[0] or len(token_components) != 3:
            return None
        elif auth_type == "player":
            auth_id = token_components[1]
            auth_token = extract(r.hget("player_tokens", auth_id))
        elif auth_type == "admin":
            auth_id = token_components[1]
            auth_token = extract(r.hget(f"admin_tokens", auth_id))
        else:
            return None

        return auth_id if token == auth_token else None
    except Exception as e:
        print("Authentication error:", e)
        return None
