use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::Manager;

pub mod models;
pub mod database;
pub mod pool;
pub mod commands;

use commands::AppState;
use pool::AccountPool;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .setup(|app| {
            let app_dir = app.path().app_data_dir()
                .unwrap_or_else(|_| PathBuf::from("./data"));
            
            let pool = Arc::new(AccountPool::new(app_dir)?);
            
            let _ = pool.check_and_reset();
            
            app.manage(AppState { pool, current_account: Mutex::new(None) });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_accounts,
            commands::get_accounts_page,
            commands::get_stats,
            commands::take_account,
            commands::switch_windsurf_account,
            commands::take_and_switch,
            commands::mark_daily_exhausted,
            commands::mark_weekly_exhausted,
            commands::unmark_exhausted,
            commands::delete_account,
            commands::batch_mark_daily_exhausted,
            commands::batch_mark_weekly_exhausted,
            commands::batch_unmark_exhausted,
            commands::batch_delete_accounts,
            commands::import_accounts,
            commands::import_from_json,
            commands::check_reset,
            commands::get_reset_info,
            commands::get_current_account,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
