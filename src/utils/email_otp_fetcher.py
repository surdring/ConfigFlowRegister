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
    subject_keywords: list[str]
    time_window_seconds: int


def extract_otp(text: str) -> Optional[str]:
    """从文本中提取 6 位验证码。"""
    if not text:
        return None
    m = re.search(r"(\d{6})", text)
    if not m:
        return None
    return m.group(1)


def extract_otp_from_subject(subject: str) -> Optional[str]:
    """从邮件主题中提取 6 位验证码（兼容旧接口）。"""
    return extract_otp(subject)


def get_email_body(msg) -> str:
    """从邮件消息中提取正文文本。"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body += payload.decode(charset, errors="ignore")
                except Exception:
                    pass
            elif content_type == "text/html" and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        # 简单去除 HTML 标签
                        html = payload.decode(charset, errors="ignore")
                        text = re.sub(r"<[^>]+>", " ", html)
                        text = re.sub(r"\s+", " ", text).strip()
                        body += " " + text
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="ignore")
        except Exception:
            pass
    return body


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
    poll_interval = 1.0

    try:
        logger.info("[OTP] 为账号 %s 启动验证码监听", account_email)
        with imaplib.IMAP4_SSL(email_cfg.imap_server, email_cfg.imap_port) as imap:
            imap.login(email_cfg.address, email_cfg.password)
            imap.select("INBOX")

            while time.time() < end_ts:
                if stop_flag and stop_flag():
                    logger.info("[OTP] 检测到停止标志，结束账号 %s 的验证码监听", account_email)
                    return

                # 只搜索未读邮件
                typ, data = imap.search(None, "UNSEEN")
                if typ != "OK":
                    time.sleep(poll_interval)
                    continue

                ids = data[0].split()
                if not ids:
                    time.sleep(poll_interval)
                    continue

                # 按ID降序（最新的优先），每轮最多检查5封最新邮件
                ids_to_check = list(reversed(ids))[:5]

                for msg_id in ids_to_check:  # 优先检查最新邮件
                    try:
                        typ, msg_data = imap.fetch(msg_id, "(RFC822)")
                        if typ != "OK" or not msg_data or not msg_data[0]:
                            continue
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = msg.get("Subject", "")
                        to_header = msg.get("To", "")
                        from_header = msg.get("From", "")

                        logger.debug("[OTP] 检查邮件: id=%s, subject=%r, to=%r, from=%r", msg_id, subject, to_header, from_header)

                        # 检查是否是发给当前账号的邮件（考虑代发情况）
                        recipient_match = account_email in to_header

                        # 如果To头不匹配，尝试从其他头或正文中找原始收件人
                        if not recipient_match:
                            # 检查 Reply-To 或其他可能包含原始收件人的头
                            reply_to = msg.get("Reply-To", "")
                            x_original_to = msg.get("X-Original-To", "")
                            delivered_to = msg.get("Delivered-To", "")
                            envelope_to = msg.get("Envelope-To", "")

                            for header in [reply_to, x_original_to, delivered_to, envelope_to]:
                                if account_email in header:
                                    recipient_match = True
                                    logger.debug("[OTP] 在其他头中找到收件人匹配: %s", header)
                                    break

                        # 如果头信息都不匹配，尝试从正文找（验证码邮件正文通常包含账号）
                        if not recipient_match:
                            body_preview = get_email_body(msg)[:1000]
                            # 常见模式：邮件正文会提到注册邮箱
                            if account_email in body_preview:
                                recipient_match = True
                                logger.debug("[OTP] 在正文中找到收件人匹配")

                        if not recipient_match:
                            # 不匹配则标记为已读，避免未读邮件堆积
                            try:
                                imap.store(msg_id, '+FLAGS', '\\Seen')
                            except Exception:
                                pass
                            logger.debug("[OTP] 跳过邮件: 收件人不匹配 (期望: %s, To头: %s)", account_email, to_header)
                            continue

                        # 账号匹配成功，直接尝试提取验证码（跳过主题关键词过滤）
                        # 先从主题提取验证码
                        code = extract_otp(subject)
                        source = "subject"

                        # 主题中没有，则从正文提取
                        if not code:
                            body = get_email_body(msg)
                            code = extract_otp(body)
                            source = "body"
                            logger.debug("[OTP] 正文内容: %r", body[:500] if body else "(empty)")

                        if not code:
                            logger.debug("[OTP] 跳过邮件: 未找到 6 位验证码 (subject=%r)", subject)
                            continue

                        logger.info(
                            "[OTP] 账号 %s 收到验证码 %s (from=%s, subject=%r)",
                            account_email,
                            code,
                            source,
                            subject,
                        )
                        # 标记为已读，避免下次重复检查
                        try:
                            imap.store(msg_id, '+FLAGS', '\\Seen')
                        except Exception:
                            pass
                        on_code(code)
                        return
                    except Exception as e:
                        # 单封邮件解析失败不影响整体轮询
                        logger.warning("[OTP] 解析邮件 %s 失败: %s", msg_id, e)
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
