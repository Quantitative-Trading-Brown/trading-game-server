# Trading Game Server

## Todo
- Keyboard shortcuts
- Research smoothing for bot impact on orderbook
  - Just use 100% aggressiveness for now
- Create some cool scenarios
  - Simple future spot arb
  - Simple ETF basket arb
  - LTCM / Limitations of Arbitrage

## Game Rules

### Margin Constraints
Positions are limited based on the comparison between equity (cash + position value) and gross exposure. Gross exposure for each asset
is scaled according to the long_margin and short_margin settings in preset json.

If this margin exceeds equity for more than some customizable number of game ticks, set off liquidation (market order the player's entire inventory).
If, after liquidation, the player still does not have enough money to cover their positions (equity < margin), a bankruptcy occurs.

### Bankruptcy
When you go bankrupt, a popup will appear asking to confirm injection of more cash (initial cash). This resets the player's cash to the starting cash amount and 
allows the player to continue trading, but they will be ranked strictly below users who did not go bankrupt. If bankruptcy occurs more than a customizable number of times,
the player will be kicked out of the game.

## Configuration
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

### Preset File

Game presets are defined in JSON configuration files located in `instance/presets/`. These files control all aspects of game behavior, timing, securities, and bots.

#### Example: Stock Trading Preset

**`instance/presets/stocks.json`**
```json
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

#### Game Settings

| Field | Type | Description |
|-------|------|-------------|
| `game_ticks` | `number` | Total number of ticks in the game (1500 = game duration) |
| `tick_length` | `number` | Duration of each tick in seconds |
| `tick_data` | `string` | Path to CSV file containing historical market data |
| `news_col` | `string` | Column name in CSV containing news/events |
| `initial_cash` | `number` | Starting cash for each player (in USD) |
| `allowed_bankruptcies` | `number` | Number of times a player can go bankrupt before elimination |
| `margin_call_ticks` | `number` | Number of ticks before forced liquidation after margin call |

#### Securities

Each security in the `securities` object defines a tradeable asset:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Display name of the security |
| `long_margin` | `number` | Margin requirement for long positions (0.1 = 10%) |
| `short_margin` | `number` | Margin requirement for short positions (0.1 = 10%) |

**Example:**
```json
"AAPL": {
    "name": "Apple",
    "long_margin": 0.1,
    "short_margin": 0.1
}
```

#### Bots (Market Makers)

Bots provide liquidity by automatically placing orders. Each bot configuration includes:

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Bot type (currently supports `"simple_mm"` for market maker) |
| `security` | `string` | Security symbol the bot trades |
| `settings.price_col` | `string` | CSV column containing reference prices |
| `settings.width` | `number` | Spread width around reference price |

**Example:**
```json
"sp500_mm": {
    "type": "simple_mm",
    "security": "SP500",
    "settings": {
        "price_col": "spindx_close",
        "width": 2
    }
}
```

### Data File Format

The CSV file specified in `tick_data` must include all the columns specified by parameters ending in `_col` above.
It should have one row per game tick.

**Example CSV structure:**
```csv
tick,spindx_close,aapl_close,news
0,4500.00,150.25,"Market opens steady"
1,4502.50,150.30,""
2,4501.00,150.50,"Tech sector rallies"
```


