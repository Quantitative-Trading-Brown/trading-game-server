from ..services import *

def identify(request_sid: str) -> tuple[str, str]:
    """Compute the game_id and player_id based on request_sid"""
    if player_id := r.hget("player_sockets", request_sid):
        game_id = r.hget(f"player:{player_id}", "game_id")
        return extract(game_id), extract(player_id)
    elif game_id := r.hget("admin_sockets", request_sid):
        return extract(game_id), "admin"
    else:
        raise RuntimeError("No associated game or player found for SID.")
