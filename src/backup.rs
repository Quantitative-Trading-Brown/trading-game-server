use std::path::Path;
use std::sync::{Arc, Mutex};

use crate::models::{GamePhase, State};

/// Save a JSON backup of a single game (state + trades).
pub fn save_backup(state: &State, game_id: &str, backup_dir: &Path) {
    let game = match state.games.get(game_id) {
        Some(g) => g,
        None => return,
    };

    // Collect player data for this game
    let players: Vec<serde_json::Value> = game
        .players
        .iter()
        .filter_map(|pid| {
            state.players.get(pid).map(|p| {
                serde_json::json!({
                    "id": p.id,
                    "username": p.username,
                    "cash": p.cash,
                    "inventory": p.inventory,
                    "position_value": p.position_value,
                    "margin": p.margin,
                    "bankruptcies": p.bankruptcies,
                    "active": p.active,
                    "score": p.score,
                })
            })
        })
        .collect();

    // Serialize full game struct (includes securities, orderbooks, orders, news)
    let game_state = serde_json::to_value(game).unwrap_or_default();

    let backup = serde_json::json!({
        "game": game_state,
        "players": players,
    });

    if let Err(e) = std::fs::create_dir_all(backup_dir) {
        tracing::error!("Failed to create backup dir: {e}");
        return;
    }

    let ts = chrono::Local::now().format("%Y%m%d_%H%M%S");
    let filename = format!("game_{game_id}_{ts}.json");
    let path = backup_dir.join(&filename);

    match std::fs::write(&path, serde_json::to_string_pretty(&backup).unwrap()) {
        Ok(_) => tracing::info!("Backup saved: {}", path.display()),
        Err(e) => tracing::error!("Backup write failed: {e}"),
    }
}

/// Spawn a background task that saves periodic backups while the game is live.
pub fn start_periodic_backup(app: Arc<Mutex<State>>, game_id: String, backup_dir: std::path::PathBuf) {

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(60));

        loop {
            interval.tick().await;

            let should_continue = {
                let state = app.lock().unwrap();
                let still_live = state
                    .games
                    .get(&game_id)
                    .map(|g| g.phase == GamePhase::Live)
                    .unwrap_or(false);

                if still_live {
                    save_backup(&state, &game_id, &backup_dir);
                }
                still_live
            };

            if !should_continue {
                break;
            }
        }
    });
}
