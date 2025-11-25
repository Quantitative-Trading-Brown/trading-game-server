from flask import Blueprint, request, jsonify
from typing import Awaitable

from .utils import socketio, r, sid
from .matching_engine import (
    process_limit_order,
    process_market_order,
    cancel_order,
    cancel_all_orders,
)
import json

order_manager = Blueprint("order_manager", __name__)


@socketio.on("market_order", namespace="/player")
def handle_market_order(security, order_side, quantity):
    exc_quantity = max(1, int(quantity))

    player_id = r.hget("socket_users", sid(request))
    game_id = r.hget(f"user:{player_id}", "game_id")

    assert not isinstance(player_id, Awaitable) and player_id
    assert not isinstance(game_id, Awaitable) and game_id

    with r.lock("everything"):
        inventory_updates, order_updates = process_market_order(
            game_id, player_id, security, order_side, quantity
        )

    for trader_id, orders in order_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("orders", orders, namespace="/player", to=trader_sid)

    for trader_id, inv in inventory_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("inventory", inv, namespace="/player", to=trader_sid)



@socketio.on("limit_order", namespace="/player")
def handle_limit_order(security, order_side, price, quantity):
    exc_price = max(0, int(price))
    exc_quantity = max(1, int(quantity))

    player_id = r.hget("socket_users", sid(request))
    game_id = r.hget(f"user:{player_id}", "game_id")

    assert not isinstance(player_id, Awaitable) and player_id
    assert not isinstance(game_id, Awaitable) and game_id

    with r.lock("everything"):
        inventory_updates, order_updates = process_limit_order(
            game_id, player_id, security, order_side, exc_price, quantity
        )

    for trader_id, orders in order_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("orders", orders, namespace="/player", to=trader_sid)

    for trader_id, inv in inventory_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("inventory", inv, namespace="/player", to=trader_sid)


@socketio.on("cancel", namespace="/player")
def cancel(order_id):
    player_id = r.hget("socket_users", sid(request))
    game_id = r.hget(f"user:{player_id}", "game_id")
    assert not isinstance(player_id, Awaitable) and player_id
    assert not isinstance(game_id, Awaitable) and game_id

    with r.lock("everything"):
        security, order_updates = cancel_order(game_id, player_id, order_id)

    for trader_id in order_updates:
        trader_sid = r.hget("user:{trader_id}", "sid")
        socketio.emit(
            "orders", order_updates[trader_id], namespace="/player", to=trader_sid
        )


@socketio.on("cancel_all", namespace="/player")
def cancel_all():
    player_id = r.hget("socket_users", sid(request))
    game_id = r.hget(f"user:{player_id}", "game_id")
    assert not isinstance(player_id, Awaitable) and player_id
    assert not isinstance(game_id, Awaitable) and game_id

    with r.lock("everything"):
        order_updates = cancel_all_orders(game_id, player_id)

    for trader_id in order_updates:
        trader_sid = r.hget("user:{trader_id}", "sid")
        socketio.emit(
            "orders", order_updates[trader_id], namespace="/player", to=trader_sid
        )
