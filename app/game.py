from flask import Blueprint, request, jsonify
from .model import socketio, db, redis_client
from .model import GameStatus, Game, Player
from .rankings import generate_rankings

game = Blueprint('game', __name__)

@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    gid = int(redis_client.hget("socket_admins", request.sid))
    game = db.session.get(Game, gid)

    snapshot = {
        "code": game.code,
        "orderbook": redis_client.hgetall(f"game:{gid}:orderbook"),
        "game_props": redis_client.hgetall(f"game:{gid}:properties"),
    }
    socketio.emit("gamedata", snapshot, 
                  namespace="/admin", to=request.sid)
    socketio.emit("gamestate", redis_client.get(f"game:{gid}:state"),
                  namespace="/admin", to=request.sid)
    
@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    pid = int(redis_client.hget("socket_users", request.sid))
    player = db.session.get(Player, pid)

    snapshot = {
        "username": player.username,
        "orderbook": redis_client.hgetall(f"game:{player.game_id}:orderbook"),
        "game_props": redis_client.hgetall(f"game:{player.game_id}:properties"),
    }
    socketio.emit("gamedata", snapshot, 
                  namespace="/player", to=request.sid)
    socketio.emit("gamestate", redis_client.get(f"game:{player.game_id}:state"),
                  namespace="/player", to=request.sid)

@socketio.on("settings", namespace="/admin")
def change_settings(updates={}):
    """Simple settings fetch if no updates"""
    game_id = int(redis_client.hget("socket_admins", request.sid))
    if not updates:
        socketio.emit("gamesettings", redis_client.hgetall(f"game:{game_id}:properties"),
                      namespace="/admin", to=request.sid)
        return

    """Change the game settings for everyone"""
    for key in updates:
        redis_client.hset(f"game:{game_id}:properties", key, updates[key])
    socketio.emit("gamesettings", redis_client.hgetall(f"game:{game_id}:properties"),
                  namespace="/admin", to=game_id)
    socketio.emit("gamesettings", redis_client.hgetall(f"game:{game_id}:properties"),
                  namespace="/player", to=game_id)

@socketio.on("settings", namespace="/player")
def fetch_settings():
    """Fetch the game settings"""
    pid = int(redis_client.hget("socket_users", request.sid))
    player = db.session.get(Player, pid)

    socketio.emit("gamesettings", redis_client.hgetall(f"game:{player.game_id}:properties"),
                  namespace="/player", to=request.sid)

@socketio.on("news", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients."""
    game_id = int(redis_client.hget("socket_admins", request.sid))
    socketio.emit("news", "[admin] " + message, 
                  namespace="/admin", to=game_id)
    socketio.emit("news", "[admin] " + message, 
                  namespace="/player", to=game_id)

@socketio.on("startgame", namespace="/admin")
def startgame():
    game_id = int(redis_client.hget("socket_admins", request.sid))
    redis_client.set(f"game:{game_id}:state", 1)
    socketio.emit("gamestate", 1,
                  namespace="/admin", to=game_id)
    socketio.emit("gamestate", 1, 
                  namespace="/player", to=game_id)

@socketio.on("endgame", namespace="/admin")
def endgame():
    game_id = int(redis_client.hget("socket_admins", request.sid))
    redis_client.set(f"game:{game_id}:state", 2)
    socketio.emit("gamestate", 2,
                  namespace="/admin", to=game_id)
    socketio.emit("gamestate", 2, 
                  namespace="/player", to=game_id)

    generate_rankings(game_id)
