import math


class SinewaveBot:
    def __init__(self, amplitude, freq, shift):
        """
        :param initial_fair_price: The internal fair price of the asset
        :param aggressiveness: How fast the bot adjusts its quotes toward the fair price (0-1)
        """
        self.amplitude = amplitude
        self.freq = freq
        self.shift = shift

    def place_orders(self, time, orderbook):
        """
        Return the current bid/ask to post in the market.
        """
        target_price = math.sin(time / self.freq) * self.amplitude + self.shift

        current_bid = target_price - 5
        current_ask = target_price + 5

        return [("bid", current_bid, 2), ("ask", current_ask, 2)]
