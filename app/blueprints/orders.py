import json

from flask import Blueprint, request, jsonify

from ..auth import identity
from ..trading import entry, cancellation
from ..services import *

blueprint = Blueprint("order", __name__)


@socketio.on("market_order", namespace="/player")
def market_order(sec_id, side, quantity):
    game_id, issuer_id = identity.identify(sid(request))

    exc_qty = max(1, int(quantity))

    with r.lock("everything"):
        entry.process_market_order(game_id, issuer_id, sec_id, side, exc_qty)


@socketio.on("limit_order", namespace="/player")
def limit_order(sec_id, side, price, quantity):
    game_id, issuer_id = identity.identify(sid(request))

    exc_price = max(0, int(price))
    exc_qty = max(1, int(quantity))

    with r.lock("everything"):
        entry.process_limit_order(game_id, issuer_id, sec_id, side, exc_price, exc_qty)


@socketio.on("cancel", namespace="/player")
def cancel(order_id):
    game_id, issuer_id = identity.identify(sid(request))

    with r.lock("everything"):
        cancellation.cancel_order(game_id, issuer_id, order_id)


@socketio.on("cancel_all", namespace="/player")
def cancel_all():
    game_id, issuer_id = identity.identify(sid(request))

    with r.lock("everything"):
        cancellation.cancel_all_orders(game_id, issuer_id)
