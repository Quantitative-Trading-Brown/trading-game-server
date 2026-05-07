use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};
use std::cmp::Reverse;
use std::time::Instant;

use serde::{Deserialize, Serialize};
use tokio::sync::mpsc::UnboundedSender;

// ---------------------------------------------------------------------------
// Top-level application state (lives behind Arc<Mutex<State>>)
// ---------------------------------------------------------------------------

pub struct State {
    // Global counters
    pub game_count: u64,
    pub player_count: u64,

    // Auth mappings
    pub codes: HashMap<String, String>,           // join-code  -> game_id
    pub player_tokens: HashMap<String, String>,   // player_id  -> token
    pub admin_tokens: HashMap<String, String>,     // game_id    -> token

    // Core data
    pub games: HashMap<String, Game>,
    pub players: HashMap<String, Player>,

    // WebSocket senders  (player_id -> tx, game_id -> vec of admin tx)
    pub player_senders: HashMap<String, WsSender>,
    pub admin_senders: HashMap<String, Vec<WsSender>>,
}

/// Wrapper so we can identify a sender for cleanup.
pub struct WsSender {
    pub conn_id: String,
    pub tx: UnboundedSender<String>,
}

impl State {
    pub fn new() -> Self {
        Self {
            game_count: 0,
            player_count: 0,
            codes: HashMap::new(),
            player_tokens: HashMap::new(),
            admin_tokens: HashMap::new(),
            games: HashMap::new(),
            players: HashMap::new(),
            player_senders: HashMap::new(),
            admin_senders: HashMap::new(),
        }
    }

    // ---- send helpers ----

    pub fn send_to_player(&self, player_id: &str, event: &str, data: serde_json::Value) {
        if let Some(ws) = self.player_senders.get(player_id) {
            let msg = serde_json::json!({"event": event, "data": data});
            let _ = ws.tx.send(msg.to_string());
        }
    }

    pub fn send_to_admins(&self, game_id: &str, event: &str, data: serde_json::Value) {
        if let Some(senders) = self.admin_senders.get(game_id) {
            let msg = serde_json::json!({"event": event, "data": data}).to_string();
            for ws in senders {
                let _ = ws.tx.send(msg.clone());
            }
        }
    }

    pub fn broadcast(&self, game_id: &str, event: &str, data: serde_json::Value) {
        if let Some(game) = self.games.get(game_id) {
            for pid in &game.players {
                self.send_to_player(pid, event, data.clone());
            }
        }
        self.send_to_admins(game_id, event, data);
    }
}

