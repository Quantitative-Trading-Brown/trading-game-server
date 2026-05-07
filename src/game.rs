use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use rand::Rng;

use crate::bots::BotManager;
use crate::config::{self, Config, LoadedPreset};
use crate::exchange;
use crate::models::*;

// ---------------------------------------------------------------------------
// Token / code generation
// ---------------------------------------------------------------------------

pub fn generate_code(len: usize) -> String {
    const CHARSET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let mut rng = rand::rng();
    (0..len)
        .map(|_| CHARSET[rng.random_range(0..CHARSET.len())] as char)
        .collect()
}

pub fn generate_token(prefix: &str, len: usize) -> String {
    let bytes: Vec<u8> = (0..len).map(|_| rand::random()).collect();
    let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    format!("{prefix}{hex}")
}

// ---------------------------------------------------------------------------
// Game creation
// ---------------------------------------------------------------------------

pub fn create_game(state: &mut State) -> (String, String, String) {
    // Unique code
    let mut code = generate_code(6);
    while state.codes.contains_key(&code) {
        code = generate_code(6);
    }

    state.game_count += 1;
    let game_id = state.game_count.to_string();
    let admin_token = generate_token(&format!("admin-{game_id}-"), 32);

    state.codes.insert(code.clone(), game_id.clone());
    state
        .admin_tokens
        .insert(game_id.clone(), admin_token.clone());

    let game = Game::new(game_id.clone(), code.clone());
    state.games.insert(game_id.clone(), game);

    (game_id, code, admin_token)
}

// ---------------------------------------------------------------------------
// Join game
// ---------------------------------------------------------------------------

pub fn join_game(
    state: &mut State,
    code: &str,
    username: &str,
) -> Result<String, String> {
    let game_id = state
        .codes
        .get(code)
        .cloned()
        .ok_or_else(|| "Game not found".to_string())?;

    let game = state
        .games
        .get(&game_id)
        .ok_or_else(|| "Game not found".to_string())?;

    // Check join allowed
    if game.phase != GamePhase::Setup && !game.allow_join {
        return Err("Game in progress. Joining not allowed.".to_string());
    }

    // Check duplicate name
    for pid in &game.players {
        if let Some(p) = state.players.get(pid) {
            if p.username == username {
                return Err("Player name taken".to_string());
            }
        }
    }

    // Create player
    state.player_count += 1;
    let player_id = state.player_count.to_string();
    let token = generate_token(&format!("player-{player_id}-"), 32);

    let mut player = Player::new(player_id.clone(), username.to_string(), game_id.clone());

    // If game is live, give initial cash
    if game.phase == GamePhase::Live {
        player.cash = game.config.initial_cash;
    }

    state
        .player_tokens
        .insert(player_id.clone(), token.clone());
    state.players.insert(player_id.clone(), player);

    let game = state.games.get_mut(&game_id).unwrap();
    game.touch();
    game.players.push(player_id.clone());
    game.active_players.insert(player_id);

    Ok(token)
}

// ---------------------------------------------------------------------------
// Auth verification
// ---------------------------------------------------------------------------

/// Returns ("player", player_id) or ("admin", game_id) on success.
pub fn verify_token(state: &State, token: &str) -> Option<(&'static str, String)> {
    let parts: Vec<&str> = token.splitn(3, '-').collect();
    if parts.len() != 3 {
        return None;
    }
    let (prefix, auth_id, _secret) = (parts[0], parts[1], parts[2]);

    match prefix {
        "player" => {
            let stored = state.player_tokens.get(auth_id)?;
            if constant_time_eq(token, stored) {
                Some(("player", auth_id.to_string()))
            } else {
                None
            }
        }
        "admin" => {
            let stored = state.admin_tokens.get(auth_id)?;
            if constant_time_eq(token, stored) {
                Some(("admin", auth_id.to_string()))
            } else {
                None
            }
        }
        _ => None,
    }
}

fn constant_time_eq(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    a.bytes()
        .zip(b.bytes())
        .fold(0u8, |acc, (x, y)| acc | (x ^ y))
        == 0
}

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

pub fn setup_to_live(
    state: &mut State,
    game_id: &str,
    preset_id: &str,
    allow_join: bool,
    cfg: &Config,
) -> bool {
    match state.games.get(game_id) {
        Some(g) if g.phase == GamePhase::Setup => {}
        _ => return false,
    };

    let preset_index = config::load_preset_index(&cfg.paths.data_dir);
    let meta = match preset_index.get(preset_id) {
        Some(m) => m,
        None => return false,
    };

    let loaded = config::load_preset(&cfg.paths.data_dir, meta);
    apply_preset(state, game_id, &loaded, allow_join);

    set_phase(state, game_id, GamePhase::Live);

    // Send snapshots to all connected clients
    send_all_snapshots(state, game_id);

    true
}

