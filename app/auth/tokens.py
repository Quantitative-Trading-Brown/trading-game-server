from ..services import *
import random, binascii, secrets, string
from typing import Optional
import hmac


def generate_code(length=6):
    """Generate a random alphanumeric game code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def generate_token(prefix, length=32):
    """Generate a random token."""
    return prefix + binascii.hexlify(secrets.token_bytes(length)).decode("utf-8")


def verify_token(token: str, auth_type: str) -> Optional[str]:
    """
    Returns player_id if user_type is player otherwise admin_id if user_type is admin
    Returns None if token is invalid
    """
    token_components = token.split("-")

    if len(token_components) != 3:
        return None

    prefix, auth_id, token_value = token_components

    if auth_type != prefix:
        return None

    try:
        key_name = f"{auth_type}_tokens"
        stored_token = extract(r.hget(key_name, auth_id))

        if hmac.compare_digest(token, stored_token):
            return auth_id
        return None

    except Exception:
        return None
