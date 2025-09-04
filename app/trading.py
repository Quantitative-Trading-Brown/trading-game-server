from flask import Blueprint, request, jsonify
from .model import GameStatus, Game, Player
from .model import socketio, r
from .exchange import process_order, cancel_order, cancel_all_orders

trading = Blueprint("trading", __name__)


@socketio.on("order", namespace="/player")
def new_order(security, order_type, price, amount):
    if not isinstance(amount, int) or amount > 1000:
        return

    player_id = int(r.hget("socket_users", request.sid))
    game_id = int(r.hget(f"user:{player_id}", "game_id"))

    with r.lock("everything"):
        orderbook_updates, inventory_updates, mrp = process_order(
            game_id, player_id, security, order_type, price, amount
        )

    socketio.emit(
        "orderbook", (security, orderbook_updates), namespace="/player", to=game_id
    )
    socketio.emit(
        "orderbook", (security, orderbook_updates), namespace="/admin", to=game_id
    )

    for trader_id, inv in inventory_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("inventory", inv, namespace="/player", to=trader_sid)

    if mrp is not None:
        socketio.emit("price", (security, mrp), namespace="/player", to=game_id)
        socketio.emit("price", (security, mrp), namespace="/admin", to=game_id)

    # socketio.emit("news", f"{player_id}: {order_type} {amount} at {price}",
    #               namespace="/admin", to=game_id)


@socketio.on("cancel", namespace="/player")
def cancel(security, price):
    player_id = int(r.hget("socket_users", request.sid))
    game_id = int(r.hget(f"user:{player_id}", "game_id"))

    with r.lock("everything"):
        updates = cancel_order(game_id, player_id, security, price)

    socketio.emit("orderbook", (security, updates), namespace="/player", to=game_id)
    socketio.emit("orderbook", (security, updates), namespace="/admin", to=game_id)

    # socketio.emit("news", f"{player_id}: canceled at {price}",
    #               namespace="/admin", to=game_id)


@socketio.on("cancel_all", namespace="/player")
def cancel_all(security):
    player_id = int(r.hget("socket_users", request.sid))
    game_id = int(r.hget(f"user:{player_id}", "game_id"))

    with r.lock("everything"):
        updates = cancel_all_orders(game_id, player_id, security)

    socketio.emit("orderbook", (security, updates), namespace="/player", to=game_id)
    socketio.emit("orderbook", (security, updates), namespace="/admin", to=game_id)

    # socketio.emit("news", f"{player_id}: canceled everything",
    #               namespace="/admin", to=game_id)
