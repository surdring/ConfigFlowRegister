use chrono::{Datelike, Duration, Local, TimeZone, Utc};
use std::path::PathBuf;
use std::sync::Mutex;
use anyhow::{Context, Result};

use crate::database::Database;
use crate::models::{Account, ImportResult, PoolStats, ResetInfo, TakeAccountResult};

pub struct AccountPool {
    db: Mutex<Database>,
    data_dir: PathBuf,
}

impl AccountPool {
    pub fn new(data_dir: PathBuf) -> Result<Self> {
        let db_path = data_dir.join("account_pool.db");
        std::fs::create_dir_all(&data_dir)
            .context("无法创建数据目录")?;
        
        let db = Database::new(&db_path)?;
        
        Ok(Self {
            db: Mutex::new(db),
            data_dir,
        })
    }

    pub fn get_data_dir(&self) -> &PathBuf {
        &self.data_dir
    }

    pub fn get_accounts(&self) -> Result<Vec<Account>> {
        let db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.get_all_accounts()
    }

    pub fn get_stats(&self) -> Result<PoolStats> {
        let db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.get_stats_sql()
    }

    /// 分页查询，支持搜索和状态过滤
    pub fn get_accounts_page(&self, page: i32, page_size: i32, search: Option<String>, status_filter: Option<String>) -> Result<(Vec<Account>, i32)> {
        let db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        let total = db.get_account_count(search.as_deref(), status_filter.as_deref())?;
        let offset = (page - 1) * page_size;
        let accounts = db.get_accounts_page(page_size, offset, search.as_deref(), status_filter.as_deref())?;
        Ok((accounts, total))
    }

