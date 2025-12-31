from ..services import *

def calculate_scores(game_id: str) -> None:
    # Calculate player scores based on true prices and inventories
    true_prices = extract(r.hgetall(f"game:{game_id}:true_prices"))
    players = extract(r.zrangebyscore(f"game:{game_id}:users", 0, 0))

    for player_id in players:
        player_inv = extract(r.hgetall(f"user:{player_id}:inventory"))

        score = 0
        for sec_id in player_inv:
            score += float(true_prices[sec_id]) * float(player_inv[sec_id])
        r.zadd(f"game:{game_id}:users", {str(player_id): round(score, 2)})
