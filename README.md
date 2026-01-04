# Trading Game Server

## Todo
- ~~Implement preset JSON loading~~
- Document the preset JSON and CSVs
- Implement local IP detection through Firebase
  - On server start, update firebase with ip and name
  - Make server selection popup on main page of frontend
- Implement reserve accounts for short and bankruptcy
- Keyboard shortcuts
- Research smoothing for bot impact on orderbook
  - Just use 100% aggressiveness for now
- Create some cool scenarios
  - Simple future spot arb
  - Simple ETF basket arb
  - LTCM / Limitations of Arbitrage


## Notional Exposure Constraints
- (Inventory liquid cash) -  (BUY limit order total volume) - (new order volume) > 0


## Margin Account Constraints
- You must have the money to liquidate a short at all times based on ask price
  - 100% of the cover amount will be tied up in the "reserve account" until you close the short

## Bankruptcy Rule
- If your balance goes negative at any time, you will have 10 ticks worth of time to make it positive
- Otherwise, bankruptcy will occur, in which case all of your positions will be unwinded into the market (including shorts)
  - We assume any remaining shortfall is covered by "insurance"


## Game Preview
https://github.com/user-attachments/assets/ce605ea8-39c1-4523-9241-886296ab2445


