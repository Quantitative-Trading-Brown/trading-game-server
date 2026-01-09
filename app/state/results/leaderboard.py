from app.services import *


def get_leaderboard(game_id):
    # Return the leaderboard for the game
    results = [
        (
            extract(r.hget(f"player:{player_id}", "username")),
            extract(r.hget(f"player:{player_id}", "score")),
        )
        for player_id in extract(r.smembers(f"game:{game_id}:players"))
    ]

    leaderboard = sorted(results, key=lambda x: x[1], reverse=True)

    named_rankings = [
        (extract(r.hget(f"player:{player_id}", "username")), score)
        for player_id, score in results
    ]
    return named_rankings
