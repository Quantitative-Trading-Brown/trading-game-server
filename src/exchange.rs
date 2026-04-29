use std::cmp::Reverse;
use std::collections::HashMap;

use crate::models::{Game, Order, Player, Security, Side, State, Trade};

// ---------------------------------------------------------------------------
// Effects accumulated during an exchange operation, flushed at the end.
// ---------------------------------------------------------------------------

struct Effects {
    /// player_id -> cash delta
    cash: HashMap<String, f64>,
    /// player_id -> qty delta (for the single security being traded)
    inventory: HashMap<String, i64>,
    /// player_id -> list of deleted order ids
    deleted: HashMap<String, Vec<String>>,
    /// player_id -> order_id -> (qty_change, new_qty)
    modified: HashMap<String, Vec<(String, i64, i64)>>,
    /// player_id -> list of new Order snapshots
    created: HashMap<String, Vec<Order>>,
    /// display orderbook deltas: price -> signed qty change
    display_deltas: HashMap<i64, i64>,
    /// trades executed
    trades: Vec<Trade>,
}

impl Effects {
    fn new() -> Self {
        Self {
            cash: HashMap::new(),
            inventory: HashMap::new(),
            deleted: HashMap::new(),
            modified: HashMap::new(),
            created: HashMap::new(),
            display_deltas: HashMap::new(),
            trades: Vec::new(),
        }
    }
}

// ---------------------------------------------------------------------------
// Public entry points
// ---------------------------------------------------------------------------

pub fn process_limit_order(
    state: &mut State,
    game_id: &str,
    issuer_id: &str,
    sec_id: &str,
    side: Side,
    price: i64,
    quantity: i64,
) {
    let mut fx = Effects::new();
    let mut remaining = quantity;

    // Match against opposite side
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    let opp_ids = collect_opposite_orders(game, sec_id, side);

    for opp_order_id in opp_ids {
        if remaining <= 0 {
            break;
        }
        let game = match state.games.get(game_id) {
            Some(g) => g,
            None => return,
        };
        let opp = match game.orders.get(&opp_order_id) {
            Some(o) => o.clone(),
            None => continue,
        };

        // Check price compatibility
        match side {
            Side::Bid => {
                if opp.price > price {
                    break; // best ask is above our bid limit
                }
            }
            Side::Ask => {
                if opp.price < price {
                    break; // best bid is below our ask limit
                }
            }
        }

        let filled = execute_trade(
            state,
            game_id,
            &opp_order_id,
            issuer_id,
            remaining,
            &mut fx,
        );
        remaining -= filled;
    }

    // Place residual as new order
    if remaining > 0 {
        let game = state.games.get_mut(game_id).unwrap();
        let order_id = game.next_order_id();
        let order = Order {
            id: order_id.clone(),
            security: sec_id.to_string(),
            side,
            price,
            quantity: remaining,
            issuer_id: issuer_id.to_string(),
        };
        insert_order(game, &order);

        if let Some(player) = state.players.get_mut(issuer_id) {
            player.orders.insert(order_id.clone());
        }

        fx.created
            .entry(issuer_id.to_string())
            .or_default()
            .push(order);
    }

    apply_effects(state, game_id, sec_id, fx);
}

pub fn process_market_order(
    state: &mut State,
    game_id: &str,
    issuer_id: &str,
    sec_id: &str,
    side: Side,
    quantity: i64,
) {
    let mut fx = Effects::new();
    let mut remaining = quantity;

    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    let opp_ids = collect_opposite_orders(game, sec_id, side);

    for opp_order_id in opp_ids {
        if remaining <= 0 {
            break;
        }

        let filled = execute_trade(
            state,
            game_id,
            &opp_order_id,
            issuer_id,
            remaining,
            &mut fx,
        );
        remaining -= filled;
    }

    apply_effects(state, game_id, sec_id, fx);
}