pub fn live_to_settlement(state: &mut State, game_id: &str) {
    if let Some(game) = state.games.get(game_id) {
        if game.phase != GamePhase::Live {
            return;
        }
    } else {
        return;
    }
    set_phase(state, game_id, GamePhase::Settlement);
}

pub fn settlement_to_results(
    state: &mut State,
    game_id: &str,
    true_prices: &HashMap<String, f64>,
) {
    let game = match state.games.get(game_id) {
        Some(g) if g.phase == GamePhase::Settlement => g,
        _ => return,
    };

    let buy_frac = game.config.buy_liquidation_fraction;
    let sell_frac = game.config.sell_liquidation_fraction;
    let player_ids: Vec<String> = game.players.clone();

    for pid in &player_ids {
        let player = match state.players.get_mut(pid) {
            Some(p) => p,
            None => continue,
        };
        let mut score = 0.0f64;
        for (sec_id, &amt) in &player.inventory {
            let true_price = true_prices.get(sec_id).copied().unwrap_or(0.0);
            if amt > 0 {
                score += sell_frac * true_price * (amt as f64);
            } else {
                score += buy_frac * true_price * (amt as f64);
            }
        }
        score += player.cash;
        player.score = (score * 100.0).round() / 100.0;
    }

    set_phase(state, game_id, GamePhase::Results);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn set_phase(state: &mut State, game_id: &str, phase: GamePhase) {
    if let Some(game) = state.games.get_mut(game_id) {
        game.phase = phase;
    }
    let data = serde_json::json!(phase as u8);
    state.broadcast(game_id, "gamestate_update", data);
}

fn apply_preset(state: &mut State, game_id: &str, preset: &LoadedPreset, allow_join: bool) {
    let game = state.games.get_mut(game_id).unwrap();
    game.config = preset.config.clone();
    game.allow_join = allow_join;

    for (sec_id, sec) in &preset.securities {
        game.securities.insert(sec_id.clone(), sec.clone());
    }

    // Give all existing players initial cash
    let pids: Vec<String> = game.players.clone();
    for pid in &pids {
        if let Some(player) = state.players.get_mut(pid) {
            player.cash = preset.config.initial_cash;
        }
    }
}

// ---------------------------------------------------------------------------
// Tick loop (spawned as a tokio task)
// ---------------------------------------------------------------------------

pub fn start_tick_loop(
    app: Arc<Mutex<State>>,
    game_id: String,
    preset: LoadedPreset,
) {
    let mut bot_manager = BotManager::new(&game_id, &preset.tick_data, &preset.bots);

    let tick_length = preset.config.tick_length_secs;
    let game_ticks = preset.config.game_ticks;
    let news_col = preset.news_col.clone();
    let tick_data = preset.tick_data.clone();

    tokio::spawn(async move {
        let mut cur_tick: u64 = 0;

        loop {
            {
                let mut state = app.lock().unwrap();

                // Check if still live
                let still_live = state
                    .games
                    .get(&game_id)
                    .map(|g| g.phase == GamePhase::Live)
                    .unwrap_or(false);

                if !still_live {
                    break;
                }

                if cur_tick >= game_ticks {
                    live_to_settlement(&mut state, &game_id);
                    break;
                }

                // 1. Run bots
                bot_manager.run(&mut state, cur_tick);

                // 2. Update prices
                update_all_prices(&mut state, &game_id);

                // 3. Mark all positions
                mark_all_positions(&mut state, &game_id);

                // 4. Check margin
                check_margin(&mut state, &game_id);

                // 5. Flush tick updates
                flush_tick(&mut state, &game_id);

                // 6. Broadcast news
                if let Some(news_text) = tick_data.get_str(&news_col, cur_tick as usize) {
                    let trimmed = news_text.trim();
                    if !trimmed.is_empty() {
                        broadcast_news(&mut state, &game_id, trimmed);
                    }
                }
            }

            tokio::time::sleep(tokio::time::Duration::from_secs_f64(tick_length)).await;
            cur_tick += 1;
        }
    });
}

// ---------------------------------------------------------------------------
// Price update
// ---------------------------------------------------------------------------

fn update_all_prices(state: &mut State, game_id: &str) {
    let game = match state.games.get_mut(game_id) {
        Some(g) => g,
        None => return,
    };
    let sec_ids: Vec<String> = game.securities.keys().cloned().collect();
    for sec_id in sec_ids {
        let price = exchange::compute_price(game.securities.get(&sec_id).unwrap());
        game.securities.get_mut(&sec_id).unwrap().price = price;
    }
}

// ---------------------------------------------------------------------------
// Position marking
// ---------------------------------------------------------------------------

fn mark_all_positions(state: &mut State, game_id: &str) {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    let active: Vec<String> = game.active_players.iter().cloned().collect();

    for pid in active {
        if let Some(player) = state.players.get_mut(&pid) {
            let game = state.games.get(game_id).unwrap();
            exchange::mark_positions(player, game);
        }
    }
}

// ---------------------------------------------------------------------------
// Margin / bankruptcy
// ---------------------------------------------------------------------------

fn check_margin(state: &mut State, game_id: &str) {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    let allowed_ticks = game.config.margin_call_ticks;
    let active: Vec<String> = game.active_players.iter().cloned().collect();

    for pid in active {
        let violated = {
            let player = match state.players.get(&pid) {
                Some(p) => p,
                None => continue,
            };
            let equity = player.cash + player.position_value;
            equity < player.margin
        };

        if violated {
            let player = state.players.get_mut(&pid).unwrap();
            player.warning_ticks += 1;
            if player.warning_ticks >= allowed_ticks {
                execute_margin_call(state, game_id, &pid);
            }
        } else {
            if let Some(player) = state.players.get_mut(&pid) {
                player.warning_ticks = 0;
            }
        }
    }
}

fn execute_margin_call(state: &mut State, game_id: &str, player_id: &str) {
    liquidate_player(state, game_id, player_id);

    let still_violated = {
        let player = match state.players.get(player_id) {
            Some(p) => p,
            None => return,
        };
        let equity = player.cash + player.position_value;
        equity < player.margin
    };

    if still_violated {
        handle_bankruptcy(state, game_id, player_id);
    } else {
        state.send_to_player(player_id, "margin_call", serde_json::Value::Null);
    }

    if let Some(player) = state.players.get_mut(player_id) {
        player.warning_ticks = 0;
    }
}

fn liquidate_player(state: &mut State, game_id: &str, player_id: &str) {
    let inv: Vec<(String, i64)> = state
        .players
        .get(player_id)
        .map(|p| p.inventory.iter().map(|(k, &v)| (k.clone(), v)).collect())
        .unwrap_or_default();

    for (sec_id, qty) in inv {
        if qty == 0 {
            continue;
        }
        let side = if qty > 0 { Side::Ask } else { Side::Bid };
        exchange::process_market_order(state, game_id, player_id, &sec_id, side, qty.unsigned_abs() as i64);
    }
}

fn handle_bankruptcy(state: &mut State, game_id: &str, player_id: &str) {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    let allowed = game.config.allowed_bankruptcies;
    let initial_cash = game.config.initial_cash;

    let player = match state.players.get_mut(player_id) {
        Some(p) => p,
        None => return,
    };

    player.bankruptcies += 1;
    player.cash = initial_cash;
    player.position_value = 0.0;
    player.margin = 0.0;
    player.inventory.clear();

    let remaining = allowed.saturating_sub(player.bankruptcies);
    let bankruptcies = player.bankruptcies;

    // Cancel all orders
    exchange::cancel_all_orders(state, game_id, player_id);

    // Send snapshot
    let snapshot = build_player_snapshot(state, game_id, player_id);
    state.send_to_player(player_id, "snapshot", snapshot);
    state.send_to_player(
        player_id,
        "bankruptcy",
        serde_json::json!(remaining),
    );

    // Check elimination
    if bankruptcies >= allowed {
        if let Some(player) = state.players.get_mut(player_id) {
            player.active = false;
            player.cash = 0.0;
        }
        if let Some(game) = state.games.get_mut(game_id) {
            game.active_players.remove(player_id);
        }
        state.send_to_player(player_id, "elimination", serde_json::Value::Null);
    }
}

// ---------------------------------------------------------------------------
// Tick flush
// ---------------------------------------------------------------------------

fn flush_tick(state: &mut State, game_id: &str) {
    // Drain pending updates and collect prices (needs &mut game, then drop it)
    let (total_update, prices) = {
        let game = match state.games.get_mut(game_id) {
            Some(g) => g,
            None => return,
        };

        let mut total_update: HashMap<String, HashMap<String, i64>> = HashMap::new();
        let sec_ids: Vec<String> = game.securities.keys().cloned().collect();

        for sec_id in &sec_ids {
            let sec = game.securities.get_mut(sec_id).unwrap();
            if sec.pending_updates.is_empty() {
                continue;
            }
            // Send absolute display values for each changed price level
            let updates: HashMap<String, i64> = sec
                .pending_updates
                .drain()
                .map(|(price, _delta)| {
                    let abs_val = sec.display.get(&price).copied().unwrap_or(0);
                    (price.to_string(), abs_val)
                })
                .collect();
            total_update.insert(sec_id.clone(), updates);
        }

        let prices: HashMap<String, f64> = game
            .securities
            .iter()
            .map(|(id, s)| (id.clone(), s.price))
            .collect();

        (total_update, prices)
    };

    // Broadcast orderbook + prices
    state.broadcast(game_id, "orderbook", serde_json::json!(total_update));
    state.broadcast(game_id, "prices", serde_json::json!(prices));

    // Per-player accounting flush
    let game = state.games.get(game_id).unwrap();
    let active: Vec<String> = game.active_players.iter().cloned().collect();

    for pid in active {
        let player = match state.players.get(&pid) {
            Some(p) => p,
            None => continue,
        };
        let msg = serde_json::json!({
            "position_value": player.position_value,
            "margin": player.margin,
        });
        state.send_to_player(&pid, "inventory", msg);
    }
}

// ---------------------------------------------------------------------------
// News
// ---------------------------------------------------------------------------

pub fn broadcast_news(state: &mut State, game_id: &str, message: &str) {
    let ts = chrono::Local::now().format("%H:%M:%S").to_string();
    let full_msg = format!("[news] {message}");

    let entry = NewsEntry {
        timestamp: ts.clone(),
        message: full_msg.clone(),
    };

    if let Some(game) = state.games.get_mut(game_id) {
        game.news.push_front(entry);
        if game.news.len() > 100 {
            game.news.pop_back();
        }
    }

    state.broadcast(
        game_id,
        "news",
        serde_json::json!([ts, full_msg]),
    );
}

// ---------------------------------------------------------------------------
// Snapshots
// ---------------------------------------------------------------------------

pub fn build_game_snapshot(state: &State, game_id: &str) -> serde_json::Value {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return serde_json::Value::Null,
    };

    let security_props: HashMap<&str, serde_json::Value> = game
        .securities
        .iter()
        .map(|(id, s)| {
            (
                id.as_str(),
                serde_json::json!({
                    "name": s.name,
                    "long_margin": s.long_margin,
                    "short_margin": s.short_margin,
                }),
            )
        })
        .collect();

    let orderbooks: HashMap<&str, &HashMap<i64, i64>> = game
        .securities
        .iter()
        .map(|(id, s)| (id.as_str(), &s.display))
        .collect();

    let past_news: Vec<serde_json::Value> = game
        .news
        .iter()
        .rev()
        .take(20)
        .map(|n| serde_json::json!([n.timestamp, n.message]))
        .collect();

    serde_json::json!({
        "game_props": {
            "state": game.phase as u8,
            "code": game.code,
            "allow_join": game.allow_join,
            "game_ticks": game.config.game_ticks,
            "tick_length": game.config.tick_length_secs,
            "initial_cash": game.config.initial_cash,
            "margin_call_ticks": game.config.margin_call_ticks,
            "allowed_bankruptcies": game.config.allowed_bankruptcies,
            "sell_liquidation_fraction": game.config.sell_liquidation_fraction,
            "buy_liquidation_fraction": game.config.buy_liquidation_fraction,
        },
        "securities": security_props,
        "orderbooks": orderbooks,
        "past_news": past_news,
    })
}

