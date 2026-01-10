from app.services import *


def calculate_scores(game_id: str, true_prices: dict) -> None:
    players = extract(r.smembers(f"game:{game_id}:players"))

    for player_id in players:
        player_inv = extract(r.hgetall(f"player:{player_id}:inventory"))

        score = 0
        for sec_id in player_inv:
            score += float(true_prices[sec_id]) * float(player_inv[sec_id])

        score += float(extract(r.get(f"player:{player_id}:inventory:cash")))

        r.hset(f"player:{player_id}", "score", round(score, 2))
