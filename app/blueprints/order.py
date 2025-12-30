from flask import Blueprint, request, jsonify
from typing import Awaitable

from ..utils.socketio import socketio, sid
from ..utils.storage import r, extract

from ..matching_engine import matching_engine as me
import json

order_manager = Blueprint("order_manager", __name__)


@socketio.on("market_order", namespace="/player")
def market_order(security, order_side, quantity):
    exc_quantity = max(1, int(quantity))

    player_id = extract(r.hget("socket_users", sid(request)))
    game_id = extract(r.hget(f"user:{player_id}", "game_id"))

    with r.lock("everything"):
        inventory_updates, order_updates = me.process_market_order(
            game_id, player_id, security, order_side, quantity
        )

    for trader_id, orders in order_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("orders", orders, namespace="/player", to=trader_sid)

    for trader_id, inv in inventory_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("inventory", inv, namespace="/player", to=trader_sid)



@socketio.on("limit_order", namespace="/player")
def limit_order(security, order_side, price, quantity):
    exc_price = max(0, int(price))
    exc_quantity = max(1, int(quantity))

    player_id = extract(r.hget("socket_users", sid(request)))
    game_id = extract(r.hget(f"user:{player_id}", "game_id"))

    with r.lock("everything"):
        inventory_updates, order_updates = me.process_limit_order(
            game_id, player_id, security, order_side, exc_price, quantity
        )

    for trader_id, orders in order_updates.items():
        trader_sid = extract(r.hget(f"user:{trader_id}", "sid"))
        socketio.emit("orders", orders, namespace="/player", to=trader_sid)

    for trader_id, inv in inventory_updates.items():
        trader_sid = extract(r.hget(f"user:{trader_id}", "sid"))
        socketio.emit("inventory", inv, namespace="/player", to=trader_sid)


@socketio.on("cancel", namespace="/player")
def cancel(order_id):
    player_id = extract(r.hget("socket_users", sid(request)))
    game_id = extract(r.hget(f"user:{player_id}", "game_id"))

    with r.lock("everything"):
        security, order_updates = me.cancel_order(game_id, player_id, order_id)

    for trader_id in order_updates:
        trader_sid = r.hget("user:{trader_id}", "sid")
        socketio.emit(
            "orders", order_updates[trader_id], namespace="/player", to=trader_sid
        )


@socketio.on("cancel_all", namespace="/player")
def cancel_all():
    player_id = extract(r.hget("socket_users", sid(request)))
    game_id = extract(r.hget(f"user:{player_id}", "game_id"))

    with r.lock("everything"):
        order_updates = me.cancel_all_orders(game_id, player_id)

    for trader_id in order_updates:
        trader_sid = r.hget("user:{trader_id}", "sid")
        socketio.emit(
            "orders", order_updates[trader_id], namespace="/player", to=trader_sid
        )
