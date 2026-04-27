use std::sync::{Arc, Mutex};
use tauri::State;
use serde::{Deserialize, Serialize};

use crate::models::*;
use crate::pool::AccountPool;

pub struct AppState {
    pub pool: Arc<AccountPool>,
    pub current_account: Mutex<Option<String>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PageResult {
    pub accounts: Vec<Account>,
    pub total: i32,
}

const FIREBASE_API_KEY: &str = "AIzaSyDsOl-1XpT5err0Tcnx8FFod1H8gVGIycY";

#[derive(Debug, Deserialize)]
struct FirebaseResponse {
    idToken: Option<String>,
    error: Option<FirebaseError>,
}

#[derive(Debug, Deserialize)]
struct FirebaseError {
    message: Option<String>,
}

/// 创建 HTTP 客户端（自动检测系统代理）
fn create_http_client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|e| format!("HTTP 客户端创建失败: {}", e))
}

/// Firebase signInWithPassword 获取 ID token
async fn firebase_login(email: &str, password: &str) -> Result<String, String> {
    let url = format!(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={}",
        FIREBASE_API_KEY
    );

    let client = create_http_client()?;
    let body = serde_json::json!({
        "email": email,
        "password": password,
        "returnSecureToken": true
    });

    let resp = client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("Referer", "https://windsurf.com/")
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Firebase 请求失败: {}", e))?;

    let data: FirebaseResponse = resp
        .json()
        .await
        .map_err(|e| format!("Firebase 响应解析失败: {}", e))?;

    if let Some(err) = data.error {
        let msg = err.message.unwrap_or_else(|| "未知错误".to_string());
        return Err(format!("Firebase 登录失败: {}", msg));
    }

    data.idToken.ok_or_else(|| "Firebase 未返回 idToken".to_string())
}

/// 通过 windsurf:// URI 切换 Windsurf 账号（跨平台）
fn open_windsurf_uri(uri: &str) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        let output = std::process::Command::new("xdg-open")
            .arg(uri)
            .output()
            .map_err(|e| format!("执行 xdg-open 失败: {}", e))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("xdg-open 失败: {}", stderr));
        }
    }

    #[cfg(target_os = "macos")]
    {
        let output = std::process::Command::new("open")
            .arg(uri)
            .output()
            .map_err(|e| format!("执行 open 失败: {}", e))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("open 失败: {}", stderr));
        }
    }

    #[cfg(target_os = "windows")]
    {
        let output = std::process::Command::new("cmd")
            .args(["/c", "start", uri])
            .output()
            .map_err(|e| format!("执行 start 失败: {}", e))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("start 失败: {}", stderr));
        }
    }

    Ok(())
}

#[tauri::command]
pub async fn switch_windsurf_account(state: State<'_, AppState>, email: String, password: Option<String>) -> Result<SwitchAccountResult, String> {
    let pw = password.unwrap_or_else(|| email.clone());
    log::info!("[一键登录] 开始登录 {}", email);

    let id_token = firebase_login(&email, &pw).await?;
    log::info!("[一键登录] Firebase 成功，正在切换...");

    let uri = format!("windsurf://codeium.windsurf/#access_token={}", urlencoding::encode(&id_token));
    open_windsurf_uri(&uri)?;
    log::info!("[一键登录] URI 已发送");

    // 记录当前登录账号
    {
        let mut current = state.current_account.lock().map_err(|_| "锁错误")?;
        *current = Some(email.clone());
    }

    Ok(SwitchAccountResult {
        email: email.clone(),
        message: format!("已切换到 {}", email),
        success: true,
    })
}

#[tauri::command]
pub async fn take_and_switch(state: State<'_, AppState>) -> Result<SwitchAccountResult, String> {
    let take_result = state.pool.take_account().map_err(|e| e.to_string())?;
    if take_result.email.is_empty() {
        return Ok(SwitchAccountResult {
            email: String::new(),
            message: take_result.message,
            success: false,
        });
    }

    let email = take_result.email;
    log::info!("[一键登录] 取用账号: {}", email);

    let id_token = firebase_login(&email, &email).await?;
    let uri = format!("windsurf://codeium.windsurf/#access_token={}", urlencoding::encode(&id_token));
    open_windsurf_uri(&uri)?;

    // 记录当前登录账号
    {
        let mut current = state.current_account.lock().map_err(|_| "锁错误")?;
        *current = Some(email.clone());
    }

    Ok(SwitchAccountResult {
        email: email.clone(),
        message: format!("已取用并切换到 {}", email),
        success: true,
    })
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

#[tauri::command]
pub fn get_current_account(state: State<AppState>) -> Result<Option<String>, String> {
    let current = state.current_account.lock().map_err(|_| "锁错误")?;
    Ok(current.clone())
}
