from app.services import *


def mark_player_positions(
    game_id: str,
    player_id: str,
    prices: dict[str, float] = {},
) -> None:
    inventory = extract(r.hgetall(f"player:{player_id}:inventory"))

    position_value = 0.0
    margin = 0.0

    for sec_id, price in prices.items():
        amount = int(inventory.get(sec_id, 0))
        current_price = float(price)

        position_value += amount * current_price

        margin_req = extract(
            r.hget(
                f"game:{game_id}:security:{sec_id}",
                "long_margin" if amount >= 0 else "short_margin",
            )
        )

        margin_req = float(margin_req) if margin_req is not None else 0.0

        margin += abs(amount * current_price) * margin_req

    r.set(f"player:{player_id}:inventory:position_value", position_value)
    r.set(f"player:{player_id}:inventory:margin", margin)


def mark_all_positions(game_id):
    players = extract(r.smembers(f"game:{game_id}:players"))
    prices = extract(r.hgetall(f"game:{game_id}:securities:prices"))

    for player_id in players:
        mark_player_positions(
            game_id,
            player_id,
            prices=prices,
        )
