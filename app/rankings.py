from .model import redis_client

def generate_rankings(game_id):
    true_prices = redis_client.hgetall(f"game:{game_id}:true_prices")
    players = redis_client.zrangebyscore(f"game:{game_id}:users", 0 , 0)

    for player_id in players:
        player_inv = redis_client.hgetall(f"user:{player_id}:inventory")
        score = 0
        for sec_id in player_inv:
            score += float(true_prices[sec_id]) * float(player_inv[sec_id])
        redis_client.zadd(f"game:{game_id}:users", {str(player_id): score})
    return redis_client.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)
