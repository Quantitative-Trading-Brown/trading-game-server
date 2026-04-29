use std::sync::{Arc, Mutex};

use axum::extract::ws::{Message, WebSocket};
use axum::extract::{Query, State as AxumState, WebSocketUpgrade};
use axum::response::IntoResponse;
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use tokio::sync::mpsc;

use crate::backup;
use crate::config::Config;
use crate::exchange;
use crate::game;
use crate::models::{self, Side, WsSender};

pub type AppState = Arc<Mutex<models::State>>;

#[derive(Deserialize)]
pub struct WsQuery {
    pub token: String,
}

// ---------------------------------------------------------------------------
// Upgrade handlers
// ---------------------------------------------------------------------------

pub async fn player_ws(
    ws: WebSocketUpgrade,
    AxumState((app, cfg)): AxumState<(AppState, Arc<Config>)>,
    Query(q): Query<WsQuery>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_player(socket, app, cfg, q.token))
}

pub async fn admin_ws(
    ws: WebSocketUpgrade,
    AxumState((app, cfg)): AxumState<(AppState, Arc<Config>)>,
    Query(q): Query<WsQuery>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_admin(socket, app, cfg, q.token))
}

// ---------------------------------------------------------------------------
// Player connection
// ---------------------------------------------------------------------------

async fn handle_player(socket: WebSocket, app: AppState, _cfg: Arc<Config>, token: String) {
    let (tx, mut rx) = mpsc::unbounded_channel::<String>();

    let player_id = {
        let mut state = app.lock().unwrap();
        let id = match game::verify_token(&state, &token) {
            Some(("player", id)) => id,
            _ => return,
        };

        if !state.players.contains_key(&id) {
            return;
        }

        let conn_id = format!("p-{id}");
        state
            .player_senders
            .insert(id.clone(), WsSender { conn_id, tx });

        id
    };

    let (mut ws_tx, mut ws_rx) = socket.split();

    // Forward channel -> websocket
    let send_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if ws_tx.send(Message::Text(msg.into())).await.is_err() {
                break;
            }
        }
    });

    // Read websocket -> dispatch
    let app_clone = app.clone();
    let pid = player_id.clone();
    let recv_task = tokio::spawn(async move {
        while let Some(Ok(msg)) = ws_rx.next().await {
            match msg {
                Message::Text(text) => {
                    dispatch_player_message(&app_clone, &pid, &text);
                }
                Message::Close(_) => break,
                _ => {}
            }
        }
    });

    tokio::select! {
        _ = send_task => {}
        _ = recv_task => {}
    }

    // Cleanup
    {
        let mut state = app.lock().unwrap();
        state.player_senders.remove(&player_id);
        // Player disconnected but still exists in game
    }
}

// ---------------------------------------------------------------------------
// Admin connection
// ---------------------------------------------------------------------------

async fn handle_admin(socket: WebSocket, app: AppState, cfg: Arc<Config>, token: String) {
    let (tx, mut rx) = mpsc::unbounded_channel::<String>();

    let (game_id, conn_id) = {
        let mut state = app.lock().unwrap();
        let gid = match game::verify_token(&state, &token) {
            Some(("admin", id)) => id,
            _ => return,
        };

        let cid = format!("a-{gid}-{}", rand::random::<u32>());
        state
            .admin_senders
            .entry(gid.clone())
            .or_default()
            .push(WsSender {
                conn_id: cid.clone(),
                tx,
            });

        (gid, cid)
    };

    let (mut ws_tx, mut ws_rx) = socket.split();

    let send_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if ws_tx.send(Message::Text(msg.into())).await.is_err() {
                break;
            }
        }
    });

    let app_clone = app.clone();
    let gid = game_id.clone();
    let cfg_clone = cfg.clone();
    let recv_task = tokio::spawn(async move {
        while let Some(Ok(msg)) = ws_rx.next().await {
            match msg {
                Message::Text(text) => {
                    dispatch_admin_message(&app_clone, &gid, &text, &cfg_clone);
                }
                Message::Close(_) => break,
                _ => {}
            }
        }
    });

    tokio::select! {
        _ = send_task => {}
        _ = recv_task => {}
    }

    // Cleanup: remove this specific admin sender
    {
        let mut state = app.lock().unwrap();
        if let Some(senders) = state.admin_senders.get_mut(&game_id) {
            senders.retain(|s| s.conn_id != conn_id);
        }
    }
}

// ---------------------------------------------------------------------------
// Message dispatch
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct WsMessage {
    event: String,
    #[serde(default)]
    data: serde_json::Value,
}

