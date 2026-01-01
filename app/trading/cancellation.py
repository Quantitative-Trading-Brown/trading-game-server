import json
from collections import defaultdict

from ..services import *

from .trade_update import TradeUpdate


def cancel_order(game_id: str, issuer_id: str, order_id: str):
    order_key = f"game:{game_id}:order:{order_id}"
    sec_id = extract(r.hget(order_key, "security"))

    to_update = TradeUpdate(game_id, sec_id)

    to_update.deleted_orders[issuer_id].append(order_id)

    to_update.apply()


def cancel_all_orders(game_id: str, issuer_id: str):
    order_ids = extract(r.smembers(f"user:{issuer_id}:orders"))
    to_delete = defaultdict(list) # sec_id to list of order_ids

    for order_id in order_ids:
        order_key = f"game:{game_id}:order:{order_id}"
        sec_id = extract(r.hget(order_key, "security"))

        to_delete.setdefault(sec_id, TradeUpdate(game_id, sec_id))
        to_delete[sec_id].deleted_orders[issuer_id].append(order_id)

    for tu in to_delete.values():
        tu.apply()
