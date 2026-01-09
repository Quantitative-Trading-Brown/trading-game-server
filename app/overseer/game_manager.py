from app.services import *
from . import tokens


def create_game():
    game_codes = extract(r.hgetall("codes"))

    code = tokens.generate_code()
    # Check if game code exists
    while code in game_codes:
        code = tokens.generate_code()

    game_id = str(r.incr("game_count"))
    admin_token = tokens.generate_token(prefix=f"admin-{game_id}-")

    r.hset("codes", code, game_id)
    r.hset(f"admin_tokens", game_id, admin_token)

    r.hset(f"game:{game_id}", "code", code)
    r.hset(f"game:{game_id}", "state", "0")

    return game_id, code, admin_token


def join_game(data):
    game_codes = extract(r.hgetall("codes"))

    if not data:
        return False, "Invalid Request"

    code = data.get("code")
    username = data.get("playerName")

    # Check if game exists
    game_id = game_codes.get(code)

    if game_id is None:
        return False, "Game not found"

    # Check if username is empty
    if not username:
        return False, "Username cannot be empty"

    # Check if player name exists
    player_ids = extract(r.smembers(f"game:{game_id}:players"))

    usernames = [r.hget(f"player:{player_id}", "username") for player_id in player_ids]

    if username in usernames:
        return False, "Player name taken"

    player_id = r.incr("player_count")
    player_token = tokens.generate_token(prefix=f"player-{player_id}-")

    r.hset(f"player:{player_id}", "username", username)
    r.hset(f"player:{player_id}", "game_id", game_id)
    r.hset(f"player_tokens", str(player_id), player_token)
    r.sadd(f"game:{game_id}:players", str(player_id))
    r.set(
        f"player:{player_id}:inventory:cash",
        extract(r.hget(f"game:{game_id}", "initial_cash")),
    )

    return True, player_token