pub fn cancel_order(state: &mut State, game_id: &str, issuer_id: &str, order_id: &str) {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    let order = match game.orders.get(order_id) {
        Some(o) => o.clone(),
        None => return,
    };

    // Verify the caller owns this order
    if order.issuer_id != issuer_id {
        return;
    }

    let sec_id = order.security.clone();
    let mut fx = Effects::new();

    remove_order_from_book(state.games.get_mut(game_id).unwrap(), &order);

    if let Some(player) = state.players.get_mut(issuer_id) {
        player.orders.remove(order_id);
    }

    fx.deleted
        .entry(issuer_id.to_string())
        .or_default()
        .push(order_id.to_string());

    apply_effects(state, game_id, &sec_id, fx);
}

pub fn cancel_all_orders(state: &mut State, game_id: &str, issuer_id: &str) {
    let order_ids: Vec<String> = if issuer_id.starts_with("_bot_") {
        // Bot orders: scan game orders
        let game = match state.games.get(game_id) {
            Some(g) => g,
            None => return,
        };
        game.orders
            .values()
            .filter(|o| o.issuer_id == issuer_id)
            .map(|o| o.id.clone())
            .collect()
    } else {
        match state.players.get(issuer_id) {
            Some(p) => p.orders.iter().cloned().collect(),
            None => return,
        }
    };

    // Group by security for batch effects
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    let mut by_sec: HashMap<String, Vec<String>> = HashMap::new();
    for oid in &order_ids {
        if let Some(order) = game.orders.get(oid) {
            by_sec
                .entry(order.security.clone())
                .or_default()
                .push(oid.clone());
        }
    }

    for (sec_id, oids) in by_sec {
        let mut fx = Effects::new();
        for oid in &oids {
            let game = state.games.get(game_id).unwrap();
            let order = match game.orders.get(oid) {
                Some(o) => o.clone(),
                None => continue,
            };
            remove_order_from_book(state.games.get_mut(game_id).unwrap(), &order);
        }

        if let Some(player) = state.players.get_mut(issuer_id) {
            for oid in &oids {
                player.orders.remove(oid);
            }
        }

        fx.deleted
            .entry(issuer_id.to_string())
            .or_default()
            .extend(oids);

        apply_effects(state, game_id, &sec_id, fx);
    }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Collect order IDs from the opposite side of the book, in price-time priority order.
fn collect_opposite_orders(game: &Game, sec_id: &str, aggressor_side: Side) -> Vec<String> {
    let sec = match game.securities.get(sec_id) {
        Some(s) => s,
        None => return Vec::new(),
    };

    let mut ids = Vec::new();
    match aggressor_side {
        Side::Bid => {
            // aggressor is buying -> match against asks (lowest first)
            for (_price, queue) in &sec.asks {
                for oid in queue {
                    ids.push(oid.clone());
                }
            }
        }
        Side::Ask => {
            // aggressor is selling -> match against bids (highest first)
            for (Reverse(_price), queue) in &sec.bids {
                for oid in queue {
                    ids.push(oid.clone());
                }
            }
        }
    }
    ids
}

/// Execute a single fill against a resting order. Returns quantity filled.
fn execute_trade(
    state: &mut State,
    game_id: &str,
    resting_order_id: &str,
    initiator_id: &str,
    requested_qty: i64,
    fx: &mut Effects,
) -> i64 {
    let game = state.games.get(game_id).unwrap();
    let resting = match game.orders.get(resting_order_id) {
        Some(o) => o.clone(),
        None => return 0,
    };

    let fill_qty = requested_qty.min(resting.quantity);
    let fill_price = resting.price;

    // Determine buyer / seller
    let (buyer_id, seller_id) = match resting.side {
        Side::Ask => (initiator_id.to_string(), resting.issuer_id.clone()),
        Side::Bid => (resting.issuer_id.clone(), initiator_id.to_string()),
    };

    // Cash
    *fx.cash.entry(buyer_id.clone()).or_default() -= (fill_price as f64) * (fill_qty as f64);
    *fx.cash.entry(seller_id.clone()).or_default() += (fill_price as f64) * (fill_qty as f64);

    // Inventory
    *fx.inventory.entry(buyer_id.clone()).or_default() += fill_qty;
    *fx.inventory.entry(seller_id.clone()).or_default() -= fill_qty;

    // Trade record
    fx.trades.push(Trade {
        timestamp: chrono::Local::now().format("%H:%M:%S").to_string(),
        security: resting.security.clone(),
        buyer_id: buyer_id.clone(),
        seller_id: seller_id.clone(),
        price: fill_price,
        quantity: fill_qty,
    });

    // Update or remove the resting order
    if resting.quantity > fill_qty {
        // Partial fill
        let new_qty = resting.quantity - fill_qty;
        let game = state.games.get_mut(game_id).unwrap();
        if let Some(order) = game.orders.get_mut(resting_order_id) {
            order.quantity = new_qty;
        }
        fx.modified
            .entry(resting.issuer_id.clone())
            .or_default()
            .push((resting_order_id.to_string(), -fill_qty, new_qty));

        // Display delta
        let mult = if resting.side == Side::Bid { 1 } else { -1 };
        *fx.display_deltas.entry(fill_price).or_default() -= fill_qty * mult;
    } else {
        // Full fill — remove from book
        remove_order_from_book(state.games.get_mut(game_id).unwrap(), &resting);

        if let Some(player) = state.players.get_mut(&resting.issuer_id) {
            player.orders.remove(resting_order_id);
        }

        fx.deleted
            .entry(resting.issuer_id.clone())
            .or_default()
            .push(resting_order_id.to_string());
    }

    fill_qty
}

fn insert_order(game: &mut Game, order: &Order) {
    let sec = game.securities.get_mut(&order.security).unwrap();

    match order.side {
        Side::Bid => {
            sec.bids
                .entry(Reverse(order.price))
                .or_default()
                .push_back(order.id.clone());
            let mult = 1;
            *sec.display.entry(order.price).or_default() += order.quantity * mult;
            *sec.pending_updates.entry(order.price).or_default() += order.quantity * mult;
        }
        Side::Ask => {
            sec.asks
                .entry(order.price)
                .or_default()
                .push_back(order.id.clone());
            let mult = -1;
            *sec.display.entry(order.price).or_default() += order.quantity * mult;
            *sec.pending_updates.entry(order.price).or_default() += order.quantity * mult;
        }
    }

    game.orders.insert(order.id.clone(), order.clone());
}

fn remove_order_from_book(game: &mut Game, order: &Order) {
    let sec = game.securities.get_mut(&order.security).unwrap();

    match order.side {
        Side::Bid => {
            if let Some(queue) = sec.bids.get_mut(&Reverse(order.price)) {
                queue.retain(|id| id != &order.id);
                if queue.is_empty() {
                    sec.bids.remove(&Reverse(order.price));
                }
            }
            let delta = -(order.quantity);
            *sec.display.entry(order.price).or_default() += delta;
            *sec.pending_updates.entry(order.price).or_default() += delta;
            if sec.display.get(&order.price) == Some(&0) {
                sec.display.remove(&order.price);
            }
        }
        Side::Ask => {
            if let Some(queue) = sec.asks.get_mut(&order.price) {
                queue.retain(|id| id != &order.id);
                if queue.is_empty() {
                    sec.asks.remove(&order.price);
                }
            }
            let delta = order.quantity;
            *sec.display.entry(order.price).or_default() += delta;
            *sec.pending_updates.entry(order.price).or_default() += delta;
            if sec.display.get(&order.price) == Some(&0) {
                sec.display.remove(&order.price);
            }
        }
    }

    game.orders.remove(&order.id);
}

// ---------------------------------------------------------------------------
// Apply effects: update player state + emit messages
// ---------------------------------------------------------------------------

fn apply_effects(state: &mut State, game_id: &str, sec_id: &str, fx: Effects) {
    let game = state.games.get_mut(game_id).unwrap();
    game.trades.extend(fx.trades);

    // Apply display deltas from partial fills
    if let Some(sec) = game.securities.get_mut(sec_id) {
        for (price, delta) in &fx.display_deltas {
            *sec.display.entry(*price).or_default() += delta;
            *sec.pending_updates.entry(*price).or_default() += delta;
            if sec.display.get(price) == Some(&0) {
                sec.display.remove(price);
            }
        }
    }

    // Apply cash & inventory changes, send inventory updates
    let all_traders: Vec<String> = fx
        .cash
        .keys()
        .chain(fx.inventory.keys())
        .cloned()
        .collect::<std::collections::HashSet<_>>()
        .into_iter()
        .collect();

    for trader_id in &all_traders {
        if trader_id.starts_with("_bot_") {
            continue;
        }
        let player = match state.players.get_mut(trader_id.as_str()) {
            Some(p) => p,
            None => continue,
        };

        if let Some(&cash_delta) = fx.cash.get(trader_id) {
            player.cash += cash_delta;
        }
        if let Some(&inv_delta) = fx.inventory.get(trader_id) {
            *player.inventory.entry(sec_id.to_string()).or_default() += inv_delta;
        }

        // Recalc position value & margin
        mark_positions(player, state.games.get(game_id).unwrap());

        // Send inventory update
        let inv_msg = serde_json::json!({
            "cash": player.cash,
            "position_value": player.position_value,
            "margin": player.margin,
            "securities": { sec_id: player.inventory.get(sec_id).copied().unwrap_or(0) },
        });
        state.send_to_player(trader_id, "inventory", inv_msg);
    }

    // Send consolidated order updates (one message per trader with all changes)
    let all_trader_ids: std::collections::HashSet<&String> = fx
        .deleted
        .keys()
        .chain(fx.modified.keys())
        .chain(fx.created.keys())
        .collect();

    for trader_id in all_trader_ids {
        if trader_id.starts_with("_bot_") {
            continue;
        }

        let mut update = serde_json::Map::new();

        if let Some(deleted_ids) = fx.deleted.get(trader_id.as_str()) {
            update.insert("deleted".to_string(), serde_json::json!(deleted_ids));
        }

        if let Some(mods) = fx.modified.get(trader_id.as_str()) {
            let mods_map: HashMap<&str, serde_json::Value> = mods
                .iter()
                .map(|(oid, qty_change, new_qty)| {
                    (oid.as_str(), serde_json::json!([qty_change, new_qty]))
                })
                .collect();
            update.insert("modified".to_string(), serde_json::json!(mods_map));
        }

        if let Some(new_orders) = fx.created.get(trader_id.as_str()) {
            let new_map: HashMap<&str, serde_json::Value> = new_orders
                .iter()
                .map(|o| {
                    (
                        o.id.as_str(),
                        serde_json::json!({
                            "security": o.security,
                            "side": match o.side { Side::Bid => "bids", Side::Ask => "asks" },
                            "price": o.price,
                            "quantity": o.quantity,
                            "issuer_id": o.issuer_id,
                        }),
                    )
                })
                .collect();
            update.insert("new".to_string(), serde_json::json!(new_map));
        }

        if !update.is_empty() {
            state.send_to_player(trader_id, "order_update", serde_json::Value::Object(update));
        }
    }
}

// ---------------------------------------------------------------------------
// Position marking (shared with game.rs tick loop)
// ---------------------------------------------------------------------------

pub fn mark_positions(player: &mut Player, game: &Game) {
    let mut pv = 0.0f64;
    let mut margin = 0.0f64;

    for (sec_id, &qty) in &player.inventory {
        let sec = match game.securities.get(sec_id) {
            Some(s) => s,
            None => continue,
        };
        let price = sec.price;
        pv += (qty as f64) * price;

        let margin_rate = if qty >= 0 {
            sec.long_margin
        } else {
            sec.short_margin
        };
        margin += (qty as f64).abs() * price * margin_rate;
    }

    player.position_value = pv;
    player.margin = margin;
}

// ---------------------------------------------------------------------------
// Price calculation (mid or one-sided)
// ---------------------------------------------------------------------------

pub fn compute_price(sec: &Security) -> f64 {
    let best_bid = sec.bids.keys().next().map(|Reverse(p)| *p);
    let best_ask = sec.asks.keys().next().map(|p| *p);

    match (best_bid, best_ask) {
        (Some(b), Some(a)) => ((b + a) as f64) / 2.0,
        (Some(b), None) => b as f64,
        (None, Some(a)) => a as f64,
        (None, None) => 0.0,
    }
}
