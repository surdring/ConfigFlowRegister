"""
数据管理模块

包含所有数据模型类和数据管理功能。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, List
from pathlib import Path
import json
import subprocess
import random
import string

# 使用相对导入（支持PyInstaller打包）
try:
    from ..utils.logger import default_logger as logger
    from ..utils.exceptions import ValidationError, EmailGeneratorError, FileCorruptedError
except ImportError:
    # 打包后的导入路径
    try:
        from src.utils.logger import default_logger as logger
        from src.utils.exceptions import ValidationError, EmailGeneratorError, FileCorruptedError
    except ImportError:
        # 最后尝试添加路径
        import sys
        import os
        # 添加src目录到Python路径
        src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        from src.utils.logger import default_logger as logger
        from src.utils.exceptions import ValidationError, EmailGeneratorError, FileCorruptedError


# 类型定义
AccountStatus = Literal["pending", "in_progress", "success", "failed"]
# success = 注册成功（简单模式和完整模式都使用此状态）
TaskStatus = Literal["not_started", "in_progress", "paused", "completed", "failed"]
ExportFormat = Literal["csv", "json"]
BrowserType = Literal["chrome", "firefox", "edge"]

# 抽取后的 Account 模型
try:
    from ..models.account import Account
except Exception:
    from src.models.account import Account  # type: ignore


@dataclass
class EmailConfig:
    """邮箱配置"""
    address: str                    # QQ邮箱地址
    password: str                   # 授权码
    imap_server: str = "imap.qq.com"
    imap_port: int = 993
    
    # 验证邮件识别策略
    sender_pattern: str = "noreply@windsurf.com"
    subject_keywords: List[str] = field(default_factory=lambda: ["windsurf", "verification", "verify"])
    time_window_seconds: int = 300  # 5分钟


@dataclass
class RegistrationConfig:
    """注册配置"""
    default_count: int = 10         # 默认注册数量
    interval_seconds: int = 5       # 账号间隔时间（秒）
    browser_type: BrowserType = "chrome"
    headless: bool = False          # 有头模式（默认）
    timeout_seconds: int = 30       # 网络请求超时
    max_retries: int = 3            # 最大重试次数
    domain: str = "yaoshangxian.top"
    url: str = "https://windsurf.com/account/register"
    password: str = ""


@dataclass
class ExportConfig:
    """导出配置"""
    format: ExportFormat = "csv"    # 导出格式
    include_failed: bool = False    # 是否包含失败账号


@dataclass
class Configuration:
    """应用总配置"""
    email: EmailConfig
    registration: RegistrationConfig
    export: ExportConfig
    
    @classmethod
    def from_json(cls, config_dict: dict) -> "Configuration":
        """从JSON配置文件加载"""
        email_data = config_dict.get("email", {})
        reg_data = config_dict.get("registration", {})
        export_data = config_dict.get("export", {})
        
        # 兼容缺失或不完整的 email 配置
        if not isinstance(email_data, dict):
            email_data = {}
        email_defaults = {
            "address": email_data.get("address", ""),
            "password": email_data.get("password", ""),
        }
        # 其余可选项由 EmailConfig 的默认值提供
        safe_email = {**email_data, **email_defaults}
        
        return cls(
            email=EmailConfig(**safe_email),
            registration=RegistrationConfig(**reg_data),
            export=ExportConfig(**export_data)
        )
    
    def validate(self) -> List[str]:
        """
        验证配置完整性，返回错误列表
        
        注意：允许邮箱和密码为空，用户可以在GUI中填写
        """
        errors = []
        
        # 邮箱配置验证（允许空值，只在有值时验证格式）
        if self.email.address and "@" not in self.email.address:
            errors.append("邮箱地址格式无效")
        # 密码允许为空，用户在GUI中填写
        
        # 注册配置验证
        if not 1 <= self.registration.default_count <= 100:
            errors.append("注册数量必须在1-100之间")
        if self.registration.interval_seconds < 0:
            errors.append("间隔时间不能为负数")
        
        return errors


@dataclass
class TaskStatistics:
    """任务统计信息"""
    total: int = 0
    completed: int = 0
    success: int = 0
    failed: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.completed == 0:
            return 0.0
        return (self.success / self.completed) * 100
    
    @property
    def progress_percentage(self) -> float:
        """进度百分比"""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100


@dataclass
class RegistrationTask:
    """注册任务实体"""
    
    # 任务标识
    task_id: str                        # 格式: YYYYMMDD_HHMMSS
    
    # 任务状态
    status: TaskStatus = "not_started"
    
    # 账号列表
    accounts: List[Account] = field(default_factory=list)
    
    # 统计信息
    statistics: TaskStatistics = field(default_factory=TaskStatistics)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 断点续传支持
    last_processed_id: int = 0          # 最后处理的账号ID
    
    def to_dict(self) -> dict:
        """转换为字典（用于JSON持久化）"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "accounts": [acc.to_dict() for acc in self.accounts],
            "statistics": {
                "total": self.statistics.total,
                "completed": self.statistics.completed,
                "success": self.statistics.success,
                "failed": self.statistics.failed
            },
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_processed_id": self.last_processed_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RegistrationTask":
        """从字典恢复实例"""
        data = data.copy()
        data["accounts"] = [Account.from_dict(acc) for acc in data["accounts"]]
        data["statistics"] = TaskStatistics(**data["statistics"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])
        return cls(**data)
    
    def update_statistics(self):
        """根据账号列表更新统计信息"""
        self.statistics.total = len(self.accounts)
        self.statistics.completed = sum(
            1 for acc in self.accounts 
            if acc.status in ["success", "completed", "failed"]
        )
        self.statistics.success = sum(
            1 for acc in self.accounts 
            if acc.status in ["success", "completed"]  # 简单模式的completed也算成功
        )
        self.statistics.failed = sum(
            1 for acc in self.accounts 
            if acc.status == "failed"
        )
    
    def get_next_pending_account(self) -> Optional[Account]:
        """获取下一个待处理账号"""
        for account in self.accounts:
            if account.status == "pending":
                return account
        return None
    
    def is_resumable(self) -> bool:
        """判断任务是否可恢复"""
        return (
            self.status in ["in_progress", "paused"] and
            self.statistics.completed < self.statistics.total
        )


