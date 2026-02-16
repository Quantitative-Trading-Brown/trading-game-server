from app.services import *


def calculate_scores(game_id: str, true_prices: dict) -> None:
    players = extract(r.smembers(f"game:{game_id}:players"))
    buy_liquidation_fraction = float(
        extract(r.hget(f"game:{game_id}", "buy_liquidation_fraction"))
    )
    sell_liquidation_fraction = float(
        extract(r.hget(f"game:{game_id}", "sell_liquidation_fraction"))
    )

    for player_id in players:
        player_inv = extract(r.hgetall(f"player:{player_id}:inventory"))

        score = 0
        for sec_id in player_inv:
            amount = float(player_inv[sec_id])
            if amount > 0:
                score += sell_liquidation_fraction * float(true_prices[sec_id]) * amount
            else:
                score += buy_liquidation_fraction * float(true_prices[sec_id]) * amount

        score += float(extract(r.get(f"player:{player_id}:inventory:cash")))

        r.hset(f"player:{player_id}", "score", round(score, 2))
