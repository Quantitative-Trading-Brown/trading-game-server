import json

from ..services import *


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
