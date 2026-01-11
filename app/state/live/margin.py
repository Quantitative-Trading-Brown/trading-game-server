from app.services import *
from app.exchange import entry
from .bankruptcy import handle_bankruptcy


def check_margin(game_id: str):
    active_players = extract(r.smembers(f"game:{game_id}:active_players"))

    prices = r.hgetall(f"game:{game_id}:securities:prices")

    for player_id in active_players:
        if equity_violation(game_id, player_id):
            warning_ticks = int(
                extract(r.hincrby(f"player:{player_id}", "warning_ticks"))
            )
            if warning_ticks >= 3:
                execute_margin_call(game_id, player_id)
        else:
            r.hset(f"player:{player_id}", "warning_ticks", "0")


def equity_violation(game_id, player_id):
    cash = float(extract(r.get(f"player:{player_id}:inventory:cash")) or 0.0)
    position_value = float(
        extract(r.get(f"player:{player_id}:inventory:position_value")) or 0.0
    )
    margin = float(extract(r.get(f"player:{player_id}:inventory:margin")) or 0.0)

    equity = cash + position_value
    return equity < margin


def liquidate_player(game_id: str, player_id: str):
    inventory = extract(r.hgetall(f"player:{player_id}:inventory"))

    for sec_id, amount in inventory.items():
        qty = int(extract(amount) or 0)
        if qty == 0:
            continue

        side = "ask" if qty > 0 else "bid"
        exc_qty = abs(qty)

        entry.process_market_order(game_id, player_id, sec_id, side, exc_qty)


def execute_margin_call(game_id: str, player_id: str):
    liquidate_player(game_id, player_id)

    if equity_violation(game_id, player_id):
        handle_bankruptcy(game_id, player_id)
    else:
        socketio.emit(
            "margin_call",
            namespace="/player",
            to=r.hget(f"player:{player_id}", "sid"),
        )

    r.hset(f"player:{player_id}", "warning_ticks", "0")
