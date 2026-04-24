"""账号池管理器

管理 Windsurf 免费账号的配额轮换，支持日配额/周配额独立标记和自动重置。
使用 SQLite 持久化账号数据和状态。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Literal

try:
    from ..utils.logger import default_logger as logger
    from ..utils.path import resource_path, ensure_dir
except Exception:
    logger = logging.getLogger(__name__)

    def resource_path(*parts):
        return Path.cwd().joinpath(*parts).resolve()

    def ensure_dir(p):
        p.mkdir(parents=True, exist_ok=True)
        return p


AccountStatus = Literal["available", "exhausted"]


@dataclass
class PoolAccount:
    """账号池中的单个账号"""

    email: str
    status: AccountStatus = "available"
    daily_exhausted: bool = False
    weekly_exhausted: bool = False
    last_used_at: str = ""
    total_uses: int = 0
    notes: str = ""

    def is_available(self) -> bool:
        return self.status == "available" and not self.daily_exhausted


@dataclass
class PoolConfig:
    """账号池配置"""

    reset_timezone: str = "Asia/Shanghai"
    reset_hour: int = 16
    strategy: str = "round_robin"
    version: int = 1


@dataclass
class PoolState:
    """账号池运行状态"""

    next_index: int = 0
    last_reset_check: str = ""


class AccountPoolManager:
    """账号池管理器：SQLite 持久化，支持加载、保存、取用、标记、重置"""

    DEFAULT_DB_FILE = "data/account_pool.db"

    def __init__(self, db_file: Optional[str] = None):
        self.db_path = Path(db_file) if db_file else resource_path(self.DEFAULT_DB_FILE)
        ensure_dir(self.db_path.parent)
        self.config = PoolConfig()
        self.state = PoolState()
        self._init_db()
        self._load_config()
        self._load_state()
        self._migrate_from_json()

    # ── 数据库初始化 ──

    def _init_db(self) -> None:
        """初始化 SQLite 数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    email TEXT PRIMARY KEY NOT NULL,
                    status TEXT DEFAULT 'available',
                    daily_exhausted INTEGER DEFAULT 0,
                    weekly_exhausted INTEGER DEFAULT 0,
                    last_used_at TEXT DEFAULT '',
                    total_uses INTEGER DEFAULT 0,
                    notes TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_status ON accounts(status);
                CREATE INDEX IF NOT EXISTS idx_daily ON accounts(daily_exhausted);
                
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
                    last_reset_check TEXT DEFAULT ''
                );
            """)
            conn.commit()

    # ── 配置加载/保存 ──

    def _load_config(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM pool_config WHERE id = 1").fetchone()
            if row:
                self.config = PoolConfig(
                    reset_timezone=row[1],
                    reset_hour=row[2],
                    strategy=row[3],
                    version=row[4],
                )

    def _save_config(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO pool_config (id, reset_timezone, reset_hour, strategy, version)
                   VALUES (1, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   reset_timezone=excluded.reset_timezone,
                   reset_hour=excluded.reset_hour,
                   strategy=excluded.strategy,
                   version=excluded.version""",
                (self.config.reset_timezone, self.config.reset_hour,
                 self.config.strategy, self.config.version)
            )
            conn.commit()

    # ── 状态加载/保存 ──

    def _load_state(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM pool_state WHERE id = 1").fetchone()
            if row:
                self.state = PoolState(next_index=row[1], last_reset_check=row[2] or "")

    def _save_state(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO pool_state (id, next_index, last_reset_check)
                   VALUES (1, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   next_index=excluded.next_index,
                   last_reset_check=excluded.last_reset_check""",
                (self.state.next_index, self.state.last_reset_check)
            )
            conn.commit()

    # ── 账号 CRUD ──

    @property
    def accounts(self) -> List[PoolAccount]:
        """从数据库加载所有账号"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM accounts ORDER BY email").fetchall()
            return [
                PoolAccount(
                    email=row["email"],
                    status=row["status"],
                    daily_exhausted=bool(row["daily_exhausted"]),
                    weekly_exhausted=bool(row["weekly_exhausted"]),
                    last_used_at=row["last_used_at"] or "",
                    total_uses=row["total_uses"],
                    notes=row["notes"] or "",
                )
                for row in rows
            ]

    def _save_account(self, acc: PoolAccount) -> None:
        """保存单个账号到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO accounts (email, status, daily_exhausted, weekly_exhausted,
                                        last_used_at, total_uses, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(email) DO UPDATE SET
                   status=excluded.status,
                   daily_exhausted=excluded.daily_exhausted,
                   weekly_exhausted=excluded.weekly_exhausted,
                   last_used_at=excluded.last_used_at,
                   total_uses=excluded.total_uses,
                   notes=excluded.notes""",
                (acc.email, acc.status, int(acc.daily_exhausted), int(acc.weekly_exhausted),
                 acc.last_used_at, acc.total_uses, acc.notes)
            )
            conn.commit()

    def _delete_account(self, email: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM accounts WHERE email = ?", (email,))
            conn.commit()

    # ── 重置检查 ──

    def check_reset(self) -> tuple[int, int]:
        now = self._now()
        today_str = now.strftime("%Y-%m-%d")

        if self.state.last_reset_check == today_str:
            return 0, 0

        daily_reset = 0
        weekly_reset = 0

        with sqlite3.connect(self.db_path) as conn:
            # 日配额重置
            conn.execute(
                "UPDATE accounts SET daily_exhausted = 0, status = 'available' "
                "WHERE daily_exhausted = 1"
            )
            daily_reset = conn.total_changes

            # 周配额重置（周六）
            if now.weekday() == 5:  # Saturday
                conn.execute(
                    "UPDATE accounts SET weekly_exhausted = 0, status = 'available' "
                    "WHERE weekly_exhausted = 1"
                )
                weekly_reset = conn.total_changes

            conn.commit()

        self.state.last_reset_check = today_str
        self._save_state()
        logger.info("配额重置: 日重置 %d, 周重置 %d", daily_reset, weekly_reset)
        return daily_reset, weekly_reset

    # ── 取用 ──

    def get_next_available(self) -> Optional[PoolAccount]:
        self.check_reset()

        accs = self.accounts
        if not accs:
            return None

        n = len(accs)
        for i in range(n):
            idx = (self.state.next_index + i) % n
            acc = accs[idx]
            if acc.is_available():
                self.state.next_index = (idx + 1) % n
                acc.last_used_at = self._now().isoformat()
                acc.total_uses += 1
                self._save_account(acc)
                self._save_state()
                return acc

        return None

    # ── 标记 ──

    def mark_daily_exhausted(self, email: str) -> bool:
        acc = self._find(email)
        if not acc:
            return False
        acc.daily_exhausted = True
        if acc.weekly_exhausted:
            acc.status = "exhausted"
        self._save_account(acc)
        return True

    def mark_weekly_exhausted(self, email: str) -> bool:
        acc = self._find(email)
        if not acc:
            return False
        acc.weekly_exhausted = True
        acc.status = "exhausted"
        self._save_account(acc)
        return True

    def mark_available(self, email: str) -> bool:
        acc = self._find(email)
        if not acc:
            return False
        acc.daily_exhausted = False
        acc.weekly_exhausted = False
        acc.status = "available"
        self._save_account(acc)
        return True

    # ── 增删 ──

    def add_accounts(self, emails: List[str]) -> int:
        existing = {a.email for a in self.accounts}
        added = 0
        for email in emails:
            email = email.strip()
            if email and email not in existing:
                acc = PoolAccount(email=email)
                self._save_account(acc)
                existing.add(email)
                added += 1
        if added:
            logger.info("账号池新增 %d 个账号", added)
        return added

    def remove_account(self, email: str) -> bool:
        before = len(self.accounts)
        self._delete_account(email)
        after = len(self.accounts)
        if after < before:
            self.state.next_index = min(self.state.next_index, max(after - 1, 0))
            self._save_state()
            return True
        return False

    # ── 导入 ──

    def import_from_json(self, file_path: str | Path) -> int:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("导入文件不存在: %s", file_path)
            return 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            emails = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        emails.append(item)
                    elif isinstance(item, dict) and "email" in item:
                        emails.append(item["email"])

            return self.add_accounts(emails)
        except Exception as e:
            logger.error("导入失败: %s", e)
            return 0

    # ── 统计 ──

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            available = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE status = 'available' AND daily_exhausted = 0"
            ).fetchone()[0]
            daily_exhausted = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE daily_exhausted = 1"
            ).fetchone()[0]
            weekly_exhausted = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE weekly_exhausted = 1"
            ).fetchone()[0]
        return {
            "total": total,
            "available": available,
            "daily_exhausted": daily_exhausted,
            "weekly_exhausted": weekly_exhausted,
        }

    def get_next_reset_info(self) -> dict:
        now = self._now()
        today = now.date()
        reset_hour = self.config.reset_hour

        today_reset = now.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
        if now < today_reset:
            next_daily = today_reset
        else:
            next_daily = today_reset + timedelta(days=1)

        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0 and now >= today_reset:
            days_until_saturday = 7
        next_weekly = datetime.combine(
            today + timedelta(days=days_until_saturday),
            now.replace(hour=reset_hour, minute=0, second=0).time(),
        )

        return {
            "next_daily_reset": next_daily.isoformat(),
            "next_weekly_reset": next_weekly.isoformat(),
            "daily_in_seconds": int((next_daily - now).total_seconds()),
            "weekly_in_seconds": int((next_weekly - now).total_seconds()),
        }

    # ── 辅助 ──

    def _find(self, email: str) -> Optional[PoolAccount]:
        for acc in self.accounts:
            if acc.email == email:
                return acc
        return None

    def _now(self) -> datetime:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.config.reset_timezone)
            return datetime.now(tz).replace(tzinfo=None)
        except Exception:
            return datetime.now()

    def _migrate_from_json(self) -> None:
        """从旧版 JSON 文件迁移数据到 SQLite"""
        json_file = self.db_path.with_suffix(".json")
        if not json_file.exists():
            return
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 迁移配置
            cfg = data.get("config", {})
            self.config = PoolConfig(
                reset_timezone=cfg.get("reset_timezone", "Asia/Shanghai"),
                reset_hour=cfg.get("reset_hour", 16),
                strategy=cfg.get("strategy", "round_robin"),
                version=cfg.get("version", 1),
            )
            self._save_config()

            # 迁移状态
            st = data.get("state", {})
            self.state = PoolState(
                next_index=st.get("next_index", 0),
                last_reset_check=st.get("last_reset_check", ""),
            )
            self._save_state()

            # 迁移账号
            accounts_data = data.get("accounts", [])
            migrated = 0
            for d in accounts_data:
                acc = PoolAccount(
                    email=d.get("email", ""),
                    status=d.get("status", "available"),
                    daily_exhausted=d.get("daily_exhausted", False),
                    weekly_exhausted=d.get("weekly_exhausted", False),
                    last_used_at=d.get("last_used_at", ""),
                    total_uses=d.get("total_uses", 0),
                    notes=d.get("notes", ""),
                )
                if acc.email:
                    self._save_account(acc)
                    migrated += 1

            # 迁移完成后删除旧文件
            json_file.unlink()
            logger.info("已从 JSON 迁移 %d 个账号到 SQLite", migrated)
        except Exception as e:
            logger.warning("JSON 迁移失败: %s", e)
