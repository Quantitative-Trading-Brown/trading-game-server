from app.services import *


def get_price(game_id: str, sec_id: str) -> float:
    bids_key = f"game:{game_id}:security:{sec_id}:orderbook:bids"
    asks_key = f"game:{game_id}:security:{sec_id}:orderbook:asks"

    best_bid_maybe = extract(r.zrange(bids_key, 0, 0, withscores=True))
    best_ask_maybe = extract(r.zrange(asks_key, 0, 0, withscores=True))

    best_bid = -best_bid_maybe[0][1] if best_bid_maybe else None
    best_ask = best_ask_maybe[0][1] if best_ask_maybe else None

    if best_bid is not None and best_ask is not None:
        return (best_bid + best_ask) / 2
    elif best_bid is not None:
        return best_bid
    elif best_ask is not None:
        return best_ask
    else:
        return 0  # Replace this with last traded price


def update_all_prices(game_id: str) -> None:
    securities = extract(r.smembers(f"game:{game_id}:securities"))
    prices = {sec_id: get_price(game_id, sec_id) for sec_id in securities}

    r.hset(f"game:{game_id}:securities:prices", mapping=prices)
