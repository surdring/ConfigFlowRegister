"""邮箱凭据加解密工具

使用环境变量提供的密钥对邮箱地址/授权码做对称加解密，避免在配置文件中以明文形式保存。

算法说明（简单实现，依赖标准库）：
- 使用 SHA-256 对环境变量中的密钥进行哈希，得到 32 字节 key。
- 将明文按字节与 key 做循环异或，得到密文字节。
- 使用 URL-safe Base64 对密文字节进行编码，并添加前缀 "enc:" 作为标识。
- 解密时，若不包含 "enc:" 前缀则视为明文（用于兼容旧配置）。

注意：
- 该实现主要用于避免明文直观暴露，安全强度受限于环境变量管理和简单异或方案，
  对于高安全场景应替换为专业密钥管理/加密方案。
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

_SECRET_ENV_VAR = "CONFIGFLOW_EMAIL_SECRET_KEY"
_PREFIX = "enc:"


class EmailCryptoError(RuntimeError):
    """邮箱凭据加解密相关错误。"""


def _derive_key() -> bytes:
    secret = os.environ.get(_SECRET_ENV_VAR)
    if not secret:
        raise EmailCryptoError(
            f"未找到环境变量 {_SECRET_ENV_VAR}，无法解密邮箱凭据；"
            "请为 OTP 邮箱配置加密密钥。"
        )
    # 使用 SHA-256 将任意长度密钥归一化为 32 字节
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_email_secret(plaintext: str) -> str:
    """加密邮箱敏感字段（地址或授权码）。

    空字符串原样返回；否则返回带前缀的 Base64 文本，形如 "enc:..."。
    """
    if not plaintext:
        return plaintext
    key = _derive_key()
    data = plaintext.encode("utf-8")
    enc_bytes = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    token = base64.urlsafe_b64encode(enc_bytes).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_email_secret(value: Optional[str]) -> str:
    """解密邮箱敏感字段。

    - 若为空或 None，返回空字符串；
    - 若不以 "enc:" 开头，则视为明文直接返回（兼容旧配置）；
    - 若以 "enc:" 开头，则尝试使用环境变量中的密钥解密。
    """
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        # 兼容旧配置：直接视为明文使用
        return value

    token = value[len(_PREFIX) :]
    key = _derive_key()
    try:
        enc_bytes = base64.urlsafe_b64decode(token.encode("ascii"))
    except Exception as exc:  # pragma: no cover - 极端错误
        raise EmailCryptoError(f"邮箱凭据解码失败: {exc}") from exc

    data = bytes(b ^ key[i % len(key)] for i, b in enumerate(enc_bytes))
    try:
        return data.decode("utf-8")
    except Exception as exc:  # pragma: no cover
        raise EmailCryptoError(f"邮箱凭据解密失败: {exc}") from exc