    /// 批量标记日配额耗尽
    pub fn batch_mark_daily_exhausted(&self, emails: Vec<String>) -> Result<i32> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.batch_mark_daily_exhausted(&emails)
    }

    /// 批量标记周配额耗尽
    pub fn batch_mark_weekly_exhausted(&self, emails: Vec<String>) -> Result<i32> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.batch_mark_weekly_exhausted(&emails)
    }

    /// 批量取消标记
    pub fn batch_unmark_exhausted(&self, emails: Vec<String>) -> Result<i32> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.batch_unmark_exhausted(&emails)
    }

    /// 批量删除
    pub fn batch_delete_accounts(&self, emails: Vec<String>) -> Result<i32> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        let count = db.batch_delete_accounts(&emails)?;
        // 调整 next_index
        let remaining = db.get_account_count(None, None)?;
        let state = db.get_state()?;
        let new_index = std::cmp::min(state.next_index, std::cmp::max(remaining - 1, 0));
        db.update_next_index(new_index)?;
        Ok(count)
    }

    pub fn take_account(&self) -> Result<TakeAccountResult> {
        // Python: 先检查并重置配额
        self.check_and_reset()?;
        
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        let accounts = db.get_all_accounts()?;
        
        if accounts.is_empty() {
            return Ok(TakeAccountResult {
                email: String::new(),
                message: "账号池为空，请先导入账号".to_string(),
            });
        }
        
        let state = db.get_state()?;
        let n = accounts.len();
        let start_idx = state.next_index as usize % n;
        
        // Python: 从 next_index 开始轮询，保持顺序
        for i in 0..n {
            let idx = (start_idx + i) % n;
            let account = &accounts[idx];
            
            // Python: is_available() = status == 'available' AND not daily_exhausted
            if account.is_available() {
                // Python: 更新账号使用信息
                db.mark_account_used(&account.email)?;
                // Python: 更新 next_index = (idx + 1) % n
                let new_next = ((idx + 1) % n) as i32;
                db.update_next_index(new_next)?;
                
                return Ok(TakeAccountResult {
                    email: account.email.clone(),
                    message: format!("已取用账号: {}", account.email),
                });
            }
        }
        
        Ok(TakeAccountResult {
            email: String::new(),
            message: "没有可用账号，请稍后再试或导入新账号".to_string(),
        })
    }

    pub fn mark_daily_exhausted(&self, email: &str) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        // Python: 只设置 daily_exhausted=True，不改变 status
        // status 只在 weekly_exhausted 时才变为 exhausted
        db.update_exhausted_flags(email, Some(true), None)?;
        Ok(())
    }

    pub fn mark_weekly_exhausted(&self, email: &str) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        // Python: weekly_exhausted=True 时 status 变为 exhausted
        db.update_exhausted_flags(email, None, Some(true))?;
        Ok(())
    }

    pub fn unmark_exhausted(&self, email: &str) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        // Python: mark_available: daily=False, weekly=False, status=available
        db.update_exhausted_flags(email, Some(false), Some(false))?;
        Ok(())
    }

    pub fn delete_account(&self, email: &str) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.delete_account(email)?;
        // Python: 删除后调整 next_index
        let accounts = db.get_all_accounts()?;
        let state = db.get_state()?;
        let new_index = std::cmp::min(state.next_index, std::cmp::max(accounts.len() as i32 - 1, 0));
        db.update_next_index(new_index)?;
        Ok(())
    }

    pub fn import_accounts(&self, emails: Vec<String>) -> Result<ImportResult> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        
        let mut imported = 0;
        let mut skipped = 0;
        let mut errors = Vec::new();
        
        for email in emails {
            if email.is_empty() || !email.contains('@') {
                errors.push(format!("无效邮箱: {}", email));
                continue;
            }
            
            if db.account_exists(&email)? {
                skipped += 1;
                continue;
            }
            
            if let Err(e) = db.add_account(&email, "") {
                errors.push(format!("导入 {} 失败: {}", email, e));
            } else {
                imported += 1;
            }
        }
        
        Ok(ImportResult {
            imported,
            skipped,
            errors,
        })
    }

    pub fn import_from_json(&self, json_content: &str) -> Result<ImportResult> {
        // 支持混合数组: 字符串和对象混合 ["a@b.com", {"email": "c@d.com", ...}]
        let items: Vec<serde_json::Value> = serde_json::from_str(json_content)
            .context("JSON 解析失败")?;
        
        let emails: Vec<String> = items.iter().filter_map(|item| {
            if let Some(s) = item.as_str() {
                Some(s.to_string())
            } else if let Some(obj) = item.as_object() {
                obj.get("email").and_then(|v| v.as_str()).map(String::from)
            } else {
                None
            }
        }).collect();
        
        if emails.is_empty() {
            return Err(anyhow::anyhow!("JSON 中未找到任何邮箱"));
        }
        
        self.import_accounts(emails)
    }

    pub fn check_and_reset(&self) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        
        let state = db.get_state()?;
        let now = Utc::now();
        let now_local = now.with_timezone(&Local);
        let today_str = now_local.format("%Y-%m-%d").to_string();
        
        // Python: 用日期字符串比较
        let should_reset = if let Some(last_check) = state.last_reset_check {
            let last_check_str = last_check.with_timezone(&Local).format("%Y-%m-%d").to_string();
            today_str != last_check_str
        } else {
            true
        };
        
        if should_reset {
            let is_saturday = now_local.weekday() == chrono::Weekday::Sat;
            let updated = db.reset_daily_quota(is_saturday)?;
            db.update_state(state.next_index, &now)?;
            
            log::info!("配额已重置: {} 个账号, 周六={}", updated, is_saturday);
        }
        
        Ok(())
    }

    pub fn get_reset_info(&self) -> Result<ResetInfo> {
        let now = Local::now();
        let today_16 = now.date_naive().and_hms_opt(16, 0, 0)
            .map(|t| Local.from_local_datetime(&t).unwrap())
            .unwrap_or(now);
        
        let next_daily_reset = if now < today_16 {
            today_16
        } else {
            today_16 + Duration::days(1)
        };
        
        let days_until_saturday = (6 - now.weekday().num_days_from_monday() as i64 + 7) % 7;
        let days_until_saturday = if days_until_saturday == 0 && now >= today_16 {
            7
        } else if days_until_saturday == 0 {
            0
        } else {
            days_until_saturday
        };
        
        let next_weekly_reset = today_16 + Duration::days(days_until_saturday);
        
        let daily_duration = next_daily_reset - now;
        let weekly_duration = next_weekly_reset - now;
        
        let daily_reset_in = format_duration(daily_duration);
        let weekly_reset_in = format_duration(weekly_duration);
        
        Ok(ResetInfo {
            next_daily_reset,
            next_weekly_reset,
            daily_reset_in,
            weekly_reset_in,
        })
    }

    /// 更新账号额度信息
    pub fn update_account_credits(&self, email: &str, api_key: Option<&str>, plan_name: Option<&str>, daily_percent: Option<f64>, weekly_percent: Option<f64>) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.update_account_credits(email, api_key, plan_name, daily_percent, weekly_percent)
    }

    /// 更新账号耗尽标记（None 表示不修改对应字段）
    pub fn update_exhausted_flags(&self, email: &str, daily: Option<bool>, weekly: Option<bool>) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.update_exhausted_flags(email, daily, weekly)?;
        Ok(())
    }

    /// 获取账号 api_key
    pub fn get_account_api_key(&self, email: &str) -> Result<Option<String>> {
        let db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.get_account_api_key(email)
    }

    /// 获取单个账号
    pub fn get_account_by_email(&self, email: &str) -> Result<Option<Account>> {
        let db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.get_account_by_email(email)
    }

    /// 更新账号上次使用时间和使用次数
    pub fn mark_account_used(&self, email: &str) -> Result<()> {
        let mut db = self.db.lock().map_err(|_| anyhow::anyhow!("数据库锁错误"))?;
        db.mark_account_used(email)?;
        Ok(())
    }
}

fn format_duration(duration: Duration) -> String {
    let days = duration.num_days();
    let hours = duration.num_hours() % 24;
    let minutes = duration.num_minutes() % 60;
    
    if days > 0 {
        format!("{}天{}小时{}分", days, hours, minutes)
    } else if hours > 0 {
        format!("{}小时{}分", hours, minutes)
    } else {
        format!("{}分", minutes)
    }
}
