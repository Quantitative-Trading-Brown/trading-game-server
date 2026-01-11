from app.services import *
from app.state.states import get_state
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
    validated, message = validate_join(data)
    if not validated:
        return False, message

    player_token = add_player(message, data.get("playerName"))

    return True, player_token


def add_player(game_id, username):
    player_id = r.incr("player_count")
    player_token = tokens.generate_token(prefix=f"player-{player_id}-")

    player_info = {
        "username": username,
        "game_id": game_id,
        "warning_ticks": 0,
        "bankruptcies": 0,
        "active": 1,
        "score": 0,
    }
    r.hset(f"player:{player_id}", mapping=player_info)

    r.hset(f"player_tokens", str(player_id), player_token)

    r.sadd(f"game:{game_id}:players", str(player_id))
    r.sadd(f"game:{game_id}:active_players", str(player_id))

    r.set(f"player:{player_id}:inventory:position_value", "0")
    r.set(f"player:{player_id}:inventory:margin", "0")

    if get_state(game_id) == 1:
        # If game is live, initialize player inventory with initial cash
        r.set(
            f"player:{player_id}:inventory:cash",
            extract(r.hget(f"game:{game_id}", "initial_cash")),
        )

    return player_token


def validate_join(data):
    if not data:
        return False, "Invalid Request"

    code = data.get("code")
    username = data.get("playerName")

    if not code or not username:
        return False, "Missing required fields"

    game_codes = extract(r.hgetall("codes"))
    game_id = game_codes.get(code)

    # Check if game exists
    if game_id is None:
        return False, "Game not found"

    # Check if joining is allowed
    join_allowed = int(extract(r.hget(f"game:{game_id}", "allow_join")) or 1)
    if get_state(game_id) != 0 and join_allowed != 1:
        return False, "Game in progress. Joining not allowed."

    # Check if player name exists
    player_ids = extract(r.smembers(f"game:{game_id}:players"))
    usernames = [r.hget(f"player:{player_id}", "username") for player_id in player_ids]
    if username in usernames:
        return False, "Player name taken"

    return True, game_id