fn dispatch_player_message(app: &AppState, player_id: &str, raw: &str) {
    let msg: WsMessage = match serde_json::from_str(raw) {
        Ok(m) => m,
        Err(_) => return,
    };

    let mut state = app.lock().unwrap();

    let game_id = match state.players.get(player_id) {
        Some(p) => p.game_id.clone(),
        None => return,
    };

    match msg.event.as_str() {
        "market_order" => {
            if !is_active(&state, player_id) {
                return;
            }
            let sec_id = msg.data["sec_id"].as_str().unwrap_or_default().to_string();
            let side = parse_side(msg.data["side"].as_str().unwrap_or_default());
            let qty = msg.data["quantity"].as_i64().unwrap_or(1).max(1);
            exchange::process_market_order(&mut state, &game_id, player_id, &sec_id, side, qty);
        }
        "limit_order" => {
            if !is_active(&state, player_id) {
                return;
            }
            let sec_id = msg.data["sec_id"].as_str().unwrap_or_default().to_string();
            let side = parse_side(msg.data["side"].as_str().unwrap_or_default());
            let price = msg.data["price"].as_i64().unwrap_or(0).max(0);
            let qty = msg.data["quantity"].as_i64().unwrap_or(1).max(1);
            exchange::process_limit_order(
                &mut state, &game_id, player_id, &sec_id, side, price, qty,
            );
        }
        "cancel" => {
            if !is_active(&state, player_id) {
                return;
            }
            let order_id = msg.data["order_id"]
                .as_str()
                .unwrap_or_default()
                .to_string();
            exchange::cancel_order(&mut state, &game_id, player_id, &order_id);
        }
        "cancel_all" => {
            if !is_active(&state, player_id) {
                return;
            }
            exchange::cancel_all_orders(&mut state, &game_id, player_id);
        }
        "snapshot" => {
            let snap = game::build_player_snapshot(&state, &game_id, player_id);
            state.send_to_player(player_id, "snapshot", snap);
        }
        "leaderboard" => {
            let lb = game::build_leaderboard(&state, &game_id);
            state.send_to_player(player_id, "leaderboard", lb);
        }
        "news" => {
            let message = msg.data["message"].as_str().unwrap_or_default();
            if !message.is_empty() {
                game::broadcast_news(&mut state, &game_id, message);
            }
        }
        _ => {}
    }
}

fn dispatch_admin_message(app: &AppState, game_id: &str, raw: &str, cfg: &Config) {
    let msg: WsMessage = match serde_json::from_str(raw) {
        Ok(m) => m,
        Err(_) => return,
    };

    match msg.event.as_str() {
        "startgame" => {
            let preset_id = msg.data["preset"].as_str().unwrap_or_default().to_string();
            let allow_join = msg.data["allow_join"].as_bool().unwrap_or(true);

            // Load preset data (file I/O — do outside lock)
            let preset_index = crate::config::load_preset_index(&cfg.paths.data_dir);
            let meta = match preset_index.get(&preset_id) {
                Some(m) => m,
                None => return,
            };
            let loaded = crate::config::load_preset(&cfg.paths.data_dir, meta);

            {
                let mut state = app.lock().unwrap();
                let ok =
                    game::setup_to_live(&mut state, game_id, &preset_id, allow_join, cfg);
                if !ok {
                    return;
                }
            }

            // Start tick loop & periodic backup
            game::start_tick_loop(app.clone(), game_id.to_string(), loaded);
            backup::start_periodic_backup(app.clone(), game_id.to_string(), cfg.paths.backup_dir.clone());
        }
        "endgame" => {
            let mut state = app.lock().unwrap();
            game::live_to_settlement(&mut state, game_id);
            backup::save_backup(&state, game_id, &cfg.paths.backup_dir);
        }
        "rankgame" => {
            let true_prices: std::collections::HashMap<String, f64> = msg
                .data
                .get("true_prices")
                .and_then(|v| serde_json::from_value(v.clone()).ok())
                .unwrap_or_default();

            {
                let mut state = app.lock().unwrap();
                game::settlement_to_results(&mut state, game_id, &true_prices);
                backup::save_backup(&state, game_id, &cfg.paths.backup_dir);
            }
            game::schedule_cleanup(app.clone(), game_id.to_string());
        }
        "presets" => {
            let presets = game::get_presets(cfg);
            let state = app.lock().unwrap();
            state.send_to_admins(game_id, "presets", presets);
        }
        "snapshot" => {
            let state = app.lock().unwrap();
            let snap = game::build_game_snapshot(&state, game_id);
            state.send_to_admins(game_id, "snapshot", snap);
        }
        "leaderboard" => {
            let state = app.lock().unwrap();
            let lb = game::build_leaderboard(&state, game_id);
            state.send_to_admins(game_id, "leaderboard", lb);
        }
        "news" => {
            let message = msg.data["message"].as_str().unwrap_or_default();
            if !message.is_empty() {
                let mut state = app.lock().unwrap();
                game::broadcast_news(&mut state, game_id, message);
            }
        }
        _ => {}
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn is_active(state: &models::State, player_id: &str) -> bool {
    state
        .players
        .get(player_id)
        .map(|p| p.active)
        .unwrap_or(false)
}

fn parse_side(s: &str) -> Side {
    match s {
        "ask" | "Ask" => Side::Ask,
        _ => Side::Bid,
    }
}
