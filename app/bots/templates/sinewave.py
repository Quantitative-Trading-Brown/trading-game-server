import math


class SinewaveBot:
    def __init__(self, base_price, amplitude, freq):
        self.base_price = base_price
        self.amplitude = amplitude
        self.freq = freq

    def place_orders(self, time, orderbook):
        """
        Return the current bid/ask to post in the market.
        """
        target_price = math.sin(time / self.freq) * self.amplitude + self.base_price

        current_bid = target_price - 5
        current_ask = target_price + 5

        return [("bid", current_bid, 2), ("ask", current_ask, 2)]
