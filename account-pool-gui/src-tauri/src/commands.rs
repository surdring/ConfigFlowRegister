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
#[allow(non_snake_case)]
struct FirebaseResponse {
    idToken: Option<String>,
    error: Option<FirebaseError>,
}

#[derive(Debug, Deserialize)]
struct FirebaseError {
    message: Option<String>,
}

/// 获取系统代理配置（支持 GNOME gsettings）
#[cfg(target_os = "linux")]
fn get_system_proxy() -> Option<String> {
    // 尝试读取 GNOME 系统代理设置
    let modes = [
        ("org.gnome.system.proxy", "mode"),
        ("org.gnome.desktop.interface", "proxy-mode"),
    ];
    
    for (schema, key) in &modes {
        let mode = std::process::Command::new("gsettings")
            .args(&["get", schema, key])
            .output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .map(|s| s.trim().trim_matches('\'').to_string());
        
        if let Some(m) = mode {
            if m == "manual" || m == "1" {
                // 读取 HTTP 代理设置
                let proxy = std::process::Command::new("gsettings")
                    .args(&["get", "org.gnome.system.proxy.http", "host"])
                    .output()
                    .ok()
                    .and_then(|o| String::from_utf8(o.stdout).ok())
                    .map(|s| s.trim().trim_matches('\'').to_string());
                
                let port = std::process::Command::new("gsettings")
                    .args(&["get", "org.gnome.system.proxy.http", "port"])
                    .output()
                    .ok()
                    .and_then(|o| String::from_utf8(o.stdout).ok())
                    .and_then(|s| s.trim().parse::<u16>().ok());
                
                if let (Some(host), Some(p)) = (proxy, port) {
                    let url = format!("http://{}:{}", host, p);
                    log::info!("[HTTP] 检测到 GNOME 系统代理: {}", url);
                    return Some(url);
                }
            }
        }
    }
    None
}

#[cfg(not(target_os = "linux"))]
fn get_system_proxy() -> Option<String> {
    None
}

/// 测试代理是否可达（支持域名解析）
fn test_proxy_reachable(url: &str) -> bool {
    let parsed = url.trim_start_matches("http://").trim_start_matches("https://");
    let addr_part = parsed.trim_end_matches('/');
    
    // 解析 host:port
    let parts: Vec<&str> = addr_part.split(':').collect();
    if parts.len() != 2 {
        return false;
    }
    
    let host = parts[0];
    let port: u16 = match parts[1].parse() {
        Ok(p) => p,
        Err(_) => return false,
    };
    
    // 先尝试直接作为 SocketAddr 解析（IP 格式）
    if let Ok(addr) = addr_part.parse::<std::net::SocketAddr>() {
        return std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(2)).is_ok();
    }
    
    // 否则作为域名解析
    match std::net::ToSocketAddrs::to_socket_addrs(&(host, port)) {
        Ok(addrs) => {
            for addr in addrs {
                if std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(2)).is_ok() {
                    log::info!("[HTTP] 代理 {} 解析到 {:?} 可达", url, addr);
                    return true;
                }
            }
            log::warn!("[HTTP] 代理 {} 解析成功但无可用地址", url);
            false
        }
        Err(e) => {
            log::warn!("[HTTP] 代理 {} DNS 解析失败: {}", url, e);
            false
        }
    }
}