pub fn build_player_snapshot(
    state: &State,
    game_id: &str,
    player_id: &str,
) -> serde_json::Value {
    let mut snap = build_game_snapshot(state, game_id);

    if let Some(player) = state.players.get(player_id) {
        let game = state.games.get(game_id).unwrap();
        let orders: HashMap<&str, serde_json::Value> = player
            .orders
            .iter()
            .filter_map(|oid| {
                game.orders.get(oid).map(|o| {
                    (
                        oid.as_str(),
                        serde_json::json!({
                            "security": o.security,
                            "side": match o.side { Side::Bid => "bids", Side::Ask => "asks" },
                            "price": o.price,
                            "quantity": o.quantity,
                            "issuer_id": o.issuer_id,
                        }),
                    )
                })
            })
            .collect();

        if let Some(obj) = snap.as_object_mut() {
            obj.insert("username".to_string(), serde_json::json!(player.username));
            obj.insert("inventory".to_string(), serde_json::json!(player.inventory));
            obj.insert("cash".to_string(), serde_json::json!(player.cash));
            obj.insert(
                "position_value".to_string(),
                serde_json::json!(player.position_value),
            );
            obj.insert("margin".to_string(), serde_json::json!(player.margin));
            obj.insert("orders".to_string(), serde_json::json!(orders));
            obj.insert("active".to_string(), serde_json::json!(player.active));
        }
    }

    snap
}

