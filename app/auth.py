from flask import Blueprint, request, jsonify
from flask_socketio import disconnect, join_room
from .model import socketio, db, redis_client
from .model import GameStatus, Game, Player

auth = Blueprint('auth', __name__)

def verify_token(token, force_type = None):
    """
    Returns player object if user_type is player otherwise game object if user_type is admin
    """
    token_components = token.split("-")
    auth_type = force_type if force_type is not None else token_components[0]
    try:
        if auth_type != token_components[0]:
            return None
        elif auth_type == "player":
            pid = token_components[1]
            auth_obj = db.session.get(Player, pid)
        elif auth_type == "admin":
            gid = token_components[1]
            auth_obj = db.session.get(Game, gid)
        else:
            return None

        return (auth_type, auth_obj) if auth_obj and token == auth_obj.token else None
    except Exception as e:
        print("Authentication error:", e)
        return None

@socketio.on('connect', namespace="/player")
def player_connect():
    # Extract token from the query parameters
    token = request.args.get('token')
    verify = verify_token(token, "player")

    if verify is not None:
        _, player = verify
        join_room(player.game_id)
        redis_client.hset("socket_users", request.sid, player.pid)
        redis_client.hset("socket_games", request.sid, player.game_id)
        redis_client.hset(f"user:{player.pid}", "sid", request.sid)
        socketio.emit('message', 'You are authenticated and connected!', 
                      namespace="/player", to=request.sid, room=player.game_id)
    else:
        disconnect()

@socketio.on('connect', namespace="/admin")
def admin_connect():
    # Extract token from the query parameters
    token = request.args.get('token')
    verify = verify_token(token, "admin")
    
    if verify is not None:
        _, game = verify
        join_room(game.gid)
        redis_client.hset("socket_admins", request.sid, game.gid)
        socketio.emit("news", f'You are authenticated and connected!', 
                      namespace="/admin", to=request.sid, room=game.gid)
    else:
        disconnect()

@socketio.on('disconnect', namespace='/player')
def player_disconnect():
    player_id = redis_client.hget("users", request.sid)
    redis_client.hdel(f"user:{player_id}", "sid")
    redis_client.hdel("users", request.sid)
