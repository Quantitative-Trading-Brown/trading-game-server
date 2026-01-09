from app.services import *


def check_margin(game_id: str):
    players = extract(r.smembers(f"game:{game_id}:players"))

    prices = r.hgetall(f"game:{game_id}:securities:prices")

    for player_id in players:
        cash = float(extract(r.hget(f"player:{player_id}", "cash")) or 0.0)
        position_value = float(
            extract(r.get(f"player:{player_id}:inventory:position_value")) or 0.0
        )
        margin = float(
            extract(r.get(f"player:{player_id}:inventory:margin")) or 0.0
        )

        equity = cash + position_value

        if equity < margin:
            r.hincrby(f"player:{player_id}", "warning_ticks")
        else:
            r.hset(f"player:{player_id}", "warning_ticks", "0")
