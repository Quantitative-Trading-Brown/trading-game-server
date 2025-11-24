from flask import Blueprint, request, jsonify
from .model import socketio, r
from .exchange import process_order, cancel_order, cancel_all_orders
import json

trading = Blueprint("trading", __name__)


@socketio.on("order", namespace="/player")
def new_order(security, order_side, price, quantity):
    exc_price = max(0, int(price))

    if not isinstance(quantity, int):
        return

    player_id = r.hget("socket_users", request.sid)
    game_id = r.hget(f"user:{player_id}", "game_id")

    with r.lock("everything"):
        inventory_updates, order_updates, mrp = process_order(
            game_id, player_id, security, order_side, exc_price, quantity
        )

    for trader_id, orders in order_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("orders", orders, namespace="/player", to=trader_sid)

    for trader_id, inv in inventory_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("inventory", inv, namespace="/player", to=trader_sid)

    # socketio.emit("news", f"{player_id}: {order_side} {quantity} at {price}",
    #               namespace="/admin", to=game_id)


@socketio.on("cancel", namespace="/player")
def cancel(order_id):
    player_id = r.hget("socket_users", request.sid)
    game_id = r.hget(f"user:{player_id}", "game_id")

    with r.lock("everything"):
        security, order_updates = cancel_order(
            game_id, player_id, order_id
        )

    for trader_id in order_updates:
        trader_sid = r.hget("user:{trader_id}", "sid")
        socketio.emit(
            "orders", order_updates[trader_id], namespace="/player", to=trader_sid
        )

    # socketio.emit("news", f"{player_id}: canceled at {price}",
    #               namespace="/admin", to=game_id)


@socketio.on("cancel_all", namespace="/player")
def cancel_all():
    player_id = r.hget("socket_users", request.sid)
    game_id = r.hget(f"user:{player_id}", "game_id")

    with r.lock("everything"):
        order_updates = cancel_all_orders(game_id, player_id)

    for trader_id in order_updates:
        trader_sid = r.hget("user:{trader_id}", "sid")
        socketio.emit(
            "orders", order_updates[trader_id], namespace="/player", to=trader_sid
        )

    # socketio.emit("news", f"{player_id}: canceled everything",
    #               namespace="/admin", to=game_id)
