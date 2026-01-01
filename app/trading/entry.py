import json
from collections import defaultdict

from ..services import *

from .trade_update import TradeUpdate


def process_limit_order(
    game_id: str,
    issuer_id: str,
    sec_id: str,
    order_side: str,
    price: float,
    quantity: int,
) -> None:
    to_update = TradeUpdate(game_id, sec_id)

    # In Redis storage, prices for bids in the sorted set of the orderbook are negative to facilitate sorting
    # Prices in order details are always positive
    remaining_quantity = quantity

    orderbook_side = "bids" if order_side == "bid" else "asks"
    orderbook_opp = "asks" if order_side == "bid" else "bids"
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"  # Raw orderbook
    opposite_set_key = f"{orderbook_key}:{orderbook_opp}"  # List of opposite orders sorted by price and recency

    while remaining_quantity > 0:
        best_price = r.zrange(opposite_set_key, 0, 0, withscores=True)

        if (
            not best_price
            or (order_side == "ask" and abs(best_price[0][1]) < price)
            or (order_side == "bid" and abs(best_price[0][1]) > price)
        ):
            break

        best_order_id = best_price[0][0]

        trade_quantity, trade_price = process_trade(
            game_id,
            best_order_id,
            issuer_id,
            remaining_quantity,
            to_update,
        )

        remaining_quantity -= trade_quantity

    # Put in new order if there is residual in the request
    if remaining_quantity > 0:
        to_update.new_orders[issuer_id].append(
            {
                "security": sec_id,
                "side": orderbook_side,
                "price": price,
                "quantity": quantity,
                "issuer_id": issuer_id,
            }
        )

    to_update.apply()


def process_market_order(
    game_id: str, issuer_id: str, sec_id: str, order_side: str, quantity: int
) -> None:
    to_update = TradeUpdate(game_id, sec_id)

    remaining_quantity = quantity
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"

    orderbook_side = "bids" if order_side == "bid" else "asks"
    orderbook_opp = "asks" if order_side == "bid" else "bids"

    opposite_set_key = f"{orderbook_key}:{orderbook_opp}"

    # Market order continues consuming liquidity until empty
    while remaining_quantity > 0:
        best_price = r.zrange(opposite_set_key, 0, 0, withscores=True)

        # No liquidity available
        if not best_price:
            break

        best_order_id = best_price[0][0]
        trade_quantity, trade_price = process_trade(
            game_id,
            best_order_id,
            issuer_id,
            remaining_quantity,
            to_update,
        )

        update_quantity = trade_quantity if order_side == "bid" else -trade_quantity
        remaining_quantity -= trade_quantity

    to_update.apply()


def process_trade(
    game_id: str,
    order_id: str,
    initiator_id: str,
    requested_quantity: int,
    to_update: TradeUpdate,
) -> tuple[int, float]:
    """
    Process a trade against an existing order in the orderbook.
    """
    order_key = f"game:{game_id}:order:{order_id}"
    order_details = extract(r.hgetall(order_key))

    issuer_id = order_details["issuer_id"]
    trade_price = int(float(order_details["price"]))

    avail_quantity = int(float(order_details["quantity"]))
    trade_quantity = min(requested_quantity, avail_quantity)

    # Update order if old order residual exists, else knock it out completely
    if avail_quantity > trade_quantity:
        to_update.updated_orders[issuer_id][order_id] = (
            -trade_quantity,
            avail_quantity - trade_quantity,
        )
    else:
        to_update.deleted_orders[issuer_id].append(order_id)

    buyer_id = initiator_id if order_details["side"] == "asks" else issuer_id
    seller_id = initiator_id if order_details["side"] == "bids" else issuer_id

    to_update.inventory_updates[buyer_id]["USD"] -= trade_price * trade_quantity
    to_update.inventory_updates[seller_id]["USD"] += trade_price * trade_quantity

    to_update.inventory_updates[buyer_id][order_details["security"]] += trade_quantity
    to_update.inventory_updates[seller_id][order_details["security"]] -= trade_quantity

    return trade_quantity, trade_price
