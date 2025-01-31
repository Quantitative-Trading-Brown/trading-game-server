from flask import Blueprint, request, jsonify
from .model import socketio, redis_client
from .model import GameStatus, Game, Player
from .rankings import generate_rankings

game = Blueprint('game', __name__)

@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    game_id = int(redis_client.hget("socket_admins", request.sid))

    snapshot = {
        "game_state": redis_client.get(f"game:{game_id}:state"),
        "game_props": redis_client.hgetall(f"game:{game_id}"),
        "orderbook": redis_client.hgetall(f"game:{game_id}:orderbook"),
    }

    socketio.emit("snapshot", snapshot, 
                  namespace="/admin", to=request.sid)

@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget(f"user:{player_id}", "game_id"))

    snapshot = {
        "username": redis_client.hget(f"user:{player_id}", "username"),
        "game_state": redis_client.get(f"game:{game_id}:state"),
        "game_props": redis_client.hgetall(f"game:{game_id}"),
        "orderbook": redis_client.hgetall(f"game:{game_id}:orderbook"),
    }

    socketio.emit("snapshot", snapshot, 
                  namespace="/player", to=request.sid)

@socketio.on("news", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients."""
    game_id = int(redis_client.hget("socket_admins", request.sid))
    socketio.emit("news", "[admin] " + message, 
                  namespace="/admin", to=game_id)
    socketio.emit("news", "[admin] " + message, 
                  namespace="/player", to=game_id)

# {{{ State Controller
def set_state(game_id, state):
    redis_client.set(f"game:{game_id}:state", state)

    socketio.emit("gamestate_update", state,
                  namespace="/admin", to=game_id)
    socketio.emit("gamestate_update", state, 
                  namespace="/player", to=game_id)

@socketio.on("startgame", namespace="/admin")
def startgame(settings={}):
    game_id = int(redis_client.hget("socket_admins", request.sid))
    for key in settings:
        redis_client.hset(f"game:{game_id}", key, settings[key])
    all_props = redis_client.hgetall(f"game:{game_id}")

    socketio.emit("gameprops_update", all_props,
                  namespace="/player", to=game_id)
    socketio.emit("gameprops_update", all_props, 
                  namespace="/admin", to=game_id)

    set_state(game_id, 1)

@socketio.on("endgame", namespace="/admin")
def endgame():
    game_id = int(redis_client.hget("socket_admins", request.sid))
    set_state(game_id, 2)

@socketio.on("rankgame", namespace="/admin")
def rankgame(true_prices={}):
    game_id = int(redis_client.hget("socket_admins", request.sid))

    for key in true_prices:
        redis_client.hset(f"game:{game_id}:true_prices", key, true_prices[key])
    redis_client.hset(f"game:{game_id}:true_prices", "cash", 1)

    generate_rankings(game_id, redis_client.hgetall(f"game:{game_id}:true_prices"))
    set_state(game_id, 3)
# }}}

@socketio.on("leaderboard", namespace="/admin")
def admin_leaderboard():
    game_id = int(redis_client.hget("socket_admins", request.sid))
    named_rankings = [(redis_client.hget(f"user:{pid}", "username"), score) 
                      for pid, score in 
                      redis_client.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)]
    socketio.emit("leaderboard", named_rankings, namespace="/admin", to=request.sid)

@socketio.on("leaderboard", namespace="/player")
def player_leaderboard():
    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget(f"user:{player_id}", "game_id"))

    named_rankings = [(redis_client.hget(f"user:{pid}", "username"), score) 
                      for pid, score in 
                      redis_client.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)]
    print(named_rankings)
    socketio.emit("leaderboard", named_rankings, namespace="/player", to=request.sid)