fn send_all_snapshots(state: &State, game_id: &str) {
    let admin_snap = build_game_snapshot(state, game_id);
    state.send_to_admins(game_id, "snapshot", admin_snap);

    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };
    for pid in &game.players {
        let snap = build_player_snapshot(state, game_id, pid);
        state.send_to_player(pid, "snapshot", snap);
    }
}

// ---------------------------------------------------------------------------
// Leaderboard
// ---------------------------------------------------------------------------

pub fn build_leaderboard(state: &State, game_id: &str) -> serde_json::Value {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return serde_json::json!([]),
    };

    let mut entries: Vec<(String, u32, f64)> = game
        .players
        .iter()
        .filter_map(|pid| {
            state.players.get(pid).map(|p| {
                (p.username.clone(), p.bankruptcies, p.score)
            })
        })
        .collect();

    // Sort: fewest bankruptcies first, then highest score
    entries.sort_by(|a, b| {
        a.1.cmp(&b.1)
            .then_with(|| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal))
    });

    serde_json::json!(entries)
}

// ---------------------------------------------------------------------------
// Game cleanup (free memory for finished games)
// ---------------------------------------------------------------------------

/// Remove a game and all associated player data from state.
/// Works in any game phase (used by both scheduled cleanup and the reaper).
pub fn cleanup_game(state: &mut State, game_id: &str) {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };

    let phase = game.phase;
    let player_ids: Vec<String> = game.players.clone();
    let code = game.code.clone();

    for pid in &player_ids {
        state.players.remove(pid);
        state.player_tokens.remove(pid);
        state.player_senders.remove(pid);
    }

    state.games.remove(game_id);
    state.codes.remove(&code);
    state.admin_senders.remove(game_id);
    state.admin_tokens.remove(game_id);

    tracing::info!("Game {game_id} cleaned up (was in phase {phase:?})");
}

