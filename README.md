# Trading Game Server

## Todo
- ~~Implement preset JSON loading~~
- Document the preset JSON and CSVs
- ~~Implement local IP detection through Firebase~~
- ~~Implement liquidation rules and bankruptcy~~
- Keyboard shortcuts
- Research smoothing for bot impact on orderbook
  - Just use 100% aggressiveness for now
- Create some cool scenarios
  - Simple future spot arb
  - Simple ETF basket arb
  - LTCM / Limitations of Arbitrage

## Preset JSON
### presets.json
File in the Flask app instance directory containing description of all presets. Sample here:
```json title="instance/presets.json"
{
    "ID": {
      "name": "Name of preset",
      "description": "Description of preset",
      "file": "Preset configuration filename in instance/presets"
    }
    "NB": {
        "name": "No Bots",
        "description": "Game with no bots for testing",
        "file": "manual.json"
    },
    "SP": {
        "name": "S&P 500 and AAPL 2019-2024",
        "description": "Uses a custom bot to track the time series of the S&P 500",
        "file": "stocks.json"
    }
}
```

### Preset File Example
File in the Flask app instance/presets directory containing specific settings for a preset.
```json title="instance/presets/stocks.json"
{
    "game_ticks": 1500,
    "tick_length": 2,
    "tick_data": "data/testing.csv",
    "news_col": "news",
    "initial_cash": 100000,
    "allowed_bankruptcies": 2,
    "margin_call_ticks": 2,
    "securities": {
        "SP500": {
            "name": "S&P500",
            "long_margin": 0.1,
            "short_margin": 0.1
        },
        "AAPL": {
            "name": "Apple",
            "long_margin": 0.1,
            "short_margin": 0.1
        }
    },
    "bots": {
        "sp500_mm": {
            "type": "simple_mm",
            "security": "SP500",
            "settings": {
                "price_col": "spindx_close",
                "width": 2
            }
        },
        "aapl_mm": {
            "type": "simple_mm",
            "security": "AAPL",
            "settings": {
                "price_col": "aapl_close",
                "width": 2
            }
        }
    }
}
```

## Margin Constraints
We limit positions based on the comparison between equity (cash + position value) and gross exposure. Gross exposure for each asset
is scaled according to the long_margin and short_margin settings in preset json.

If this margin exceeds equity for more than some customizable number of game ticks, set off liquidation (market order the user's entire inventory).
If, after liquidation, the user is still negative cash, a "margin call" occurs.

## Margin Call
When you receive a margin call, a popup will appear asking to confirm injection of more cash (initial cash). This allows you to continue trading,
but you will be ranked strictly below users who did not get margin called. If you get margin called more than a customizable number of times,
you will be kicked out of the game.

## Valkey Key Documentation

Player ids count up from 0 independent of game. This means that if Game 1 has three players, Game 2's first player will have player id 3.

### Player
*player:{player_id}* -- Hashmap of player properties
- game_id
- sid
- username
- score

*player:{player_id}:orders* -- Set of player's order ids

*player:{player_id}:inventory* -- Hashmap of security id to position

*player:{player_id}:inventory:cash* -- Player's cash amount

*player:{player_id}:inventory:position_value* -- Sum value of positions based on last updated prices

*player:{player_id}:inventory:margin* -- Most recently calculated margin requirement

### Game
*game:{game_id}:players* -- Set of player ids

*game:{game_id}* -- Hash map of game properties
- code -- join code for players
- state -- current status of the game (0,1,2,3)
- game_ticks -- length of game in ticks
- tick_length -- length of one tick in seconds

*game:{game_id}:order_count* -- Number of orders placed this game (used to build order ids)

*game:{game_id}:securities* -- Set of security ids

*game:{game_id}:securities:prices* -- Map of security ids to most last updated price

*game:{game_id}:security:{sec_id}:orderbook:bids/asks* -- Set of order ids sorted first by highest/lowest price, then lexigraphically by order_id
- For bids/asks, higher/lower prices get priority
- As of now, this is done by storing negated bid prices because reversing the sort in its entirety would also reverse time priority
- In future versions, a separate order_id assignment mechanism for bids can be developed to allow reverse sort

*game:{game_id}:security:{sec_id}:orderbook* -- Hashmap from price to quantity in the orderbook (asks are represented as negative)

*game:{game_id}:security:{sec_id}:orderbook:updates* -- List of json objects representing orderbook updates since last tick

*game:{game_id}:order:{order_id}* -- Hashmap of order properties
- price
- quantity
- security -- security id
- side -- "bids" or "asks"
- issuer_id -- player_id that put in the order


### Other
*game_count* -- Number of games created so far (used to generate next game id)

*player_tokens* -- Hashmap from player_id to player token

*admin_tokens* -- Hashmap from game_id to admin token

*player_sockets* -- Hashmap from player's sid to player_id

*admin_sockets* -- Hashmap from admin's sid to game_id

*codes* -- Hashmap from code to game_id


## Game Preview
https://github.com/user-attachments/assets/ce605ea8-39c1-4523-9241-886296ab2445


