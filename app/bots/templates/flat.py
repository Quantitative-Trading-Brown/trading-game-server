import math


class FlatBot:
    def __init__(self, target, width = 5):
        """
        :param initial_fair_price: The internal fair price of the asset
        :param aggressiveness: How fast the bot adjusts its quotes toward the fair price (0-1)
        """
        self.target = target
        self.width = width

    def place_orders(self, time, orderbook):
        """
        Return the current bid/ask to post in the market.
        """
        current_bid = self.target - self.width
        current_ask = self.target + self.width

        return [("bid", current_bid, 2), ("ask", current_ask, 2)]
