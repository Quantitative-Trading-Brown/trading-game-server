from .model import redis_client

def generate_rankings(game_id):
    print(redis_client.hgetall("game:users"))
