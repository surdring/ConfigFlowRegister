use chrono::{DateTime, NaiveDateTime, Utc};
use rusqlite::{params, Connection};
use std::path::Path;
use anyhow::{Context, Result as AnyhowResult};

use crate::models::{Account, AccountStatus, PoolConfig, PoolState, PoolStats, Strategy};

/// accounts 表的 SELECT 列名列表（避免重复拼写）
const ACCOUNT_COLUMNS: &str = "email, status, daily_exhausted, weekly_exhausted, last_used_at, total_uses, notes, api_key, plan_name, daily_percent, weekly_percent, credits_updated_at";

pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn new<P: AsRef<Path>>(db_path: P) -> AnyhowResult<Self> {
        let conn = Connection::open(db_path)
            .context("无法打开数据库")?;
        
        let mut db = Self { conn };
        db.init_tables()?;
        db.migrate()?;
        db.init_default_data()?;
        
        Ok(db)
    }

    /// 迁移：为旧表添加新列
    fn migrate(&mut self) -> AnyhowResult<()> {
        let columns = self.conn.prepare("SELECT * FROM accounts LIMIT 0")?;
        let existing: Vec<String> = columns.column_names().iter().map(|s| s.to_string()).collect();
        
        let migrations = [
            ("api_key", "ALTER TABLE accounts ADD COLUMN api_key TEXT DEFAULT NULL"),
            ("plan_name", "ALTER TABLE accounts ADD COLUMN plan_name TEXT DEFAULT NULL"),
            ("daily_percent", "ALTER TABLE accounts ADD COLUMN daily_percent REAL DEFAULT NULL"),
            ("weekly_percent", "ALTER TABLE accounts ADD COLUMN weekly_percent REAL DEFAULT NULL"),
            ("credits_updated_at", "ALTER TABLE accounts ADD COLUMN credits_updated_at TEXT DEFAULT NULL"),
        ];
        
        for (col, sql) in &migrations {
            if !existing.contains(&col.to_string()) {
                self.conn.execute_batch(sql)?;
            }
        }
        
        Ok(())
    }

    fn init_tables(&mut self) -> AnyhowResult<()> {
        self.conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS accounts (
                email TEXT PRIMARY KEY NOT NULL,
                status TEXT DEFAULT 'available',
                daily_exhausted INTEGER DEFAULT 0,
                weekly_exhausted INTEGER DEFAULT 0,
                last_used_at TEXT DEFAULT NULL,
                total_uses INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                api_key TEXT DEFAULT NULL,
                plan_name TEXT DEFAULT NULL,
                daily_percent REAL DEFAULT NULL,
                weekly_percent REAL DEFAULT NULL,
                credits_updated_at TEXT DEFAULT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_status ON accounts(status);
            CREATE INDEX IF NOT EXISTS idx_daily ON accounts(daily_exhausted);
            CREATE INDEX IF NOT EXISTS idx_email ON accounts(email);

            CREATE TABLE IF NOT EXISTS pool_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                reset_timezone TEXT DEFAULT 'Asia/Shanghai',
                reset_hour INTEGER DEFAULT 16,
                strategy TEXT DEFAULT 'round_robin',
                version INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS pool_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                next_index INTEGER DEFAULT 0,
                last_reset_check TEXT DEFAULT NULL
            );
            "#
        ).context("创建表失败")?;
        
        Ok(())
    }

    fn init_default_data(&mut self) -> AnyhowResult<()> {
        let tx = self.conn.transaction()?;
        
        let config_count: i32 = tx.query_row(
            "SELECT COUNT(*) FROM pool_config WHERE id = 1",
            [],
            |row| row.get(0),
        )?;
        
        if config_count == 0 {
            tx.execute(
                "INSERT INTO pool_config (id, reset_timezone, reset_hour, strategy, version) VALUES (1, 'Asia/Shanghai', 16, 'round_robin', 1)",
                [],
            )?;
        }
        
        let state_count: i32 = tx.query_row(
            "SELECT COUNT(*) FROM pool_state WHERE id = 1",
            [],
            |row| row.get(0),
        )?;
        
        if state_count == 0 {
            tx.execute(
                "INSERT INTO pool_state (id, next_index, last_reset_check) VALUES (1, 0, NULL)",
                [],
            )?;
        }
        
        tx.commit()?;
        Ok(())
    }

    fn row_to_account(row: &rusqlite::Row) -> rusqlite::Result<Account> {
        let status_str: String = row.get(1)?;
        let status = match status_str.as_str() {
            "exhausted" => AccountStatus::Exhausted,
            _ => AccountStatus::Available,
        };
        let last_used_at: Option<String> = row.get(4)?;
        let last_used_at = last_used_at.and_then(|s| {
            NaiveDateTime::parse_from_str(&s, "%Y-%m-%d %H:%M:%S").ok()
                .map(|dt| DateTime::from_naive_utc_and_offset(dt, Utc))
        });
        let credits_updated_at: Option<String> = row.get(11)?;
        let credits_updated_at = credits_updated_at.and_then(|s| {
            NaiveDateTime::parse_from_str(&s, "%Y-%m-%d %H:%M:%S").ok()
                .map(|dt| DateTime::from_naive_utc_and_offset(dt, Utc))
        });
        Ok(Account {
            email: row.get(0)?,
            status,
            daily_exhausted: row.get(2)?,
            weekly_exhausted: row.get(3)?,
            last_used_at,
            total_uses: row.get(5)?,
            notes: row.get(6)?,
            api_key: row.get(7)?,
            plan_name: row.get(8)?,
            daily_percent: row.get(9)?,
            weekly_percent: row.get(10)?,
            credits_updated_at,
        })
    }

    pub fn get_all_accounts(&self) -> AnyhowResult<Vec<Account>> {
        let mut stmt = self.conn.prepare(
            &format!("SELECT {} FROM accounts ORDER BY email", ACCOUNT_COLUMNS)
        )?;
        let accounts: Vec<Account> = stmt.query_map([], Self::row_to_account)?.filter_map(|a| a.ok()).collect();
        Ok(accounts)
    }

    /// 分页查询账号，支持搜索和状态过滤
    pub fn get_accounts_page(&self, limit: i32, offset: i32, search: Option<&str>, status_filter: Option<&str>) -> AnyhowResult<Vec<Account>> {
        let mut where_clauses = Vec::new();
        let mut params_vec: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
        
        if let Some(s) = search {
            where_clauses.push("email LIKE ?".to_string());
            params_vec.push(Box::new(format!("%{}%", s)));
        }
        if let Some(status) = status_filter {
            if status == "available" {
                where_clauses.push("status = 'available' AND daily_exhausted = 0".to_string());
            } else if status == "daily_exhausted" {
                where_clauses.push("daily_exhausted = 1".to_string());
            } else if status == "weekly_exhausted" {
                where_clauses.push("weekly_exhausted = 1".to_string());
            }
        }
        
        let where_sql = if where_clauses.is_empty() { "".to_string() } else { format!("WHERE {}", where_clauses.join(" AND ")) };
        let sql = format!(
            "SELECT {} FROM accounts {} ORDER BY email LIMIT ? OFFSET ?",
            ACCOUNT_COLUMNS, where_sql
        );
        
        params_vec.push(Box::new(limit));
        params_vec.push(Box::new(offset));
        let params_refs: Vec<&dyn rusqlite::ToSql> = params_vec.iter().map(|p| p.as_ref()).collect();
        
        let mut stmt = self.conn.prepare(&sql)?;
        let accounts: Vec<Account> = stmt
            .query_map(rusqlite::params_from_iter(params_refs), Self::row_to_account)?
            .filter_map(|a| a.ok())
            .collect();
        Ok(accounts)
    }

    /// 获取账号总数（带过滤）
    pub fn get_account_count(&self, search: Option<&str>, status_filter: Option<&str>) -> AnyhowResult<i32> {
        let mut where_clauses = Vec::new();
        let mut params_vec: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
        
        if let Some(s) = search {
            where_clauses.push("email LIKE ?".to_string());
            params_vec.push(Box::new(format!("%{}%", s)));
        }
        if let Some(status) = status_filter {
            if status == "available" {
                where_clauses.push("status = 'available' AND daily_exhausted = 0".to_string());
            } else if status == "daily_exhausted" {
                where_clauses.push("daily_exhausted = 1".to_string());
            } else if status == "weekly_exhausted" {
                where_clauses.push("weekly_exhausted = 1".to_string());
            }
        }
        
        let where_sql = if where_clauses.is_empty() { "".to_string() } else { format!("WHERE {}", where_clauses.join(" AND ")) };
        let sql = format!("SELECT COUNT(*) FROM accounts {}", where_sql);
        
        let params_refs: Vec<&dyn rusqlite::ToSql> = params_vec.iter().map(|p| p.as_ref()).collect();
        let count: i32 = self
            .conn
            .query_row(&sql, rusqlite::params_from_iter(params_refs), |row| row.get(0))?;
        Ok(count)
    }

    /// 用 SQL 直接统计，避免加载全部账号
    pub fn get_stats_sql(&self) -> AnyhowResult<PoolStats> {
        let total: i32 = self.conn.query_row("SELECT COUNT(*) FROM accounts", [], |row| row.get(0))?;
        let available: i32 = self.conn.query_row(
            "SELECT COUNT(*) FROM accounts WHERE status = 'available' AND daily_exhausted = 0", [], |row| row.get(0)
        )?;
        let daily_exhausted: i32 = self.conn.query_row(
            "SELECT COUNT(*) FROM accounts WHERE daily_exhausted = 1", [], |row| row.get(0)
        )?;
        let weekly_exhausted: i32 = self.conn.query_row(
            "SELECT COUNT(*) FROM accounts WHERE weekly_exhausted = 1", [], |row| row.get(0)
        )?;
        Ok(PoolStats { total, available, daily_exhausted, weekly_exhausted })
    }

    pub fn get_account_by_email(&self, email: &str) -> AnyhowResult<Option<Account>> {
        let mut stmt = self.conn.prepare(
            &format!("SELECT {} FROM accounts WHERE email = ?", ACCOUNT_COLUMNS)
        )?;
        let result = stmt.query_row([email], Self::row_to_account);
        match result {
            Ok(account) => Ok(Some(account)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    pub fn add_account(&mut self, email: &str, notes: &str) -> AnyhowResult<()> {
        self.conn.execute(
            "INSERT OR IGNORE INTO accounts (email, status, daily_exhausted, weekly_exhausted, total_uses, notes, api_key, plan_name, daily_percent, weekly_percent, credits_updated_at) VALUES (?, 'available', 0, 0, 0, ?, NULL, NULL, NULL, NULL, NULL)",
            params![email, notes],
        )?;
        Ok(())
    }

    /// 更新账号的耗尽标记，None 表示不修改该字段
    /// 优化：用单条 SQL 的 CASE WHEN 代替先查后改
    pub fn update_exhausted_flags(&mut self, email: &str, daily: Option<bool>, weekly: Option<bool>) -> AnyhowResult<()> {
        let daily_sql = match daily {
            Some(true) => "daily_exhausted = 1",
            Some(false) => "daily_exhausted = 0",
            None => "", // 不修改
        };
        let weekly_sql = match weekly {
            Some(true) => "weekly_exhausted = 1",
            Some(false) => "weekly_exhausted = 0",
            None => "", // 不修改
        };
        
        // 构建 SET 子句
        let mut sets = Vec::new();
        if !daily_sql.is_empty() { sets.push(daily_sql.to_string()); }
        if !weekly_sql.is_empty() { sets.push(weekly_sql.to_string()); }
        
        // status 逻辑: weekly_exhausted 决定 status
        if weekly.is_some() {
            let status_val = if weekly == Some(true) { "'exhausted'" } else { "'available'" };
            sets.push(format!("status = {}", status_val));
        } else if daily == Some(true) {
            // daily_exhausted=True 但 weekly 不变: status 需要根据当前 weekly 决定
            sets.push("status = CASE WHEN weekly_exhausted = 1 THEN 'exhausted' ELSE 'available' END".to_string());
        }
        
        if sets.is_empty() { return Ok(()); }
        
        let sql = format!("UPDATE accounts SET {} WHERE email = ?", sets.join(", "));
        self.conn.execute(&sql, [email])?;
        Ok(())
    }

    /// 批量标记日配额耗尽
    pub fn batch_mark_daily_exhausted(&mut self, emails: &[String]) -> AnyhowResult<i32> {
        let tx = self.conn.transaction()?;
        let mut count = 0;
        for email in emails {
            let changed = tx.execute(
                "UPDATE accounts SET daily_exhausted = 1, status = CASE WHEN weekly_exhausted = 1 THEN 'exhausted' ELSE 'available' END WHERE email = ? AND daily_exhausted = 0",
                [email],
            )?;
            count += changed;
        }
        tx.commit()?;
        Ok(count as i32)
    }

    /// 批量标记周配额耗尽
    pub fn batch_mark_weekly_exhausted(&mut self, emails: &[String]) -> AnyhowResult<i32> {
        let tx = self.conn.transaction()?;
        let mut count = 0;
        for email in emails {
            let changed = tx.execute(
                "UPDATE accounts SET weekly_exhausted = 1, status = 'exhausted' WHERE email = ? AND weekly_exhausted = 0",
                [email],
            )?;
            count += changed;
        }
        tx.commit()?;
        Ok(count as i32)
    }

    /// 批量取消标记
    pub fn batch_unmark_exhausted(&mut self, emails: &[String]) -> AnyhowResult<i32> {
        let tx = self.conn.transaction()?;
        let mut count = 0;
        for email in emails {
            let changed = tx.execute(
                "UPDATE accounts SET daily_exhausted = 0, weekly_exhausted = 0, status = 'available' WHERE email = ?",
                [email],
            )?;
            count += changed;
        }
        tx.commit()?;
        Ok(count as i32)
    }

    /// 批量删除
    pub fn batch_delete_accounts(&mut self, emails: &[String]) -> AnyhowResult<i32> {
        let tx = self.conn.transaction()?;
        let mut count = 0;
        for email in emails {
            let changed = tx.execute("DELETE FROM accounts WHERE email = ?", [email])?;
            count += changed;
        }
        tx.commit()?;
        Ok(count as i32)
    }

    pub fn mark_account_used(&mut self, email: &str) -> AnyhowResult<()> {
        let now = Utc::now().format("%Y-%m-%d %H:%M:%S").to_string();
        self.conn.execute(
            "UPDATE accounts SET last_used_at = ?, total_uses = total_uses + 1 WHERE email = ?",
            params![now, email],
        )?;
        Ok(())
    }

    pub fn delete_account(&mut self, email: &str) -> AnyhowResult<()> {
        self.conn.execute(
            "DELETE FROM accounts WHERE email = ?",
            [email],
        )?;
        Ok(())
    }

    pub fn get_config(&self) -> AnyhowResult<PoolConfig> {
        let config = self.conn.query_row(
            "SELECT reset_timezone, reset_hour, strategy, version FROM pool_config WHERE id = 1",
            [],
            |row| {
                let strategy_str: String = row.get(2)?;
                let strategy = match strategy_str.as_str() {
                    "round_robin" => Strategy::RoundRobin,
                    _ => Strategy::RoundRobin,
                };
                
                Ok(PoolConfig {
                    reset_timezone: row.get(0)?,
                    reset_hour: row.get(1)?,
                    strategy,
                    version: row.get(3)?,
                })
            },
        )?;
        
        Ok(config)
    }

    pub fn get_state(&self) -> AnyhowResult<PoolState> {
        let state = self.conn.query_row(
            "SELECT next_index, last_reset_check FROM pool_state WHERE id = 1",
            [],
            |row| {
                let last_reset_check: Option<String> = row.get(1)?;
                let last_reset_check = last_reset_check.and_then(|s| {
                    // 尝试解析日期字符串 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
                    if s.len() >= 10 {
                        NaiveDateTime::parse_from_str(&s, "%Y-%m-%d %H:%M:%S").ok()
                            .map(|dt| DateTime::from_naive_utc_and_offset(dt, Utc))
                            .or_else(|| {
                                chrono::NaiveDate::parse_from_str(&s[..10], "%Y-%m-%d").ok()
                                    .map(|d| d.and_hms_opt(0, 0, 0).unwrap())
                                    .map(|dt| DateTime::from_naive_utc_and_offset(dt, Utc))
                            })
                    } else {
                        None
                    }
                });
                
                Ok(PoolState {
                    next_index: row.get(0)?,
                    last_reset_check,
                })
            },
        )?;
        
        Ok(state)
    }

    pub fn update_state(&mut self, next_index: i32, last_reset_check: &DateTime<Utc>) -> AnyhowResult<()> {
        let check_str = last_reset_check.format("%Y-%m-%d %H:%M:%S").to_string();
        self.conn.execute(
            "UPDATE pool_state SET next_index = ?, last_reset_check = ? WHERE id = 1",
            params![next_index, check_str],
        )?;
        Ok(())
    }

    pub fn update_next_index(&mut self, next_index: i32) -> AnyhowResult<()> {
        self.conn.execute(
            "UPDATE pool_state SET next_index = ? WHERE id = 1",
            [next_index],
        )?;
        Ok(())
    }

    /// 重置日配额/周配额，匹配 Python 逻辑
    /// Python: 日配额重置 daily_exhausted=0, status='available'
    /// Python: 周六额外重置 weekly_exhausted=0, status='available'
    pub fn reset_daily_quota(&mut self, is_saturday: bool) -> AnyhowResult<i32> {
        let daily_reset = self.conn.execute(
            "UPDATE accounts SET daily_exhausted = 0, status = 'available' WHERE daily_exhausted = 1",
            [],
        )? as i32;
        
        let weekly_reset = if is_saturday {
            self.conn.execute(
                "UPDATE accounts SET weekly_exhausted = 0, status = 'available' WHERE weekly_exhausted = 1",
                [],
            )? as i32
        } else {
            0
        };
        
        Ok(daily_reset + weekly_reset)
    }

    pub fn account_exists(&self, email: &str) -> AnyhowResult<bool> {
        let count: i32 = self.conn.query_row(
            "SELECT COUNT(*) FROM accounts WHERE email = ?",
            [email],
            |row| row.get(0),
        )?;
        Ok(count > 0)
    }

    /// 更新账号的 API key 和额度信息
    pub fn update_account_credits(&mut self, email: &str, api_key: Option<&str>, plan_name: Option<&str>, daily_percent: Option<f64>, weekly_percent: Option<f64>) -> AnyhowResult<()> {
        let now = Utc::now().format("%Y-%m-%d %H:%M:%S").to_string();
        self.conn.execute(
            "UPDATE accounts SET api_key = ?, plan_name = ?, daily_percent = ?, weekly_percent = ?, credits_updated_at = ? WHERE email = ?",
            params![api_key, plan_name, daily_percent, weekly_percent, now, email],
        )?;
        Ok(())
    }

    /// 获取账号的 api_key
    pub fn get_account_api_key(&self, email: &str) -> AnyhowResult<Option<String>> {
        let api_key: Option<String> = self.conn.query_row(
            "SELECT api_key FROM accounts WHERE email = ?",
            [email],
            |row| row.get(0),
        )?;
        Ok(api_key)
    }
}
