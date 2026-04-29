use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde::Deserialize;

use crate::models::{
    BotDef, GameConfig, PresetConfig, PresetMeta, Security, TickData,
};

// ---------------------------------------------------------------------------
// Server config — loaded from config.toml with env var overrides
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Deserialize)]
pub struct Config {
    #[serde(default = "default_server")]
    pub server: ServerConfig,
    #[serde(default)]
    pub paths: PathsConfig,
    #[serde(default)]
    pub firebase: FirebaseConfig,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ServerConfig {
    #[serde(default = "default_host")]
    pub host: String,
    #[serde(default = "default_port")]
    pub port: u16,
    #[serde(default = "default_cors")]
    pub cors_origins: Vec<String>,
    #[serde(default)]
    pub debug: bool,
}

#[derive(Clone, Debug, Deserialize)]
pub struct PathsConfig {
    #[serde(default = "default_data_dir")]
    pub data_dir: PathBuf,
    #[serde(default = "default_backup_dir")]
    pub backup_dir: PathBuf,
}

#[derive(Clone, Debug, Deserialize)]
pub struct FirebaseConfig {
    #[serde(default)]
    pub upload: bool,
    #[serde(default = "default_fb_creds")]
    pub credentials: String,
    #[serde(default)]
    pub doc: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub address: String,
}

// Defaults
fn default_server() -> ServerConfig {
    ServerConfig {
        host: default_host(),
        port: default_port(),
        cors_origins: default_cors(),
        debug: false,
    }
}
fn default_host() -> String { "0.0.0.0".into() }
fn default_port() -> u16 { 5000 }
fn default_cors() -> Vec<String> { vec!["http://localhost:3000".into()] }
fn default_data_dir() -> PathBuf { PathBuf::from("data") }
fn default_backup_dir() -> PathBuf { PathBuf::from("backups") }
fn default_fb_creds() -> String { "credentials/firebase-admin-key.json".into() }

impl Default for PathsConfig {
    fn default() -> Self {
        Self { data_dir: default_data_dir(), backup_dir: default_backup_dir() }
    }
}

impl Default for FirebaseConfig {
    fn default() -> Self {
        Self {
            upload: false,
            credentials: default_fb_creds(),
            doc: String::new(),
            name: String::new(),
            address: String::new(),
        }
    }
}

impl Config {
    pub fn load() -> Self {
        let builder = config::Config::builder()
            // 1. config.toml (optional — missing file is fine)
            .add_source(
                config::File::with_name("config")
                    .format(config::FileFormat::Toml)
                    .required(false),
            )
            // 2. Env var overrides (SERVER_HOST, SERVER_PORT, PATHS_DATA_DIR, FIREBASE_UPLOAD, etc.)
            .add_source(
                config::Environment::default()
                    .separator("_")
                    .try_parsing(true),
            )
            .build()
            .expect("Failed to build config");

        builder
            .try_deserialize::<Config>()
            .expect("Failed to deserialize config")
    }

    // Convenience accessors matching the old interface
    pub fn firebase_credentials_path(&self) -> PathBuf {
        self.paths.data_dir.join(&self.firebase.credentials)
    }
}

// ---------------------------------------------------------------------------
// Preset loading
// ---------------------------------------------------------------------------

pub fn load_preset_index(data_dir: &Path) -> HashMap<String, PresetMeta> {
    let path = data_dir.join("presets.json");
    let content = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("Cannot read {}: {e}", path.display()));
    serde_json::from_str(&content)
        .unwrap_or_else(|e| panic!("Bad presets.json: {e}"))
}

pub struct LoadedPreset {
    pub config: GameConfig,
    pub securities: HashMap<String, Security>,
    pub tick_data: TickData,
    pub bots: Vec<(String, BotDef)>,
    pub news_col: String,
}

pub fn load_preset(data_dir: &Path, meta: &PresetMeta) -> LoadedPreset {
    let cfg_path = data_dir.join("presets").join(&meta.file);
    let raw = std::fs::read_to_string(&cfg_path)
        .unwrap_or_else(|e| panic!("Cannot read {}: {e}", cfg_path.display()));
    let pc: PresetConfig = serde_json::from_str(&raw)
        .unwrap_or_else(|e| panic!("Bad preset config {}: {e}", cfg_path.display()));

    let config = GameConfig {
        game_ticks: pc.game_ticks.unwrap_or(100),
        tick_length_secs: pc.tick_length.unwrap_or(1.0),
        initial_cash: pc.initial_cash.unwrap_or(100_000.0),
        margin_call_ticks: pc.margin_call_ticks.unwrap_or(3),
        allowed_bankruptcies: pc.allowed_bankruptcies.unwrap_or(3),
        sell_liquidation_fraction: pc.sell_liquidation_fraction.unwrap_or(0.5),
        buy_liquidation_fraction: pc.buy_liquidation_fraction.unwrap_or(1.5),
    };

    let securities = pc
        .securities
        .unwrap_or_default()
        .into_iter()
        .map(|(id, def)| {
            let sec = Security::new(
                def.name.unwrap_or_else(|| id.clone()),
                def.long_margin.unwrap_or(0.0),
                def.short_margin.unwrap_or(0.0),
            );
            (id, sec)
        })
        .collect();

    let tick_data = if let Some(ref td_path) = pc.tick_data {
        load_tick_data(&data_dir.join(td_path))
    } else {
        TickData {
            columns: HashMap::new(),
        }
    };

    let bots = parse_bots(&pc.bots);
    let news_col = pc.news_col.unwrap_or_else(|| "news".to_string());

    LoadedPreset {
        config,
        securities,
        tick_data,
        bots,
        news_col,
    }
}

fn load_tick_data(path: &Path) -> TickData {
    let mut rdr = csv::Reader::from_path(path)
        .unwrap_or_else(|e| panic!("Cannot open tick data {}: {e}", path.display()));

    let headers: Vec<String> = rdr
        .headers()
        .unwrap()
        .iter()
        .map(|h| h.to_string())
        .collect();

    let mut columns: HashMap<String, Vec<String>> = headers
        .iter()
        .map(|h| (h.clone(), Vec::new()))
        .collect();

    for result in rdr.records() {
        let record = result.unwrap();
        for (i, hdr) in headers.iter().enumerate() {
            columns
                .get_mut(hdr)
                .unwrap()
                .push(record.get(i).unwrap_or("").to_string());
        }
    }

    TickData { columns }
}

fn parse_bots(val: &Option<serde_json::Value>) -> Vec<(String, BotDef)> {
    match val {
        None => Vec::new(),
        Some(serde_json::Value::Array(_)) => Vec::new(),
        Some(serde_json::Value::Object(map)) => map
            .iter()
            .filter_map(|(name, v)| {
                serde_json::from_value::<BotDef>(v.clone())
                    .ok()
                    .map(|b| (name.clone(), b))
            })
            .collect(),
        _ => Vec::new(),
    }
}
