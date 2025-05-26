from flask import Blueprint, request, jsonify
from .model import socketio, r
from .model import GameStatus, Game, Player
from .rankings import generate_rankings

game = Blueprint('game', __name__)

# {{{ Snapshotting
def game_snapshot(game_id, player_id=None):
    securities = r.smembers(f"game:{game_id}:securities")
    orderbooks = {sec_id:r.hgetall(f"game:{game_id}:security:{sec_id}:orderbook") 
                  for sec_id in securities}
    security_props = {sec_id:r.hgetall(f"game:{game_id}:security:{sec_id}") 
                  for sec_id in securities}
    snapshot = {
        "game_state": r.get(f"game:{game_id}:state"),
        "game_props": r.hgetall(f"game:{game_id}"),
        "securities": security_props,
        "orderbooks": orderbooks,
    }

    if player_id:
        snapshot["username"] = r.hget(f"user:{player_id}", "username")

    return snapshot

@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    game_id = int(r.hget("socket_admins", request.sid))

    socketio.emit("snapshot", game_snapshot(game_id), 
                  namespace="/admin", to=request.sid)

@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    player_id = int(r.hget("socket_users", request.sid))
    game_id = int(r.hget(f"user:{player_id}", "game_id"))

    socketio.emit("snapshot", game_snapshot(game_id, player_id), 
                  namespace="/player", to=request.sid)
# }}}

@socketio.on("news", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients."""
    game_id = int(r.hget("socket_admins", request.sid))
    socketio.emit("news", "[news] " + message, 
                  namespace="/admin", to=game_id)
    socketio.emit("news", "[news] " + message, 
                  namespace="/player", to=game_id)

# {{{ State Controller
def set_state(game_id, state):
    r.set(f"game:{game_id}:state", state)

    socketio.emit("gamestate_update", state,
                  namespace="/admin", to=game_id)
    socketio.emit("gamestate_update", state, 
                  namespace="/player", to=game_id)

@socketio.on("startgame", namespace="/admin")
def startgame(settings={}):
    game_id = int(r.hget("socket_admins", request.sid))
    for security in settings["securities"]:
        sec_id = security["id"]
        r.sadd(f"game:{game_id}:securities", sec_id)
        r.hset(f"game:{game_id}:security:{sec_id}", "name", security["name"])
        r.hset(f"game:{game_id}:security:{sec_id}", "bookMin", security["bookMin"])
        r.hset(f"game:{game_id}:security:{sec_id}", "bookMax", security["bookMax"])
        r.hset(f"game:{game_id}:security:{sec_id}", "scale", security["scale"])

    # For now, securities are the only things we need to update. Maybe other game settings later?
    security_props = {sec_id:r.hgetall(f"game:{game_id}:security:{sec_id}") 
                      for sec_id in r.smembers(f"game:{game_id}:securities")}
    socketio.emit("securities_update", security_props, 
                  namespace="/admin", to=game_id)
    socketio.emit("securities_update", security_props, 
                  namespace="/player", to=game_id)

    set_state(game_id, 1)

@socketio.on("endgame", namespace="/admin")
def endgame():
    game_id = int(r.hget("socket_admins", request.sid))
    set_state(game_id, 2)

@socketio.on("rankgame", namespace="/admin")
def rankgame(true_prices={}):
    game_id = int(r.hget("socket_admins", request.sid))

    for sec_id, price in true_prices.items():
        r.hset(f"game:{game_id}:true_prices", sec_id, price)
    r.hset(f"game:{game_id}:true_prices", 0, 1)

    generate_rankings(game_id)
    set_state(game_id, 3)
# }}}

# {{{ Leaderboard Management
@socketio.on("leaderboard", namespace="/admin")
def admin_leaderboard():
    game_id = int(r.hget("socket_admins", request.sid))
    named_rankings = [(r.hget(f"user:{pid}", "username"), score) 
                      for pid, score in 
                      r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)]
    socketio.emit("leaderboard", named_rankings, namespace="/admin", to=request.sid)

@socketio.on("leaderboard", namespace="/player")
def player_leaderboard():
    player_id = int(r.hget("socket_users", request.sid))
    game_id = int(r.hget(f"user:{player_id}", "game_id"))

    named_rankings = [(r.hget(f"user:{pid}", "username"), score) 
                      for pid, score in 
                      r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)]
    print(named_rankings)
    socketio.emit("leaderboard", named_rankings, namespace="/player", to=request.sid)# }}}
