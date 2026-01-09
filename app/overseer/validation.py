from ..services import *
from typing import Optional
import hmac


# This acts as a soft auth check on the frontend to see if a redirect is necessary
def check_auth(data):
    if not data or "token" not in data:
        return None

    token = data["token"]

    verify_player = verify_token(token, "player")
    if verify_player is not None:
        return "player"

    verify_admin = verify_token(token, "admin")
    if verify_admin is not None:
        return "admin"

    return None


def verify_token(token: str, auth_type: str) -> Optional[str]:
    """
    Returns player_id if auth_tyep is player otherwise admin_id if auth_type is admin
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


def new_player_connection(request):
    # Extract token from the query parameters
    token = request.args.get("token")
    player_id = verify_token(token, "player")

    if player_id is None:
        return False
    else:
        r.hset("player_sockets", sid(request), player_id)
        r.hset(f"player:{player_id}", "sid", sid(request))

        game_id = extract(r.hget(f"player:{player_id}", "game_id"))
        return game_id


def new_admin_connection(request):
    token = request.args.get("token")
    game_id = verify_token(token, "admin")

    if game_id is None:
        return False
    else:
        r.hset("admin_sockets", sid(request), game_id)
        return game_id
