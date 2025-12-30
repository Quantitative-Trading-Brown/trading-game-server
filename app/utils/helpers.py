import json

from .services import socketio, r, extract

def identify(request_sid: str) -> tuple[str, str]:
    """Compute the game_id and player_id based on request_sid"""
    if player_id := extract(r.hget("socket_users", request_sid)):
        game_id = extract(r.hget(f"user:{player_id}", "game_id"))
        return game_id, player_id
    elif game_id := extract(r.hget("socket_admins", request_sid)):
        return game_id, "admin"
    else:
        raise RuntimeError("No associated game or player found for SID.")

def set_state(game_id: str, state: int) -> None:
    # Update in Redis backend
    r.set(f"game:{game_id}:state", state)

    # Notify all clients about the state change
    socketio.emit("gamestate_update", state, namespace="/admin", to=game_id)
    socketio.emit("gamestate_update", state, namespace="/player", to=game_id)

def generate_rankings(game_id: str) -> None:
    # Calculate player scores based on true prices and inventories
    true_prices = extract(r.hgetall(f"game:{game_id}:true_prices"))
    players = extract(r.zrangebyscore(f"game:{game_id}:users", 0, 0))

    for player_id in players:
        player_inv = extract(r.hgetall(f"user:{player_id}:inventory"))

        score = 0
        for sec_id in player_inv:
            score += float(true_prices[sec_id]) * float(player_inv[sec_id])
        r.zadd(f"game:{game_id}:users", {str(player_id): round(score, 2)})

def flush_orderbook(game_id: str) -> None:
    with r.lock("everything"):
        securities = extract(r.smembers(f"game:{game_id}:securities"))

        total_update = {}
        for security in securities:
            ob_key = f"game:{game_id}:security:{security}:orderbook:updates"
            orderbook_items = extract(r.lrange(ob_key, 0, -1))

            if orderbook_items:
                orderbook_update_queue = [json.loads(x) for x in orderbook_items]
                combined = {k: v for d in orderbook_update_queue for k, v in d.items()}
                total_update[security] = combined
                r.delete(ob_key)

        # Emit combined orderbook updates
        socketio.emit(
            "orderbook", total_update, namespace="/player", to=game_id
        )
        socketio.emit(
            "orderbook", total_update, namespace="/admin", to=game_id
        )

def make_snapshot(game_id, player_id=None):
    securities = extract(r.smembers(f"game:{game_id}:securities"))

    orderbooks = {
        sec_id: r.hgetall(f"game:{game_id}:security:{sec_id}:orderbook")
        for sec_id in securities
    }
    security_props = {
        sec_id: r.hgetall(f"game:{game_id}:security:{sec_id}") for sec_id in securities
    }

    raw_news = extract(r.lrange(f"game:{game_id}:news", 0, 19))

    past_news = [
        [json.loads(raw)["timestamp"], json.loads(raw)["message"]]
        for raw in reversed(raw_news)
    ]

    snapshot = {
        "game_state": r.get(f"game:{game_id}:state"),
        "game_props": r.hgetall(f"game:{game_id}"),
        "securities": security_props,
        "orderbooks": orderbooks,
        "past_news": past_news,
    }

    if player_id:
        orders = extract(r.smembers(f"user:{player_id}:orders"))

        snapshot["username"] = r.hget(f"user:{player_id}", "username")
        snapshot["inventory"] = r.hgetall(f"user:{player_id}:inventory")
        snapshot["orders"] = {o: r.hgetall(f"game:{game_id}:order:{o}") for o in orders}

    return snapshot

def verify_token(token, auth_type):
    """
    Returns player object if user_type is player otherwise game object if user_type is admin
    """
    token_components = token.split("-")
    try:
        if auth_type != token_components[0] or len(token_components) != 3:
            return None
        elif auth_type == "player":
            auth_id = int(token_components[1])
            auth_token = extract(r.hget("player_tokens", str(auth_id)))
        elif auth_type == "admin":
            auth_id = int(token_components[1])
            auth_token = extract(r.hget(f"admin_tokens", str(auth_id)))
        else:
            return None

        return auth_id if token == auth_token else None
    except Exception as e:
        print("Authentication error:", e)
        return None
