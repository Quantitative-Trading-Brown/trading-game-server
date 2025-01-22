from flask import Blueprint, request, jsonify
from .model import GameStatus, Game, Player
from .model import socketio, db, redis_client
from .auth import verify_token
from .exchange import process_order, cancel_order, cancel_all_orders

game = Blueprint('game', __name__)

# This acts as a soft auth check on the frontend to see if a redirect is necessary
@game.route("/auth", methods=['POST'])
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

@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    gid = int(redis_client.hget("socket_admins", request.sid))
    game = db.session.get(Game, gid)

    snapshot = {
        "code": game.code,
        "orderbook": redis_client.hgetall(f"{gid}:orderbook"),
        "game_props": redis_client.hgetall(f"{gid}:properties"),
    }
    socketio.emit("gamedata", snapshot, 
                  namespace="/admin", to=request.sid)
    socketio.emit("gamestate", redis_client.get(f"{gid}:state"),
                  namespace="/admin", to=request.sid)
    
@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    pid = int(redis_client.hget("socket_users", request.sid))
    player = db.session.get(Player, pid)

    snapshot = {
        "username": player.username,
        "orderbook": redis_client.hgetall(f"{player.game_id}:orderbook"),
        "game_props": redis_client.hgetall(f"{player.game_id}:properties"),
    }
    socketio.emit("gamedata", snapshot, 
                  namespace="/player", to=request.sid)
    socketio.emit("gamestate", redis_client.get(f"{player.game_id}:state"),
                  namespace="/player", to=request.sid)

@socketio.on("startgame", namespace="/admin")
def startgame():
    game_id = int(redis_client.hget("socket_admins", request.sid))
    redis_client.set(f"{game_id}:state", 1)
    socketio.emit("gamestate", 1,
                  namespace="/admin", room=game_id)
    socketio.emit("gamestate", 1, 
                  namespace="/player", room=game_id)

@socketio.on("settings", namespace="/admin")
def admin_settings(prop, value):
    """Change the game settings"""
    game_id = int(redis_client.hget("socket_admins", request.sid))
    redis_client.hset(f"{game_id}:properties", prop, value)
    socketio.emit("gamesettings", redis_client.hgetall(f"{game_id}:properties"),
                  namespace="/admin", room=game_id)
    socketio.emit("gamesettings", redis_client.hgetall(f"{game_id}:properties"),
                  namespace="/player", room=game_id)

@socketio.on("news", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients."""
    game_id = int(redis_client.hget("socket_admins", request.sid))
    socketio.emit("news", "[admin] " + message, 
                  namespace="/admin", room=game_id)
    socketio.emit("news", "[admin] " + message, 
                  namespace="/player", room=game_id)

@socketio.on("order", namespace="/player")
def new_order(order_type, price, amount):
    if not isinstance(amount, int) or amount > 1000:
        return

    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget("socket_games", request.sid))

    orderbook, inventory, mrp = process_order(game_id, player_id, order_type, price, amount)

    socketio.emit("orderbook", orderbook,
                  namespace="/player", room=game_id)
    socketio.emit("orderbook", orderbook,
                  namespace="/admin", room=game_id)

    for trader_id, inv in inventory.items():
        trader_sid = redis_client.hget(f"user:{trader_id}", "sid")
        socketio.emit("inventory", inv,
                      namespace="/player", room=game_id, to=trader_sid)

    if mrp is not None:
        socketio.emit("price", mrp,
                      namespace="/player", room=game_id)
        socketio.emit("price", mrp,
                      namespace="/admin", room=game_id)

    socketio.emit("message", f"{player_id}: {order_type} {amount} at {price}", 
                  namespace="/admin", room=game_id)

@socketio.on("cancel", namespace="/player")
def cancel(price):
    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget("socket_games", request.sid))

    updates = cancel_order(game_id, player_id, price)
    socketio.emit("orderbook", updates,
                  namespace="/player", room=game_id)
    socketio.emit("orderbook", updates,
                  namespace="/admin", room=game_id)

    socketio.emit("message", f"{player_id}: canceled at {price}", 
                  namespace="/admin", room=game_id)

@socketio.on("cancel_all", namespace="/player")
def cancel_all():
    player_id = int(redis_client.hget("socket_users", request.sid))
    game_id = int(redis_client.hget("socket_games", request.sid))

    updates = cancel_all_orders(game_id, player_id)
    socketio.emit("orderbook", updates,
                  namespace="/player", room=game_id)
    socketio.emit("orderbook", updates,
                  namespace="/admin", room=game_id)

    socketio.emit("message", f"{player_id}: canceled everything", 
                  namespace="/admin", room=game_id)
