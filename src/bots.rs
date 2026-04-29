use std::collections::HashMap;

use crate::exchange;
use crate::models::{BotDef, Side, State, TickData};

use rand::Rng;

// ---------------------------------------------------------------------------
// Bot trait
// ---------------------------------------------------------------------------

pub trait Bot: Send {
    fn place_orders(
        &mut self,
        tick: u64,
        orderbook_display: &HashMap<i64, i64>,
    ) -> Vec<(Side, i64, i64)>; // (side, price, quantity)
}

// ---------------------------------------------------------------------------
// MarketSimulator — builds a realistic, dynamic orderbook around a reference
// price series. Features:
//   - Multiple price levels with depth curve (thin near spread, thick further)
//   - Noise on sizes and prices
//   - Dynamic spread: widens after large net player flow, tightens when calm
//   - Momentum-aware: thinner depth on the side price is moving toward
// ---------------------------------------------------------------------------

pub struct MarketSimulator {
    series: Vec<f64>,
    /// Number of price levels on each side
    levels: usize,
    /// Base spread half-width (ticks from mid to best bid/ask)
    base_half_spread: i64,
    /// Spacing between price levels
    tick_size: i64,
    /// Base quantity at the best level
    base_qty: i64,
    /// How much qty grows per level away from mid (multiplier per level)
    depth_growth: f64,
    /// Tracks net order flow from players to widen/tighten spread
    net_flow: f64,
    /// Flow decay rate per bot tick (0..1, higher = faster decay)
    flow_decay: f64,
    /// How much flow widens the spread (spread_addition = flow_impact * |net_flow|)
    flow_impact: f64,
    /// Previous reference price for momentum detection
    prev_price: f64,
}

impl MarketSimulator {
    pub fn new(tick_data: &TickData, settings: &serde_json::Value) -> Self {
        let col = settings["price_col"].as_str().unwrap_or("price");
        let series: Vec<f64> = tick_data
            .columns
            .get(col)
            .map(|v| v.iter().filter_map(|s| s.parse().ok()).collect())
            .unwrap_or_default();

        Self {
            series,
            levels: settings["levels"].as_u64().unwrap_or(5) as usize,
            base_half_spread: settings["half_spread"].as_i64().unwrap_or(3),
            tick_size: settings["tick_size"].as_i64().unwrap_or(1),
            base_qty: settings["base_qty"].as_i64().unwrap_or(500),
            depth_growth: settings["depth_growth"].as_f64().unwrap_or(1.5),
            flow_impact: settings["flow_impact"].as_f64().unwrap_or(0.02),
            flow_decay: settings["flow_decay"].as_f64().unwrap_or(0.7),
            prev_price: 0.0,
            net_flow: 0.0,
        }
    }

    /// Measure net player flow from the current orderbook.
    /// Positive = more buy pressure, negative = more sell pressure.
    fn measure_flow(&self, orderbook: &HashMap<i64, i64>) -> f64 {
        let mut bid_depth: i64 = 0;
        let mut ask_depth: i64 = 0;
        for (_, &qty) in orderbook {
            if qty > 0 {
                bid_depth += qty;
            } else {
                ask_depth += qty.abs();
            }
        }
        // Imbalance: how much more bid vs ask depth exists
        (bid_depth - ask_depth) as f64
    }
}

impl Bot for MarketSimulator {
    fn place_orders(
        &mut self,
        tick: u64,
        orderbook: &HashMap<i64, i64>,
    ) -> Vec<(Side, i64, i64)> {
        let idx = tick as usize;
        if idx >= self.series.len() {
            return Vec::new();
        }

        let target = self.series[idx];
        let mid = target as i64;
        let mut rng = rand::rng();

        // Update flow tracking
        let current_flow = self.measure_flow(orderbook);
        self.net_flow = self.net_flow * self.flow_decay + current_flow * (1.0 - self.flow_decay);

        // Dynamic spread: widen when flow is high
        let flow_spread = (self.net_flow.abs() * self.flow_impact) as i64;
        let half_spread = self.base_half_spread + flow_spread;

        // Momentum: detect price direction
        let momentum = if self.prev_price > 0.0 {
            target - self.prev_price
        } else {
            0.0
        };
        self.prev_price = target;

        // Momentum skew: thin the side price is moving toward
        // positive momentum (price going up) -> thin asks, thick bids
        let momentum_factor = (momentum / (self.base_half_spread as f64)).clamp(-0.6, 0.6);

        let best_bid = mid - half_spread;
        let best_ask = mid + half_spread;

        let mut orders = Vec::new();

        for level in 0..self.levels {
            let level_f = level as f64;

            // Depth curve: grows exponentially away from mid
            let depth_mult = self.depth_growth.powf(level_f);

            // Noise: ±30% on quantity
            let noise_bid = rng.random_range(0.7..=1.3);
            let noise_ask = rng.random_range(0.7..=1.3);

            // Momentum skew on quantity
            // Price going up -> bids get thicker (support), asks get thinner
            let bid_skew = 1.0 + momentum_factor;  // >1 when price rising
            let ask_skew = 1.0 - momentum_factor;  // >1 when price falling

            let bid_qty = ((self.base_qty as f64) * depth_mult * noise_bid * bid_skew) as i64;
            let ask_qty = ((self.base_qty as f64) * depth_mult * noise_ask * ask_skew) as i64;

            // Price noise: ±1 tick at each level
            let price_noise_bid: i64 = rng.random_range(-1..=1);
            let price_noise_ask: i64 = rng.random_range(-1..=1);

            let bid_price = best_bid - (level as i64) * self.tick_size + price_noise_bid;
            let ask_price = best_ask + (level as i64) * self.tick_size + price_noise_ask;

            if bid_qty > 0 {
                orders.push((Side::Bid, bid_price.max(1), bid_qty));
            }
            if ask_qty > 0 {
                orders.push((Side::Ask, ask_price.max(1), ask_qty));
            }
        }

        orders
    }
}

// ---------------------------------------------------------------------------
// BotManager
// ---------------------------------------------------------------------------

pub struct BotManager {
    pub game_id: String,
    pub bots: Vec<(String, String, Box<dyn Bot>)>, // (name, security, bot)
}

impl BotManager {
    pub fn new(game_id: &str, tick_data: &TickData, bot_defs: &[(String, BotDef)]) -> Self {
        let bots = bot_defs
            .iter()
            .filter_map(|(name, def)| {
                let bot: Box<dyn Bot> = Box::new(MarketSimulator::new(tick_data, &def.settings));
                Some((name.clone(), def.security.clone(), bot))
            })
            .collect();

        Self {
            game_id: game_id.to_string(),
            bots,
        }
    }

    pub fn run(&mut self, state: &mut State, tick: u64) {

        let bot_trader_id = format!("_bot_{}", self.game_id);

        // Cancel all existing bot orders
        exchange::cancel_all_orders(state, &self.game_id, &bot_trader_id);

        // Place new quotes
        for (_name, security, bot) in &mut self.bots {
            let display = state
                .games
                .get(&self.game_id)
                .and_then(|g| g.securities.get(security))
                .map(|s| s.display.clone())
                .unwrap_or_default();

            for (side, price, qty) in bot.place_orders(tick, &display) {
                exchange::process_limit_order(
                    state,
                    &self.game_id,
                    &bot_trader_id,
                    security,
                    side,
                    price,
                    qty,
                );
            }
        }
    }
}