/// 分类网络错误类型，提供详细诊断信息
fn classify_network_error(error: &reqwest::Error, host: &str) -> String {
    let error_str = error.to_string().to_lowercase();
    
    // DNS 解析失败
    if error_str.contains("dns") 
        || error_str.contains("resolve") 
        || error_str.contains("name") 
        || error_str.contains("host not found")
        || error_str.contains("nodename nor servname provided") {
        return format!(
            "DNS 解析失败 - 无法解析域名 '{}'. 可能原因: 1) DNS 服务器配置错误 2) 域名被污染 3) 网络连接断开. 建议: 检查 /etc/resolv.conf 或尝试更换 DNS (如 8.8.8.8)",
            host
        );
    }
    
    // 连接超时或拒绝
    if error_str.contains("timeout") {
        return format!(
            "连接超时 - 无法连接到 '{}'. 可能原因: 1) 防火墙阻止 2) 需要代理 3) 服务器无响应. 建议: 检查网络连通性 (ping {})",
            host, host
        );
    }
    
    if error_str.contains("refused") || error_str.contains("reset") {
        return format!(
            "连接被拒绝 - 目标主机 '{}' 拒绝了连接. 可能原因: 1) 服务器未运行 2) 防火墙阻止 3) 路由问题",
            host
        );
    }
    
    // TLS/SSL 错误
    if error_str.contains("tls") 
        || error_str.contains("ssl") 
        || error_str.contains("certificate")
        || error_str.contains("handshake") {
        return format!(
            "TLS/SSL 错误 - 与 '{}' 建立安全连接失败. 可能原因: 1) 系统时间不正确 2) 缺少 CA 证书 3) 证书被中间人篡改. 建议: 检查系统时间和更新 ca-certificates",
            host
        );
    }
    
    // 代理相关错误
    if error_str.contains("proxy") {
        return format!(
            "代理错误 - 通过代理连接到 '{}' 失败. 可能原因: 1) 代理服务器无响应 2) 代理配置错误 3) 代理需要认证",
            host
        );
    }
    
    // 网络不可达
    if error_str.contains("unreachable") 
        || error_str.contains("network")
        || error_str.contains("no route") {
        return format!(
            "网络不可达 - 无法路由到 '{}'. 可能原因: 1) 网络接口未启用 2) 网关配置错误 3) 目标网络不可达",
            host
        );
    }
    
    // 默认返回原始错误
    format!("{} (主机: {})", error, host)
}