/// Spawn a task that cleans up the game after a delay (5 minutes after results).
pub fn schedule_cleanup(
    app: std::sync::Arc<std::sync::Mutex<State>>,
    game_id: String,
) {
    tokio::spawn(async move {
        tokio::time::sleep(tokio::time::Duration::from_secs(300)).await;
        let mut state = app.lock().unwrap();
        cleanup_game(&mut state, &game_id);
    });
}

/// Periodically scan for abandoned or expired games and clean them up.
///
/// - **Inactivity**: games with no player/admin activity for `MAX_INACTIVITY_SECS` (30 min).
/// - **Max lifetime**: games older than `MAX_GAME_LIFETIME_SECS` (2 hours) regardless of activity.
///
/// Games in the Results phase are skipped here — they already have `schedule_cleanup`.
pub fn start_reaper(app: std::sync::Arc<std::sync::Mutex<State>>) {
    use crate::models::{MAX_GAME_LIFETIME_SECS, MAX_INACTIVITY_SECS};

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(60));
        loop {
            interval.tick().await;

            let mut state = app.lock().unwrap();
            let now = std::time::Instant::now();

            let game_ids: Vec<String> = state.games.keys().cloned().collect();
            for gid in game_ids {
                let game = match state.games.get(&gid) {
                    Some(g) => g,
                    None => continue,
                };

                // Results phase games are already scheduled for cleanup.
                if game.phase == GamePhase::Results {
                    continue;
                }

                let age = now.duration_since(game.created_at).as_secs();
                let idle = now.duration_since(game.last_activity).as_secs();

                if age >= MAX_GAME_LIFETIME_SECS {
                    tracing::warn!("Reaping game {gid}: exceeded max lifetime ({age}s)");
                    cleanup_game(&mut state, &gid);
                } else if idle >= MAX_INACTIVITY_SECS {
                    tracing::warn!("Reaping game {gid}: inactive for {idle}s");
                    cleanup_game(&mut state, &gid);
                }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Presets query
// ---------------------------------------------------------------------------

pub fn get_presets(cfg: &Config) -> serde_json::Value {
    let index = config::load_preset_index(&cfg.paths.data_dir);
    let list: Vec<serde_json::Value> = index
        .iter()
        .map(|(id, m)| {
            serde_json::json!({
                "id": id,
                "name": m.name,
                "desc": m.description,
            })
        })
        .collect();
    serde_json::json!(list)
}
