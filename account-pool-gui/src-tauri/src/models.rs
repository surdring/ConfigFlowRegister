use chrono::{DateTime, Local, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Account {
    pub email: String,
    pub status: AccountStatus,
    pub daily_exhausted: bool,
    pub weekly_exhausted: bool,
    pub last_used_at: Option<DateTime<Utc>>,
    pub total_uses: i32,
    pub notes: String,
    pub api_key: Option<String>,
    pub plan_name: Option<String>,
    pub daily_percent: Option<f64>,
    pub weekly_percent: Option<f64>,
    pub credits_updated_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum AccountStatus {
    Available,
    Exhausted,
}

impl Account {
    pub fn display_status(&self) -> String {
        if self.weekly_exhausted {
            "周耗尽".to_string()
        } else if self.daily_exhausted {
            "日耗尽".to_string()
        } else {
            "可用".to_string()
        }
    }

    pub fn status_icon(&self) -> &'static str {
        if self.weekly_exhausted {
            "🟠"
        } else if self.daily_exhausted {
            "🟡"
        } else {
            "🟢"
        }
    }

    /// Python: is_available() = status == 'available' AND not daily_exhausted
    /// 注意：status 只在 weekly_exhausted 时才变为 exhausted
    pub fn is_available(&self) -> bool {
        self.status == AccountStatus::Available && !self.daily_exhausted
    }

    /// 获取额度显示文本
    pub fn credit_display(&self) -> String {
        match (self.daily_percent, self.weekly_percent) {
            (Some(d), Some(w)) => format!("日{:.0}% 周{:.0}%", d, w),
            (Some(d), None) => format!("日{:.0}%", d),
            (None, Some(w)) => format!("周{:.0}%", w),
            (None, None) => "-".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PoolConfig {
    pub reset_timezone: String,
    pub reset_hour: i32,
    pub strategy: Strategy,
    pub version: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Strategy {
    RoundRobin,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PoolState {
    pub next_index: i32,
    pub last_reset_check: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PoolStats {
    pub total: i32,
    pub available: i32,
    pub daily_exhausted: i32,
    pub weekly_exhausted: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditInfo {
    pub plan_name: String,
    pub daily_percent: f64,
    pub weekly_percent: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResetInfo {
    pub next_daily_reset: DateTime<Local>,
    pub next_weekly_reset: DateTime<Local>,
    pub daily_reset_in: String,
    pub weekly_reset_in: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TakeAccountResult {
    pub email: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImportResult {
    pub imported: i32,
    pub skipped: i32,
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SwitchAccountResult {
    pub email: String,
    pub message: String,
    pub success: bool,
}
