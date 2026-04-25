use std::sync::Arc;
use tauri::State;
use serde::Serialize;

use crate::models::*;
use crate::pool::AccountPool;

pub struct AppState {
    pub pool: Arc<AccountPool>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PageResult {
    pub accounts: Vec<Account>,
    pub total: i32,
}

#[tauri::command]
pub fn get_accounts(state: State<AppState>) -> Result<Vec<Account>, String> {
    state.pool.get_accounts().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_accounts_page(state: State<AppState>, page: i32, page_size: i32, search: Option<String>, status_filter: Option<String>) -> Result<PageResult, String> {
    let (accounts, total) = state.pool.get_accounts_page(page, page_size, search, status_filter).map_err(|e| e.to_string())?;
    Ok(PageResult { accounts, total })
}

#[tauri::command]
pub fn get_stats(state: State<AppState>) -> Result<PoolStats, String> {
    state.pool.get_stats().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn take_account(state: State<AppState>) -> Result<TakeAccountResult, String> {
    state.pool.take_account().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn mark_daily_exhausted(state: State<AppState>, email: String) -> Result<(), String> {
    state.pool.mark_daily_exhausted(&email).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn mark_weekly_exhausted(state: State<AppState>, email: String) -> Result<(), String> {
    state.pool.mark_weekly_exhausted(&email).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn unmark_exhausted(state: State<AppState>, email: String) -> Result<(), String> {
    state.pool.unmark_exhausted(&email).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn delete_account(state: State<AppState>, email: String) -> Result<(), String> {
    state.pool.delete_account(&email).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn batch_mark_daily_exhausted(state: State<AppState>, emails: Vec<String>) -> Result<i32, String> {
    state.pool.batch_mark_daily_exhausted(emails).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn batch_mark_weekly_exhausted(state: State<AppState>, emails: Vec<String>) -> Result<i32, String> {
    state.pool.batch_mark_weekly_exhausted(emails).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn batch_unmark_exhausted(state: State<AppState>, emails: Vec<String>) -> Result<i32, String> {
    state.pool.batch_unmark_exhausted(emails).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn batch_delete_accounts(state: State<AppState>, emails: Vec<String>) -> Result<i32, String> {
    state.pool.batch_delete_accounts(emails).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn import_accounts(state: State<AppState>, emails: Vec<String>) -> Result<ImportResult, String> {
    state.pool.import_accounts(emails).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn import_from_json(state: State<AppState>, json_content: String) -> Result<ImportResult, String> {
    state.pool.import_from_json(&json_content).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn check_reset(state: State<AppState>) -> Result<(), String> {
    state.pool.check_and_reset().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_reset_info(state: State<AppState>) -> Result<ResetInfo, String> {
    state.pool.get_reset_info().map_err(|e| e.to_string())
}
