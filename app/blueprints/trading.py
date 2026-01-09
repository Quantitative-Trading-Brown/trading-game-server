"""
Trading-related socket event handlers.

market_order: Handle market order submissions
limit_order: Handle limit order submissions
cancel: Handle order cancellations
cancel_all: Handle cancellation of all orders for a player
"""

import json

from flask import Blueprint, request

from app.overseer import identity
from app.exchange import entry, cancellation
from app.services import *

blueprint = Blueprint("trading", __name__)


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