// ---------------------------------------------------------------------------
// Game
// ---------------------------------------------------------------------------

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum GamePhase {
    Setup = 0,
    Live = 1,
    Settlement = 2,
    Results = 3,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GameConfig {
    pub game_ticks: u64,
    pub tick_length_secs: f64,
    pub initial_cash: f64,
    pub margin_call_ticks: u32,
    pub allowed_bankruptcies: u32,
    pub sell_liquidation_fraction: f64,
    pub buy_liquidation_fraction: f64,
}

impl Default for GameConfig {
    fn default() -> Self {
        Self {
            game_ticks: 100,
            tick_length_secs: 1.0,
            initial_cash: 100_000.0,
            margin_call_ticks: 3,
            allowed_bankruptcies: 3,
            sell_liquidation_fraction: 0.5,
            buy_liquidation_fraction: 1.5,
        }
    }
}

/// Max time a game can exist regardless of activity (2 hours).
pub const MAX_GAME_LIFETIME_SECS: u64 = 2 * 60 * 60;
/// Max inactivity before a game is reaped (30 minutes).
pub const MAX_INACTIVITY_SECS: u64 = 30 * 60;

#[derive(Serialize, Deserialize)]
pub struct Game {
    pub id: String,
    pub code: String,
    pub phase: GamePhase,
    pub allow_join: bool,
    pub config: GameConfig,

    pub securities: HashMap<String, Security>,
    pub players: Vec<String>,              // all player ids (insertion order)
    pub active_players: HashSet<String>,

    pub news: VecDeque<NewsEntry>,
    pub trades: Vec<Trade>,
    pub order_count: u64,
    pub orders: HashMap<String, Order>,

    /// When the game was created.
    #[serde(skip, default = "Instant::now")]
    pub created_at: Instant,
    /// Last time any player or admin interacted with this game.
    #[serde(skip, default = "Instant::now")]
    pub last_activity: Instant,
}

impl Game {
    pub fn new(id: String, code: String) -> Self {
        let now = Instant::now();
        Self {
            id,
            code,
            phase: GamePhase::Setup,
            allow_join: true,
            config: GameConfig::default(),
            securities: HashMap::new(),
            players: Vec::new(),
            active_players: HashSet::new(),
            news: VecDeque::new(),
            trades: Vec::new(),
            order_count: 0,
            orders: HashMap::new(),
            created_at: now,
            last_activity: now,
        }
    }

    /// Update the last activity timestamp (call on any player/admin action).
    pub fn touch(&mut self) {
        self.last_activity = Instant::now();
    }

    pub fn next_order_id(&mut self) -> String {
        self.order_count += 1;
        format!("{:010}", self.order_count)
    }
}

// ---------------------------------------------------------------------------
// Security & OrderBook
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Security {
    pub name: String,
    pub long_margin: f64,
    pub short_margin: f64,
    /// Extra properties from the preset (forwarded to clients).
    pub extra: HashMap<String, serde_json::Value>,

    pub bids: BTreeMap<Reverse<i64>, VecDeque<String>>,  // best (highest) first
    pub asks: BTreeMap<i64, VecDeque<String>>,            // best (lowest) first

    /// Display orderbook: price -> signed qty (positive = bid depth, negative = ask depth)
    pub display: HashMap<i64, i64>,
    /// Accumulated during a tick, flushed to clients at tick end.
    #[serde(skip)]
    pub pending_updates: HashMap<i64, i64>,

    pub price: f64,
}

impl Security {
    pub fn new(name: String, long_margin: f64, short_margin: f64) -> Self {
        Self {
            name,
            long_margin,
            short_margin,
            extra: HashMap::new(),
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
            display: HashMap::new(),
            pending_updates: HashMap::new(),
            price: 0.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Order
// ---------------------------------------------------------------------------

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Side {
    Bid,
    Ask,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Order {
    pub id: String,
    pub security: String,
    pub side: Side,
    pub price: i64,
    pub quantity: i64,
    pub issuer_id: String,
}

// ---------------------------------------------------------------------------
// Player
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Player {
    pub id: String,
    pub username: String,
    pub game_id: String,
    pub cash: f64,
    pub inventory: HashMap<String, i64>,   // sec_id -> qty
    pub position_value: f64,
    pub margin: f64,
    pub orders: HashSet<String>,
    pub warning_ticks: u32,
    pub bankruptcies: u32,
    pub active: bool,
    pub score: f64,
}

impl Player {
    pub fn new(id: String, username: String, game_id: String) -> Self {
        Self {
            id,
            username,
            game_id,
            cash: 0.0,
            inventory: HashMap::new(),
            position_value: 0.0,
            margin: 0.0,
            orders: HashSet::new(),
            warning_ticks: 0,
            bankruptcies: 0,
            active: true,
            score: 0.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Trade & News
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Trade {
    pub timestamp: String,
    pub security: String,
    pub buyer_id: String,
    pub seller_id: String,
    pub price: i64,
    pub quantity: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NewsEntry {
    pub timestamp: String,
    pub message: String,
}

// ---------------------------------------------------------------------------
// Preset / tick-data structures (loaded from disk, not stored in State)
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Deserialize)]
pub struct PresetMeta {
    pub name: String,
    pub description: Option<String>,
    pub file: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct PresetConfig {
    pub game_ticks: Option<u64>,
    pub tick_length: Option<f64>,
    pub tick_data: Option<String>,
    pub news_col: Option<String>,
    pub initial_cash: Option<f64>,
    pub allowed_bankruptcies: Option<u32>,
    pub margin_call_ticks: Option<u32>,
    pub sell_liquidation_fraction: Option<f64>,
    pub buy_liquidation_fraction: Option<f64>,
    pub securities: Option<HashMap<String, SecurityDef>>,
    pub bots: Option<serde_json::Value>,  // can be array [] or object {}
}

#[derive(Clone, Debug, Deserialize)]
pub struct SecurityDef {
    pub name: Option<String>,
    pub long_margin: Option<f64>,
    pub short_margin: Option<f64>,
}

/// Column-oriented tick data loaded from CSV.
#[derive(Clone, Debug)]
pub struct TickData {
    pub columns: HashMap<String, Vec<String>>,
}

impl TickData {
    pub fn get_str(&self, col: &str, row: usize) -> Option<&str> {
        self.columns.get(col)?.get(row).map(|s| s.as_str())
    }
}

// ---------------------------------------------------------------------------
// Bot config (parsed from preset JSON)
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Deserialize)]
pub struct BotDef {
    pub security: String,
    pub settings: serde_json::Value,
}
