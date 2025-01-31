from .model import redis_client

def generate_rankings(game_id, true_values):
    """
    true_values: dictionary containing true values of assets
    """
    players = redis_client.zrangebyscore(f"game:{game_id}:users", 0 , 0)
    for player_id in players:
        player_info = redis_client.hgetall(f"user:{player_id}:asset")
        score = sum(int(true_values[asset]) * int(player_info[asset]) for asset in player_info)
        redis_client.zadd(f"game:{game_id}:users", {str(player_id): score})
    return redis_client.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)
