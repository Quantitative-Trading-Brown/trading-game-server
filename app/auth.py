from flask import Blueprint, request, jsonify
from flask_socketio import disconnect
from .model import socketio, db, redis_client
from .model import GameStatus, Game, Player
from werkzeug.exceptions import Unauthorized

auth = Blueprint('auth', __name__)

@auth.route('/verify-player', methods=['POST'])
def verify_player():
    data = request.json
    token = data.get('token')
    
    try:
        pid = token.split("-")[0]
        player = db.session.get(Player, pid)
        if token == player.token:
            return jsonify({"name": player.username}), 201
        else:
            return jsonify({"error": "Unauthorized"}), 404
    except:
        return jsonify({"error": "Unauthorized"}), 404

@socketio.on('connect', namespace="/player")
def player_connect():
    # Extract token from the query parameters
    token = request.args.get('token')

    try:
        pid = token.split("-")[0]
        player = db.session.get(Player, pid)
        if player and token == player.token:
            redis_client.set(request.sid, pid)
            socketio.emit('message', 'You are authenticated and connected!', namespace="/player", to=request.sid)
        else:
            disconnect()
    except Exception as e:
        print(e)
        disconnect()

@auth.route('/verify-admin', methods=['POST'])
def verify_admin():
    data = request.json
    token = data.get('token')
    
    try:
        gid = token.split("-")[0]
        game = db.session.get(Game, gid)
        if game and token == game.token:
            return jsonify({"code": game.code}), 201
        else:
            return jsonify({"error": "Unauthorized"}), 404
    except:
        return jsonify({"error": "Unauthorized"}), 404

@socketio.on('connect', namespace="/admin")
def admin_connect():
    # Extract token from the query parameters
    token = request.args.get('token')

    try:
        gid = token.split("-")[0]
        game = db.session.get(Game, gid)
        if token == game.token:
            socketio.emit('message', f'You are authenticated and connected!', 
                          namespace="/admin", to=request.sid)
        else:
            disconnect()
    except:
        disconnect()