/// 创建 HTTP 客户端（自动检测系统代理环境变量，代理不可达则直连）
fn create_http_client() -> Result<reqwest::Client, String> {
    let mut builder = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .no_proxy()
        .local_address(std::net::IpAddr::V4(std::net::Ipv4Addr::UNSPECIFIED));

    // 优先读取环境变量（HTTPS_PROXY > HTTP_PROXY）
    let proxy_url = std::env::var("HTTPS_PROXY")
        .or_else(|_| std::env::var("https_proxy"))
        .or_else(|_| std::env::var("HTTP_PROXY"))
        .or_else(|_| std::env::var("http_proxy"))
        .or_else(|_| get_system_proxy().ok_or_else(|| String::new()));

    if let Ok(url) = proxy_url {
        if test_proxy_reachable(&url) {
            if let Ok(proxy) = reqwest::Proxy::all(&url) {
                log::info!("[HTTP] 使用代理: {}", url);
                builder = builder.proxy(proxy);
            }
        } else {
            log::warn!("[HTTP] 代理不可达，将尝试直连: {}", url);
        }
    } else {
        log::info!("[HTTP] 未检测到代理配置，使用直连");
    }

    builder.build().map_err(|e| format!("HTTP 客户端创建失败: {}", e))
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
        .map_err(|e| {
            let detailed = classify_network_error(&e, "identitytoolkit.googleapis.com");
            format!("Firebase 请求失败: {}", detailed)
        })?;

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

/// Auth1 登录结果
struct Auth1Tokens {
    session_token: String,
    one_time_auth_token: String,
}

/// Auth1 登录（3 步：password login → PostAuth → GetOneTimeAuthToken）
async fn auth1_login(email: &str, password: &str) -> Result<Auth1Tokens, String> {
    let client = create_http_client()?;

    // Step 1: password login → 获取 auth1 token
    let resp = client
        .post("https://windsurf.com/_devin-auth/password/login")
        .header("Content-Type", "application/json")
        .header("Referer", "https://windsurf.com/")
        .json(&serde_json::json!({ "email": email, "password": password }))
        .send()
        .await
        .map_err(|e| {
            let detailed = classify_network_error(&e, "windsurf.com");
            format!("Auth1 Step1 请求失败: {}", detailed)
        })?;

    #[derive(Deserialize)]
    #[allow(non_snake_case)]
    struct Auth1Step1Response {
        token: Option<String>,
        detail: Option<String>,
    }

    let data: Auth1Step1Response = resp
        .json()
        .await
        .map_err(|e| format!("Auth1 Step1 响应解析失败: {}", e))?;

    if let Some(detail) = data.detail {
        return Err(format!("Auth1 登录失败: {}", detail));
    }
    let auth1_token = data.token.ok_or_else(|| "Auth1 未返回 token".to_string())?;
    log::info!("[Auth1] Step1 登录成功");

    // Step 2: PostAuth → 获取 sessionToken
    let resp = client
        .post("https://server.self-serve.windsurf.com/exa.seat_management_pb.SeatManagementService/WindsurfPostAuth")
        .header("Content-Type", "application/json")
        .header("Connect-Protocol-Version", "1")
        .json(&serde_json::json!({ "auth1Token": auth1_token, "orgId": "" }))
        .send()
        .await
        .map_err(|e| format!("Auth1 Step2 PostAuth 请求失败: {}", e))?;

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Auth1 Step2 响应解析失败: {}", e))?;

    let session_token = data.get("sessionToken")
        .and_then(|v| v.as_str())
        .ok_or_else(|| format!("Auth1 PostAuth 未返回 sessionToken: {}", data))?;
    log::info!("[Auth1] Step2 PostAuth 成功");

    // Step 3: GetOneTimeAuthToken → 获取 oneTimeAuthToken
    let resp = client
        .post("https://server.self-serve.windsurf.com/exa.seat_management_pb.SeatManagementService/GetOneTimeAuthToken")
        .header("Content-Type", "application/json")
        .header("Connect-Protocol-Version", "1")
        .json(&serde_json::json!({ "authToken": session_token }))
        .send()
        .await
        .map_err(|e| format!("Auth1 Step3 OTT 请求失败: {}", e))?;

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Auth1 Step3 响应解析失败: {}", e))?;

    let ott = data.get("authToken")
        .and_then(|v| v.as_str())
        .ok_or_else(|| format!("Auth1 OTT 未返回 authToken: {}", data))?;
    log::info!("[Auth1] Step3 OTT 成功");

    Ok(Auth1Tokens {
        session_token: session_token.to_string(),
        one_time_auth_token: ott.to_string(),
    })
}

/// 用 token 注册 Codeium 获取 apiKey
async fn register_codeium(token: &str) -> Result<String, String> {
    let url = "https://api.codeium.com/register_user/";
    let client = create_http_client()?;
    
    let resp = client
        .post(url)
        .header("Content-Type", "application/json")
        .json(&serde_json::json!({ "firebase_id_token": token }))
        .send()
        .await
        .map_err(|e| format!("Codeium 注册请求失败: {}", e))?;
    
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Codeium 响应解析失败: {}", e))?;
    
    let api_key = data.get("api_key")
        .and_then(|v| v.as_str())
        .ok_or_else(|| format!("Codeium 未返回 api_key: {}", data))?;
    
    log::info!("[Codeium] 注册成功, apiKey={}...", &api_key[..api_key.len().min(20)]);
    Ok(api_key.to_string())
}

/// 用 apiKey 查询 Windsurf 额度信息
async fn get_user_status(api_key: &str) -> Result<CreditInfo, String> {
    let hosts = [
        "server.codeium.com",
        "server.self-serve.windsurf.com",
    ];
    
    let client = create_http_client()?;
    let body = serde_json::json!({
        "metadata": {
            "apiKey": api_key,
            "ideName": "windsurf",
            "ideVersion": "1.9600.41",
            "extensionName": "windsurf",
            "extensionVersion": "1.9600.41",
            "locale": "en"
        }
    });
    
    let path = "/exa.seat_management_pb.SeatManagementService/GetUserStatus";
    
    for host in &hosts {
        let url = format!("https://{}{}", host, path);
        match client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("Connect-Protocol-Version", "1")
            .json(&body)
            .send()
            .await
        {
            Ok(resp) => {
                let status = resp.status();
                let data: serde_json::Value = resp.json().await
                    .map_err(|e| format!("额度响应解析失败: {}", e))?;
                
                if status.is_success() {
                    let user_status = data.get("userStatus").and_then(|v| v.as_object())
                        .or_else(|| data.as_object());
                    
                    let plan_status = user_status.and_then(|v| v.get("planStatus")).and_then(|v| v.as_object());
                    let plan = plan_status.and_then(|v| v.get("planInfo")).and_then(|v| v.as_object());
                    
                    let plan_name = plan.and_then(|v| v.get("planName"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("Unknown");
                    
                    let daily_percent = plan_status
                        .and_then(|v| v.get("dailyQuotaRemainingPercent"))
                        .and_then(|v| v.as_f64());
                    
                    let weekly_percent = plan_status
                        .and_then(|v| v.get("weeklyQuotaRemainingPercent"))
                        .and_then(|v| v.as_f64());
                    
                    log::info!("[额度查询] {}: plan={}, daily={:?}, weekly={:?}", host, plan_name, daily_percent, weekly_percent);
                    
                    return Ok(CreditInfo {
                        plan_name: plan_name.to_string(),
                        daily_percent: daily_percent.unwrap_or(0.0),
                        weekly_percent: weekly_percent.unwrap_or(0.0),
                    });
                }
            }
            Err(e) => {
                log::warn!("[额度查询] {} 失败: {}", host, e);
            }
        }
    }
    
    Err("所有额度查询主机均失败".to_string())
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

/// 登录结果：uri_token 用于 windsurf:// URI，codeium_token 用于 Codeium 注册
struct LoginTokens {
    uri_token: String,
    codeium_token: String,
}

/// 统一登录：优先 Auth1，失败回退 Firebase
async fn login_with_fallback(email: &str, password: &str) -> Result<LoginTokens, String> {
    match auth1_login(email, password).await {
        Ok(tokens) => {
            log::info!("[登录] Auth1 成功");
            Ok(LoginTokens {
                uri_token: tokens.session_token.clone(),
                codeium_token: tokens.one_time_auth_token,
            })
        }
        Err(auth1_err) => {
            log::warn!("[登录] Auth1 失败: {}，尝试 Firebase...", auth1_err);
            match firebase_login(email, password).await {
                Ok(id_token) => {
                    log::info!("[登录] Firebase 成功");
                    Ok(LoginTokens {
                        uri_token: id_token.clone(),
                        codeium_token: id_token,
                    })
                }
                Err(fb_err) => {
                    Err(format!("Auth1 和 Firebase 均失败: Auth1({}) Firebase({})", auth1_err, fb_err))
                }
            }
        }
    }
}

/// 后台刷新额度：注册 Codeium → 查询额度 → 更新数据库 + 自动耗尽标记
fn spawn_credits_refresh(pool: Arc<AccountPool>, email: String, token: String) {
    tokio::spawn(async move {
        log::info!("[后台] 尝试注册 Codeium 获取额度: {}", email);

        match register_codeium(&token).await {
            Ok(api_key) => {
                match get_user_status(&api_key).await {
                    Ok(credits) => {
                        let _ = pool.update_account_credits(
                            &email,
                            Some(&api_key),
                            Some(&credits.plan_name),
                            Some(credits.daily_percent),
                            Some(credits.weekly_percent),
                        );

                        // 自动耗尽标记（<=0 视为耗尽）
                        let daily_exhausted = credits.daily_percent <= 0.0;
                        let weekly_exhausted = credits.weekly_percent <= 0.0;
                        let _ = pool.update_exhausted_flags(
                            &email,
                            Some(daily_exhausted),
                            Some(weekly_exhausted),
                        );
                        log::info!("[后台] 额度更新成功: {} plan={} daily={:.0}% weekly={:.0}%",
                            email, credits.plan_name, credits.daily_percent, credits.weekly_percent);
                    }
                    Err(e) => log::error!("[后台] 查询额度失败 {}: {}", email, e),
                }
            }
            Err(e) => log::error!("[后台] Codeium 注册失败 {}: {}", email, e),
        }
    });
}

#[tauri::command]
pub async fn switch_windsurf_account(state: State<'_, AppState>, email: String, password: Option<String>) -> Result<SwitchAccountResult, String> {
    let pw = password.unwrap_or_else(|| email.clone());
    log::info!("[一键登录] 开始登录 {}", email);

    let tokens = login_with_fallback(&email, &pw).await?;

    let uri = format!("windsurf://codeium.windsurf/#access_token={}", urlencoding::encode(&tokens.uri_token));
    open_windsurf_uri(&uri)?;
    log::info!("[一键登录] URI 已发送");

    // 记录当前登录账号
    {
        let mut current = state.current_account.lock().map_err(|_| "锁错误")?;
        *current = Some(email.clone());
    }

    // 更新上次使用时间和使用次数
    let _ = state.pool.mark_account_used(&email);

    // 后台刷新额度
    spawn_credits_refresh(Arc::clone(&state.pool), email.clone(), tokens.codeium_token);

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

    let tokens = login_with_fallback(&email, &email).await?;

    let uri = format!("windsurf://codeium.windsurf/#access_token={}", urlencoding::encode(&tokens.uri_token));
    open_windsurf_uri(&uri)?;

    // 记录当前登录账号
    {
        let mut current = state.current_account.lock().map_err(|_| "锁错误")?;
        *current = Some(email.clone());
    }

    // 后台刷新额度
    spawn_credits_refresh(Arc::clone(&state.pool), email.clone(), tokens.codeium_token);

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
pub async fn check_reset(state: State<'_, AppState>) -> Result<String, String> {
    // 1. 先重置配额
    state.pool.check_and_reset().map_err(|e| e.to_string())?;

    // 2. 批量刷新所有有 apiKey 的账号额度
    let accounts = state.pool.get_accounts().map_err(|e| e.to_string())?;
    let mut refreshed = 0;
    let mut failed = 0;

    for account in &accounts {
        if let Some(ref api_key) = account.api_key {
            match get_user_status(api_key).await {
                Ok(credits) => {
                    let _ = state.pool.update_account_credits(
                        &account.email,
                        Some(api_key),
                        Some(&credits.plan_name),
                        Some(credits.daily_percent),
                        Some(credits.weekly_percent),
                    );
                    let daily_exhausted = credits.daily_percent <= 0.0;
                    let weekly_exhausted = credits.weekly_percent <= 0.0;
                    let _ = state.pool.update_exhausted_flags(
                        &account.email,
                        Some(daily_exhausted),
                        Some(weekly_exhausted),
                    );
                    refreshed += 1;
                }
                Err(_) => {
                    failed += 1;
                }
            }
        }
    }

    Ok(format!("配额已重置，额度已刷新: {} 成功, {} 失败", refreshed, failed))
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

#[tauri::command]
pub async fn switch_account_via_cli(state: State<'_, AppState>, email: String) -> Result<SwitchAccountResult, String> {
    log::info!("[CLI 备选] 调用 Python 脚本切换账号: {}", email);

    // 只从数据目录查找脚本
    let data_dir = state.pool.get_data_dir();
    let script_path = data_dir.join("switch_windsurf_account.py");
    if !script_path.exists() {
        return Err(format!("未找到脚本: {:?}，请将 switch_windsurf_account.py 放到数据目录", script_path));
    }

    // --login-only --open：仅登录+打开URI，跳过 Codeium 注册
    let output = tokio::process::Command::new("python3")
        .arg(&script_path)
        .arg(&email)
        .arg("--method")
        .arg("auto")
        .arg("--login-only")
        .arg("--open")
        .output()
        .await
        .map_err(|e| format!("执行 Python 脚本失败: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    if output.status.success() {
        log::info!("[CLI 备选] 脚本执行成功: {}", stdout);

        // 记录当前登录账号
        {
            let mut current = state.current_account.lock().map_err(|_| "锁错误")?;
            *current = Some(email.clone());
        }

        // 更新上次使用时间和使用次数
        let _ = state.pool.mark_account_used(&email);

        Ok(SwitchAccountResult {
            email: email.clone(),
            message: format!("已通过 CLI 切换到 {}", email),
            success: true,
        })
    } else {
        let error_msg = format!("脚本执行失败: {} {}", stdout, stderr);
        log::error!("[CLI 备选] {}", error_msg);
        Err(error_msg)
    }
}

/// 刷新单个账号的额度信息（需要已有 apiKey，否则需要先登录）
#[tauri::command]
pub async fn refresh_account_credits(state: State<'_, AppState>, email: String) -> Result<SwitchAccountResult, String> {
    log::info!("[刷新额度] 开始刷新账号额度: {}", email);
    
    // 1. 检查是否已有 apiKey
    let api_key = match state.pool.get_account_api_key(&email) {
        Ok(Some(key)) => key,
        Ok(None) => {
            log::warn!("[刷新额度] {} 没有 apiKey，需要先登录", email);
            return Err("该账号没有 apiKey，请先一键登录以获取额度信息".to_string());
        }
        Err(e) => {
            return Err(format!("获取 apiKey 失败: {}", e));
        }
    };
    
    // 2. 查询额度
    let credits = get_user_status(&api_key).await?;
    
    // 3. 更新数据库
    state.pool.update_account_credits(
        &email,
        Some(&api_key),
        Some(&credits.plan_name),
        Some(credits.daily_percent),
        Some(credits.weekly_percent),
    ).map_err(|e| e.to_string())?;

    // B 方案：自动耗尽标记（<=0 视为耗尽）
    let daily_exhausted = credits.daily_percent <= 0.0;
    let weekly_exhausted = credits.weekly_percent <= 0.0;
    state
        .pool
        .update_exhausted_flags(&email, Some(daily_exhausted), Some(weekly_exhausted))
        .map_err(|e| e.to_string())?;
    
    log::info!("[刷新额度] {} 额度已更新: plan={} daily={:.0}% weekly={:.0}%", 
        email, credits.plan_name, credits.daily_percent, credits.weekly_percent);
    
    Ok(SwitchAccountResult {
        email: email.clone(),
        message: format!("{} 额度已刷新: {} 日{:.0}% 周{:.0}%", email, credits.plan_name, credits.daily_percent, credits.weekly_percent),
        success: true,
    })
}
