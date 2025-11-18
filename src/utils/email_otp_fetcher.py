from __future__ import annotations

import imaplib
import email
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from .logger import default_logger as logger

try:
    # 运行时解密邮箱账号与授权码
    from .email_crypto import decrypt_email_secret
except Exception:  # pragma: no cover - 回退路径
    try:
        from src.utils.email_crypto import decrypt_email_secret  # type: ignore
    except Exception:
        decrypt_email_secret = lambda v: v  # type: ignore


@dataclass
class OtpMailboxConfig:
    address: str
    password: str
    imap_server: str
    imap_port: int
    sender_pattern: str
    subject_keywords: list[str]
    time_window_seconds: int


def extract_otp_from_subject(subject: str) -> Optional[str]:
    """从邮件主题中提取 6 位验证码。"""
    if not subject:
        return None
    m = re.search(r"(\d{6})", subject)
    if not m:
        return None
    return m.group(1)


def _build_mailbox_config(raw_cfg: dict) -> Optional[OtpMailboxConfig]:
    if not isinstance(raw_cfg, dict):
        return None

    raw_address = raw_cfg.get("address") or ""
    raw_password = raw_cfg.get("password") or ""
    if not raw_address or not raw_password:
        return None

    # 支持 enc: 前缀加密配置，运行时解密后再使用
    try:
        address = decrypt_email_secret(str(raw_address))
    except Exception:
        address = str(raw_address)
    try:
        password = decrypt_email_secret(str(raw_password))
    except Exception:
        password = str(raw_password)

    if not address or not password:
        return None

    return OtpMailboxConfig(
        address=address,
        password=password,
        imap_server=raw_cfg.get("imap_server") or "imap.qq.com",
        imap_port=int(raw_cfg.get("imap_port") or 993),
        sender_pattern=raw_cfg.get("sender_pattern") or "",
        subject_keywords=list(raw_cfg.get("subject_keywords") or []),
        time_window_seconds=int(raw_cfg.get("time_window_seconds") or 300),
    )


def fetch_otp_for_account(
    email_cfg: OtpMailboxConfig,
    account_email: str,
    on_code: Callable[[str], None],
    stop_flag: Optional[Callable[[], bool]] = None,
) -> None:
    """在独立线程中轮询 OTP 邮箱，为指定账号拉取验证码。

    - 使用 email_cfg 中的 IMAP 配置连接到邮箱。
    - 在 time_window_seconds 时间窗口内轮询 INBOX，查找 To 中包含 account_email 的邮件，
      并从主题中提取 6 位验证码。
    - 一旦获取到验证码，调用 on_code(code) 并返回。
    - 若 stop_flag 存在且返回 True，则提前终止轮询。
    """
    if not account_email:
        return

    end_ts = time.time() + max(5, email_cfg.time_window_seconds)
    poll_interval = 5.0

    try:
        logger.info("[OTP] 为账号 %s 启动验证码监听", account_email)
        with imaplib.IMAP4_SSL(email_cfg.imap_server, email_cfg.imap_port) as imap:
            imap.login(email_cfg.address, email_cfg.password)
            imap.select("INBOX")

            while time.time() < end_ts:
                if stop_flag and stop_flag():
                    logger.info("[OTP] 检测到停止标志，结束账号 %s 的验证码监听", account_email)
                    return

                # 优先在未读邮件中查找验证码；如果没有未读邮件，则回退到全部邮件。
                typ, data = imap.search(None, "UNSEEN")
                if typ != "OK" or not data or not data[0]:
                    typ, data = imap.search(None, "ALL")
                    if typ != "OK":
                        time.sleep(poll_interval)
                        continue

                ids = data[0].split()
                if not ids:
                    time.sleep(poll_interval)
                    continue

                # 只检查最新的 10 封邮件，减少无效遍历
                ids_to_check = list(reversed(ids[-10:]))

                for msg_id in ids_to_check:  # 优先检查最新邮件
                    try:
                        typ, msg_data = imap.fetch(msg_id, "(RFC822)")
                        if typ != "OK" or not msg_data or not msg_data[0]:
                            continue
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = msg.get("Subject", "")
                        to_header = msg.get("To", "")

                        if account_email not in to_header:
                            continue

                        # 关键字匹配（若配置了 subject_keywords，则要求全部命中）
                        subj_lower = subject.lower()
                        if email_cfg.subject_keywords:
                            if not all(k.lower() in subj_lower for k in email_cfg.subject_keywords):
                                continue

                        code = extract_otp_from_subject(subject)
                        if not code:
                            continue

                        logger.info(
                            "[OTP] 账号 %s 收到验证码 %s (subject=%r)",
                            account_email,
                            code,
                            subject,
                        )
                        on_code(code)
                        return
                    except Exception:
                        # 单封邮件解析失败不影响整体轮询
                        continue

                time.sleep(poll_interval)

        logger.info("[OTP] 在窗口内未为账号 %s 找到验证码邮件", account_email)
    except Exception as e:  # pragma: no cover - 网络/环境依赖
        logger.warning("[OTP] 为账号 %s 监听验证码失败: %s", account_email, e)


def build_and_fetch_from_dict(
    email_cfg_dict: dict,
    account_email: str,
    on_code: Callable[[str], None],
    stop_flag: Optional[Callable[[], bool]] = None,
) -> None:
    """从原始配置字典构造 OtpMailboxConfig 并启动拉取逻辑。"""
    cfg = _build_mailbox_config(email_cfg_dict)
    if not cfg:
        logger.info("[OTP] 邮箱配置不完整，跳过验证码监听")
        return
    fetch_otp_for_account(cfg, account_email, on_code, stop_flag=stop_flag)
