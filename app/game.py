from flask import Blueprint, request, jsonify
from .model import GameStatus, Game
from .model import socketio, db, redis_client
from .auth import verify_token
from .exchange import process_order, cancel_order, cancel_all_orders

game = Blueprint('game', __name__)

@game.route('/snapshot', methods=['POST'])
def snapshot():
    data = request.json
    token = data["token"]
    
    verify_player = verify_token(token, "player")
    if verify_player is not None:
        _, player = verify_player
        return jsonify({
            "name": player.username,
            "orderbook": redis_client.hgetall(f"{player.game_id}:orderbook")
        }), 201

    verify_admin = verify_token(token, "admin")
    if verify_admin is not None:
        _, game = verify_admin
        return jsonify({"code": game.code}), 201
    
    return jsonify({"error": "Invalid request"}), 404

@socketio.on("message", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients."""
    game_id = int(redis_client.hget("socket_admins", request.sid))
    socketio.emit("message", "[admin] " + message, 
                  namespace="/admin", room=game_id)
    socketio.emit("message", "[admin] " + message, 
                  namespace="/player", room=game_id)

@socketio.on("order", namespace="/player")
def new_order(order_type, price, amount):
    if not isinstance(amount, int) or amount > 1000:
        return

    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget("socket_games", request.sid))

    updates, mrp = process_order(game_id, player_id, order_type, price, amount)

    socketio.emit("orderbook", updates,
                  namespace="/player", room=game_id)
    if mrp is not None:
        socketio.emit("price", mrp,
                      namespace="/player", room=game_id)

    socketio.emit("message", f"{player_id}: {order_type} {amount} at {price}", 
                  namespace="/admin", room=game_id)

@socketio.on("cancel", namespace="/player")
def cancel(price):
    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget("socket_games", request.sid))

    updates = cancel_order(game_id, player_id, price)
    socketio.emit("orderbook", updates,
                  namespace="/player", room=game_id)

    socketio.emit("message", f"{player_id}: canceled at {price}", 
                  namespace="/admin", room=game_id)

@socketio.on("cancel_all", namespace="/player")
def cancel_all():
    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget("socket_games", request.sid))

    updates = cancel_all_orders(game_id, player_id)
    socketio.emit("orderbook", updates,
                  namespace="/player", room=game_id)

    socketio.emit("message", f"{player_id}: canceled everything", 
                  namespace="/admin", room=game_id)
