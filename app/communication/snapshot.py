import json

from app.services import *


def get_snapshot(game_id, player_id=None):
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
        "game_props": r.hgetall(f"game:{game_id}"),
        "securities": security_props,
        "orderbooks": orderbooks,
        "past_news": past_news,
    }

    if player_id is not None:
        oids = extract(r.smembers(f"player:{player_id}:orders"))

        snapshot["username"] = r.hget(f"player:{player_id}", "username")
        snapshot["inventory"] = r.hgetall(f"player:{player_id}:inventory")
        snapshot["cash"] = r.get(f"player:{player_id}:inventory:cash")
        snapshot["position_value"] = r.get(
            f"player:{player_id}:inventory:position_value"
        )
        snapshot["margin"] = r.get(f"player:{player_id}:inventory:margin")
        snapshot["orders"] = {
            oid: r.hgetall(f"game:{game_id}:order:{oid}") for oid in oids
        }
        snapshot["active"] = r.hget(f"player:{player_id}", "active")

    return snapshot
