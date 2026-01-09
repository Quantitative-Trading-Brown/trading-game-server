import json
from collections import defaultdict

from ..services import *

from .executor import Executor


def cancel_order(game_id: str, issuer_id: str, order_id: str):
    order_key = f"game:{game_id}:order:{order_id}"
    sec_id = extract(r.hget(order_key, "security"))

    to_update = Executor(game_id, sec_id)

    to_update.deleted_orders[issuer_id].append(order_id)

    to_update.apply()


def cancel_all_orders(game_id: str, issuer_id: str):
    order_ids = extract(r.smembers(f"player:{issuer_id}:orders"))
    to_delete = {}  # sec_id to executor

    for order_id in order_ids:
        order_key = f"game:{game_id}:order:{order_id}"
        sec_id = extract(r.hget(order_key, "security"))

        to_delete.setdefault(sec_id, Executor(game_id, sec_id)).deleted_orders[
            issuer_id
        ].append(order_id)

    for tu in to_delete.values():
        tu.apply()
