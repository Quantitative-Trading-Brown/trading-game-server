import random


class SimpleMM:
    def __init__(self, data, settings):
        """
        A simple market making bot that places bid and ask orders around a target price series.
        """
        self.series = data[settings["price_col"]]
        self.width = settings["width"]
        print(self.width)

    def count_bid_asks(
        self, orderbook: dict[str, float], price_low: float, price_high: float
    ) -> tuple[int, int, int]:
        to_hit_count = 0

        for p_str, qty in orderbook.items():
            q = int(qty)
            if float(p_str) <= price_low:
                to_hit_count -= (q < 0) * abs(q)
            if float(p_str) >= price_high:
                to_hit_count += (q > 0) * abs(q)

        existing_bids = int(orderbook.get(str(price_low), 0))
        existing_asks = int(orderbook.get(str(price_high), 0))

        return to_hit_count, existing_bids, existing_asks

    def place_orders(self, cur_tick, orderbook) -> list[tuple[str, float, int]]:
        """
        Return the current bid/ask to post in the market.
        """
        target_index = int(cur_tick)
        if target_index >= len(self.series):
            return []

        target_price = self.series[target_index]

        current_bid = float(target_price - self.width * random.randint(1,3))
        current_ask = float(target_price + self.width * random.randint(1,3))

        to_hit, cur_bids, cur_asks = self.count_bid_asks(
            orderbook, current_bid, current_ask
        )

        # If to_hit is positive, orderbook has bad orders on bid side
        if to_hit > 0:
            return [
                ("ask", current_ask, abs(to_hit) + 10000),
                ("bid", current_bid, 10000),
            ]
        else:
            return [
                ("bid", current_bid, abs(to_hit) + 10000),
                ("ask", current_ask, 10000),
            ]
