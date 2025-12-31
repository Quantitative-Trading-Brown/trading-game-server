import json

from flask import Blueprint, request, jsonify

from ..auth import identity
from ..trading import entry, cancellation
from ..services import *

blueprint = Blueprint("order", __name__)


@socketio.on("market_order", namespace="/player")
def market_order(security, order_side, quantity):
    game_id, issuer_id = identity.identify(sid(request))

    exc_quantity = max(1, int(quantity))

    with r.lock("everything"):
        update = entry.process_market_order(
            game_id, issuer_id, security, order_side, quantity
        )

        update.apply()


@socketio.on("limit_order", namespace="/player")
def limit_order(security, order_side, price, quantity):
    game_id, issuer_id = identity.identify(sid(request))

    exc_price = max(0, int(price))
    exc_quantity = max(1, int(quantity))

    with r.lock("everything"):
        update = entry.process_limit_order(
            game_id, issuer_id, security, order_side, exc_price, quantity
        )

        update.apply()


@socketio.on("cancel", namespace="/player")
def cancel(order_id):
    game_id, issuer_id = identity.identify(sid(request))

    with r.lock("everything"):
        update = cancellation.cancel_order(game_id, issuer_id, order_id)

        update.apply()


@socketio.on("cancel_all", namespace="/player")
def cancel_all():
    game_id, issuer_id = identity.identify(sid(request))

    with r.lock("everything"):
        update = cancellation.cancel_all_orders(game_id, issuer_id)

        update.apply()
