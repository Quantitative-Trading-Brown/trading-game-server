from .model import r

def generate_rankings(game_id):
    true_prices = r.hgetall(f"game:{game_id}:true_prices")
    players = r.zrangebyscore(f"game:{game_id}:users", 0 , 0)

    for player_id in players:
        player_inv = r.hgetall(f"user:{player_id}:inventory")
        score = 0
        for sec_id in player_inv:
            score += float(true_prices[sec_id]) * float(player_inv[sec_id])
        r.zadd(f"game:{game_id}:users", {str(player_id): round(score,2)})
    return r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)
