# How to Run

## macos (outdated since update to valkey)
- Installing redis: brew services redis
- Running redis: brew services start

- To start: sudo launchctl start com.cloudflare.cloudflared
- To stop: sudo launchctl stop com.cloudflare.cloudflared

# Valkey Key Schema Documentation

This system uses **Valkey (Redis) sorted sets, hashes, and counters** to manage a trading order book for multiple games, securities, and players.

---

## Order Book Keys

### `game:{game_id}:security:{sec_id}:orderbook`
- **Type**: Hash (`HSET`, `HINCRBY`)  
- **Fields**: `{price}` → aggregated net amount at that price  
- **Purpose**: Tracks total outstanding volume at each price level for a given security in a game.  
- **Notes**:  
  - Buy orders increment (positive values).  
  - Sell orders decrement (negative values).  

---

### `game:{game_id}:security:{sec_id}:orderbook:bids`
- **Type**: Sorted Set (`ZADD`, `ZRANGE`)  
- **Members**: `{order_key}` (reference to an individual order)  
- **Scores**: `-price` (negative price ensures highest bid sorts first)  
- **Purpose**: Holds all active buy orders for the security.  

---

### `game:{game_id}:security:{sec_id}:orderbook:asks`
- **Type**: Sorted Set (`ZADD`, `ZRANGE`)  
- **Members**: `{order_key}`  
- **Scores**: `price`  
- **Purpose**: Holds all active sell orders for the security.  

---

### `game:{game_id}:security:{sec_id}:orderbook:order_count`
- **Type**: Counter (`INCR`)  
- **Purpose**: Generates sequential order IDs for the security’s order book.  

---

## Individual Order Keys

### `{orderbook_key}:{order_id}`  
Example: `game:12:security:7:orderbook:000123`  

- **Type**: Hash (`HSET`, `HGETALL`)  
- **Fields**:  
  - `side` → `"bids"` or `"asks"`  
  - `price` → price of the order  
  - `amount` → remaining quantity of the order  
  - `player_id` → owner of the order  
- **Purpose**: Stores details for each individual order.  
- **Lifecycle**: Created when an order has residual volume; deleted when fully matched or cancelled.  

---

## User Order Keys

### `user:{player_id}:security:{sec_id}:orders`
- **Type**: Sorted Set (`ZADD`, `ZRANGEBYSCORE`, `ZRANGE`)  
- **Members**: `{order_key}`  
- **Scores**: `price`  
- **Purpose**: Tracks all active orders for a given player and security.  
- **Notes**: Used for cancellation of individual or all user orders.  

---

## User Inventory Keys

### `user:{player_id}:inventory`
- **Type**: Hash (`HINCRBY`, `HINCRBYFLOAT`)  
- **Fields**:  
  - `0` → cash balance (float)  
  - `{sec_id}` → quantity of that security (integer)  
- **Purpose**: Tracks each user’s cash and security holdings.  
- **Notes**: Updated when trades execute.  

---

## Security Metadata

### `game:{game_id}:security:{sec_id}`
- **Type**: Hash (`HGET`)  
- **Fields**:  
  - `scale` → float scaling factor for currency adjustments  
- **Purpose**: Provides per-security parameters needed for trade settlement.  

---

## Key Lifecycle

1. **Placing an order**  
   - New orders are added to `user:{player_id}:security:{sec_id}:orders` and to the relevant `:bids` or `:asks` set.  
   - Order details go into `{orderbook_key}:{order_id}`.  
   - `orderbook` hash updated with net volume at that price.  

2. **Matching orders**  
   - Orders are matched against the opposite side (`bids` vs. `asks`).  
   - If an order is fully filled, it is removed from all sets and deleted.  
   - If partially filled, its `amount` field is updated.  

3. **Cancelling orders**  
   - Removes entries from both the orderbook side set and the user’s order set.  
   - Deletes the `{orderbook_key}:{order_id}`.  
   - Adjusts the aggregate `orderbook` hash volume.  

