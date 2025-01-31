from flask import Blueprint, request, jsonify
from flask_socketio import disconnect, join_room
from .model import socketio, redis_client
from .model import GameStatus, Game, Player

auth = Blueprint('auth', __name__)

def verify_token(token, auth_type):
    """
    Returns player object if user_type is player otherwise game object if user_type is admin
    """
    token_components = token.split("-")
    try:
        if auth_type != token_components[0] or len(token_components) != 3:
            return None
        elif auth_type == "player":
            auth_id = int(token_components[1])
            auth_token = redis_client.hget("player_tokens", auth_id)
        elif auth_type == "admin":
            auth_id = int(token_components[1])
            auth_token = redis_client.hget(f"admin_tokens", auth_id)
        else:
            return None

        return auth_id if token == auth_token else None
    except Exception as e:
        print("Authentication error:", e)
        return None

# This acts as a soft auth check on the frontend to see if a redirect is necessary
@auth.route("/auth", methods=['POST'])
def checkAuth():
    data = request.json
    token = data["token"]

    verify_player = verify_token(token, "player")
    if verify_player is not None:
        return jsonify({
            "type": "player"
        }), 201
    
    verify_admin = verify_token(token, "admin")
    if verify_admin is not None:
        return jsonify({
            "type": "admin"
        }), 201

    return jsonify({
        "error": "Invalid token"
    }), 404

@socketio.on('connect', namespace="/player")
def player_connect():
    # Extract token from the query parameters
    token = request.args.get('token')
    player_id = verify_token(token, "player")

    if player_id is not None:
        game_id = int(redis_client.hget(f"user:{player_id}", "game_id"))

        join_room(game_id)
        redis_client.hset("socket_users", request.sid, player_id)
        redis_client.hset(f"user:{player_id}", "sid", request.sid)
        socketio.emit('message', 'You are authenticated and connected!', 
                      namespace="/player", to=request.sid)
    else:
        disconnect()

@socketio.on('connect', namespace="/admin")
def admin_connect():
    # Extract token from the query parameters
    token = request.args.get('token')
    game_id = verify_token(token, "admin")
    
    if game_id is not None:
        join_room(game_id)
        redis_client.hset("socket_admins", request.sid, game_id)
        socketio.emit("news", f'You are authenticated and connected!', 
                      namespace="/admin", to=request.sid)
    else:
        disconnect()

@socketio.on('disconnect', namespace='/player')
def player_disconnect():
    player_id = int(redis_client.hget("socket_users", request.sid))
    redis_client.hdel(f"user:{player_id}", "sid")
    redis_client.hdel("socket_users", request.sid)