class DataManager:
    """数据管理器"""
    
    def __init__(self, email_generator_script: Optional[Path] = None, config: Optional["Configuration"] = None):
        """
        初始化数据管理器
        
        Args:
            email_generator_script: 外部邮箱生成器脚本路径（已废弃，使用内置生成器）
        """
        self.email_generator = email_generator_script  # 保留以兼容旧代码
        self.config = config
        
        # 数据目录改为程序当前目录下的data文件夹
        self.data_dir = Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 历史邮箱记录文件：放在程序根目录（和config.json同级）
        self.history_file = Path("registered_emails.txt")
        
        logger.info(f"DataManager initialized with data dir: {self.data_dir.absolute()}")
    
    def generate_accounts(self, count: int) -> List[Account]:
        """
        生成指定数量的账号
        
        Args:
            count: 账号数量（1-100）
            
        Returns:
            账号列表
            
        Raises:
            ValueError: count超出范围
            EmailGeneratorError: 邮箱生成器执行失败
        """
        # 验证数量
        if not 1 <= count <= 100:
            raise ValueError("账号数量必须在1-100之间")
        
        logger.info(f"开始生成{count}个账号...")
        
        # 调用外部邮箱生成器
        emails = self.call_email_generator(count)
        
        # 创建账号对象
        accounts = []
        for i, email_addr in enumerate(emails, start=1):
            first_name, last_name = self.extract_name_parts(email_addr)
            username = email_addr.split("@")[0]
            
            # 密码优先从配置读取，兼容老配置则回退到历史默认值
            resolved_password = "xqxatcdj1014"
            cfg = getattr(self, "config", None)
            try:
                if cfg is not None:
                    if isinstance(cfg, dict):
                        p = cfg.get("registration", {}).get("password")
                        if isinstance(p, str) and p:
                            resolved_password = p
                    else:
                        reg = getattr(cfg, "registration", None)
                        p = getattr(reg, "password", None) if reg is not None else None
                        if isinstance(p, str) and p:
                            resolved_password = p
            except Exception:
                pass

            account = Account(
                id=i,
                email=email_addr,
                username=username,
                password=resolved_password,
                first_name=first_name,
                last_name=last_name
            )
            accounts.append(account)
        
        logger.info(f"成功生成{len(accounts)}个账号")
        return accounts
    
    def call_email_generator(self, count: int) -> List[str]:
        """
        生成随机邮箱地址（内置实现，避免打包后subprocess问题）
        
        Args:
            count: 需要生成的邮箱数量
            
        Returns:
            邮箱地址列表
            
        Raises:
            EmailGeneratorError: 生成失败
        """
        try:
            if count < 1 or count > 1000:
                raise EmailGeneratorError(f"邮箱数量必须在1-1000之间，当前: {count}")
            
            emails = []
            domain = "yaoshangxian.top"
            cfg = getattr(self, "config", None)
            if cfg is not None:
                if isinstance(cfg, dict):
                    domain = cfg.get("registration", {}).get("domain", domain)
                else:
                    reg = getattr(cfg, "registration", None)
                    d = getattr(reg, "domain", None) if reg is not None else None
                    if isinstance(d, str) and d:
                        domain = d
            
            for _ in range(count):
                # 生成随机15位字符的本地部分（小写字母+数字）
                chars = string.ascii_lowercase + string.digits
                local_part = ''.join(random.choices(chars, k=15))
                
                # 固定域名（必须使用yaoshangxian.top）
                email = f"{local_part}@{domain}"
                
                emails.append(email)
            
            logger.info(f"成功生成{count}个随机邮箱地址")
            return emails
            
        except Exception as e:
            raise EmailGeneratorError(f"生成邮箱地址失败: {e}")
    
    def extract_name_parts(self, email: str) -> tuple[str, str]:
        """
        从邮箱地址提取姓名部分
        
        Args:
            email: 邮箱地址（如 abcdefgh@gmail.com）
            
        Returns:
            (first_name, last_name)
            - first_name: 随机生成的3位字母（首字母大写）
            - last_name: 随机生成的3位字母（首字母大写）
            
        Note:
            不再依赖邮箱地址中的字母，直接生成随机名字，更可靠
        """
        import random
        import string
        
        # 直接生成随机名字，不依赖邮箱内容
        first_name = ''.join(random.choices(string.ascii_lowercase, k=3))
        last_name = ''.join(random.choices(string.ascii_lowercase, k=3))
        
        # 首字母大写
        first_name = first_name.capitalize()
        last_name = last_name.capitalize()
        
        logger.debug(f"为邮箱 {email} 生成名字: {first_name} {last_name}")
        
        return (first_name, last_name)
    
    def create_task(self, accounts: List[Account]) -> RegistrationTask:
        """
        创建注册任务
        
        Args:
            accounts: 账号列表
            
        Returns:
            注册任务对象
        """
        task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        task = RegistrationTask(
            task_id=task_id,
            accounts=accounts
        )
        task.update_statistics()
        
        logger.info(f"创建注册任务: {task_id}, 账号数量: {len(accounts)}")
        return task
    
    def export_to_csv(self, accounts: List[Account], file_path: Path) -> None:
        """
        导出账号到CSV文件
        
        Args:
            accounts: 账号列表
            file_path: 输出文件路径
            
        Raises:
            IOError: 文件写入失败
        """
        import csv
        
        try:
            logger.info(f"导出{len(accounts)}个账号到CSV: {file_path}")
            
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                
                # 写入表头
                writer.writerow([
                    "ID", "Email", "Username", "Password", 
                    "FirstName", "LastName", "Status", 
                    "ErrorMessage", "CreatedAt", "CompletedAt"
                ])
                
                # 写入数据
                for account in accounts:
                    writer.writerow([
                        account.id,
                        account.email,
                        account.username,
                        account.password,
                        account.first_name,
                        account.last_name,
                        account.status,
                        account.error_message or "",
                        account.created_at.isoformat(),
                        account.completed_at.isoformat() if account.completed_at else ""
                    ])
            
            logger.info(f"CSV导出成功: {file_path}")
            
        except Exception as e:
            logger.error(f"CSV导出失败: {e}")
            raise IOError(f"无法写入CSV文件: {e}")
    
    def save_task(self, task: RegistrationTask) -> None:
        """
        保存任务到本地文件（原子性写入）
        
        Args:
            task: 任务对象
        """
        progress_file = self.data_dir / "tasks" / "progress.json"
        progress_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 写入临时文件
            temp_file = progress_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)
            
            # 原子性重命名
            temp_file.replace(progress_file)
            logger.debug(f"任务已保存: {progress_file}")
            
        except Exception as e:
            logger.error(f"保存任务失败: {e}")
            raise IOError(f"无法保存任务: {e}")
    
    def load_task(self) -> Optional[RegistrationTask]:
        """
        加载未完成的任务
        
        Returns:
            任务对象，如果没有未完成任务返回None
        """
        progress_file = self.data_dir / "tasks" / "progress.json"
        
        if not progress_file.exists():
            return None
        
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            task = RegistrationTask.from_dict(data)
            logger.info(f"加载任务: {task.task_id}, 状态: {task.status}")
            return task
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"任务文件损坏: {e}")
            # 归档损坏的文件
            self._archive_corrupted_file(progress_file)
            return None
        except Exception as e:
            logger.error(f"加载任务失败: {e}")
            return None
    
    def update_account_status(
        self,
        task: RegistrationTask,
        account_id: int,
        status: AccountStatus,
        error_message: Optional[str] = None
    ) -> None:
        """
        更新账号状态并自动保存
        
        Args:
            task: 任务对象
            account_id: 账号ID
            status: 新状态
            error_message: 错误消息（如果失败）
        """
        # 找到账号
        for account in task.accounts:
            if account.id == account_id:
                account.status = status
                if error_message:
                    account.error_message = error_message
                
                # 处理已完成的账号
                if status == "success":
                    # 注册成功
                    account.completed_at = datetime.now()
                elif status == "failed":
                    # 失败时只记录完成时间
                    account.completed_at = datetime.now()
                
                break
        
        # 更新统计
        task.update_statistics()
        task.last_processed_id = account_id
        
        # 自动保存
        self.save_task(task)
    
    def clear_task_data(self) -> None:
        """
        清除任务数据
        
        用于用户选择"清除"选项时
        """
        progress_file = self.data_dir / "tasks" / "progress.json"
        
        if progress_file.exists():
            try:
                # 归档而不是删除
                self._archive_corrupted_file(progress_file)
                logger.info("任务数据已清除")
            except Exception as e:
                logger.error(f"清除任务数据失败: {e}")
    
    def _archive_corrupted_file(self, file_path: Path) -> None:
        """归档损坏的文件"""
        archive_dir = self.data_dir / "tasks" / "archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = archive_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
        
        try:
            file_path.rename(archive_file)
            logger.info(f"文件已归档: {archive_file}")
        except Exception as e:
            logger.error(f"归档文件失败: {e}")
    
    def _load_history_emails(self) -> set:
        """
        加载历史已注册成功的邮箱地址
        
        Returns:
            历史邮箱地址集合
        """
        if not self.history_file.exists():
            return set()
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                emails = {line.strip() for line in f if line.strip()}
            return emails
        except Exception as e:
            logger.warning(f"加载历史邮箱失败: {e}")
            return set()
    
    def save_success_email(self, email: str) -> None:
        """
        保存注册成功的邮箱地址到历史记录
        
        Args:
            email: 成功注册的邮箱地址
        """
        try:
            # 追加写入（避免覆盖）
            with open(self.history_file, 'a', encoding='utf-8') as f:
                f.write(f"{email}\n")
            logger.debug(f"已记录成功邮箱: {email}")
        except Exception as e:
            logger.warning(f"保存历史邮箱失败: {e}")
