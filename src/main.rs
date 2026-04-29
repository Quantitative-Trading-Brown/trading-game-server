mod backup;
mod bots;
mod config;
mod exchange;
mod game;
mod models;
mod websocket;

use std::sync::{Arc, Mutex};

use axum::extract::{Json, State as AxumState};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{get, post};
use axum::Router;
use serde::Deserialize;
use tower_http::cors::{AllowOrigin, CorsLayer};

use config::Config;
use models::State;
use websocket::AppState;

// ---------------------------------------------------------------------------
// HTTP route handlers
// ---------------------------------------------------------------------------

async fn health() -> impl IntoResponse {
    StatusCode::NO_CONTENT
}

#[derive(Deserialize)]
struct AuthRequest {
    token: String,
}

async fn check_auth(
    AxumState((app, _cfg)): AxumState<(AppState, Arc<Config>)>,
    Json(body): Json<AuthRequest>,
) -> impl IntoResponse {
    let state = app.lock().unwrap();
    match game::verify_token(&state, &body.token) {
        Some((auth_type, _id)) => (
            StatusCode::CREATED,
            Json(serde_json::json!({"type": auth_type})),
        ),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "Invalid token"})),
        ),
    }
}

async fn create_game(
    AxumState((app, _cfg)): AxumState<(AppState, Arc<Config>)>,
) -> impl IntoResponse {
    let mut state = app.lock().unwrap();
    let (_game_id, code, admin_token) = game::create_game(&mut state);
    tracing::info!("Game created: code={code}");
    (
        StatusCode::CREATED,
        Json(serde_json::json!({"code": code, "token": admin_token})),
    )
}

#[derive(Deserialize)]
struct JoinRequest {
    code: String,
    #[serde(rename = "playerName")]
    player_name: String,
}

async fn join_game(
    AxumState((app, _cfg)): AxumState<(AppState, Arc<Config>)>,
    Json(body): Json<JoinRequest>,
) -> impl IntoResponse {
    let mut state = app.lock().unwrap();
    match game::join_game(&mut state, &body.code, &body.player_name) {
        Ok(token) => (
            StatusCode::OK,
            Json(serde_json::json!({"message": "Joined successfully", "token": token})),
        ),
        Err(e) => (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))),
    }
}

// ---------------------------------------------------------------------------
// Firebase upload (optional)
// ---------------------------------------------------------------------------

async fn upload_firebase_address(cfg: &Config) {
    if !cfg.firebase.upload {
        return;
    }

    tracing::info!("Uploading server address to Firebase...");

    let creds_raw = match std::fs::read_to_string(&cfg.firebase_credentials_path()) {
        Ok(c) => c,
        Err(e) => {
            tracing::error!("Cannot read Firebase credentials: {e}");
            return;
        }
    };

    let creds: serde_json::Value = match serde_json::from_str(&creds_raw) {
        Ok(v) => v,
        Err(e) => {
            tracing::error!("Bad Firebase credentials JSON: {e}");
            return;
        }
    };

    let project_id = creds["project_id"].as_str().unwrap_or_default();
    let client_email = creds["client_email"].as_str().unwrap_or_default();
    let private_key = creds["private_key"].as_str().unwrap_or_default();

    // Build JWT for Google OAuth2
    let now = chrono::Utc::now().timestamp() as u64;
    let claims = serde_json::json!({
        "iss": client_email,
        "scope": "https://www.googleapis.com/auth/datastore",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    });

    let key = match jsonwebtoken::EncodingKey::from_rsa_pem(private_key.as_bytes()) {
        Ok(k) => k,
        Err(e) => {
            tracing::error!("Bad RSA key: {e}");
            return;
        }
    };

    let header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
    let jwt = match jsonwebtoken::encode(&header, &claims, &key) {
        Ok(t) => t,
        Err(e) => {
            tracing::error!("JWT encode error: {e}");
            return;
        }
    };

    // Exchange JWT for access token
    let client = reqwest::Client::new();
    let token_resp = client
        .post("https://oauth2.googleapis.com/token")
        .form(&[
            ("grant_type", "urn:ietf:params:oauth:grant-type:jwt-bearer"),
            ("assertion", &jwt),
        ])
        .send()
        .await;

    let access_token = match token_resp {
        Ok(resp) => {
            let body: serde_json::Value = resp.json().await.unwrap_or_default();
            body["access_token"]
                .as_str()
                .unwrap_or_default()
                .to_string()
        }
        Err(e) => {
            tracing::error!("Token exchange failed: {e}");
            return;
        }
    };

    if access_token.is_empty() {
        tracing::error!("Empty access token from Google OAuth2");
        return;
    }

    // Write to Firestore
    let doc_url = format!(
        "https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/servers/{}",
        cfg.firebase.doc
    );

    let doc_body = serde_json::json!({
        "fields": {
            "name": {"stringValue": cfg.firebase.name},
            "ip": {"stringValue": cfg.firebase.address},
        }
    });

    match client
        .patch(&doc_url)
        .bearer_auth(&access_token)
        .json(&doc_body)
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => {
            tracing::info!("Firebase address uploaded successfully");
        }
        Ok(resp) => {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            tracing::error!("Firebase write failed ({status}): {body}");
        }
        Err(e) => {
            tracing::error!("Firebase request failed: {e}");
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let cfg = Config::load();
    tracing::info!(
        "Starting trading-game-server on {}:{}",
        cfg.server.host,
        cfg.server.port
    );

    upload_firebase_address(&cfg).await;

    let state: AppState = Arc::new(Mutex::new(State::new()));
    let cfg = Arc::new(cfg);

    // CORS
    let origins: Vec<_> = cfg
        .server
        .cors_origins
        .iter()
        .filter_map(|o| o.parse().ok())
        .collect();
    let cors = CorsLayer::new()
        .allow_origin(AllowOrigin::list(origins))
        .allow_methods(tower_http::cors::Any)
        .allow_headers(tower_http::cors::Any);

    // Debug: auto-create and start a game with the first available preset
    if cfg.server.debug {
        let preset_index = config::load_preset_index(&cfg.paths.data_dir);
        if let Some(meta) = preset_index.get("SP") {
            let preset_id = "SP";
            let loaded = config::load_preset(&cfg.paths.data_dir, meta);
            let game_id = {
                let mut s = state.lock().unwrap();
                let (game_id, code, _token) = game::create_game(&mut s);
                game::setup_to_live(&mut s, &game_id, preset_id, true, &cfg);
                tracing::info!("Debug game started with preset={preset_id}");
                println!("\n  Game Code: {code}\n");
                game_id
            };
            game::start_tick_loop(state.clone(), game_id.clone(), loaded);
            backup::start_periodic_backup(state.clone(), game_id, cfg.paths.backup_dir.clone());
        } else {
            let mut s = state.lock().unwrap();
            let (_game_id, code, _token) = game::create_game(&mut s);
            tracing::info!("Debug game created (no presets found): code={code}");
        }
    }

    let app = Router::new()
        .route("/", get(health))
        .route("/auth", post(check_auth))
        .route("/create-game", post(create_game))
        .route("/join-game", post(join_game))
        .route("/ws/player", get(websocket::player_ws))
        .route("/ws/admin", get(websocket::admin_ws))
        .layer(cors)
        .with_state((state, cfg.clone()));

    let addr = format!("{}:{}", cfg.server.host, cfg.server.port);
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("Failed to bind");

    tracing::info!("Listening on {addr}");
    axum::serve(listener, app).await.unwrap();
}
