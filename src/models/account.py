from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

AccountStatus = Literal["pending", "in_progress", "success", "failed"]


@dataclass
class Account:
    """WindSurf账号实体（从 data_manager 抽取）"""

    # 主键
    id: int

    # 账号信息
    email: str
    username: str
    password: str = ""
    first_name: str = ""
    last_name: str = ""

    # 状态管理
    status: AccountStatus = "pending"
    error_message: Optional[str] = None
    retry_count: int = 0

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "password": self.password,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "status": self.status,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        data = data.copy()
        data["created_at"] = datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at")
        if data.get("started_at"):
            data["started_at"] = datetime.fromisoformat(data["started_at"]) if isinstance(data.get("started_at"), str) else data.get("started_at")
        if data.get("completed_at"):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"]) if isinstance(data.get("completed_at"), str) else data.get("completed_at")
        return cls(**data)
