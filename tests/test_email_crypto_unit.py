import os

import pytest

from src.utils.email_crypto import (
    encrypt_email_secret,
    decrypt_email_secret,
    EmailCryptoError,
)


def test_encrypt_decrypt_roundtrip(monkeypatch):
    """加密后再解密应还原原文，且带有 enc: 前缀。"""
    monkeypatch.setenv("CONFIGFLOW_EMAIL_SECRET_KEY", "test-secret-key")

    plaintext = "user@example.com"
    token = encrypt_email_secret(plaintext)

    assert token.startswith("enc:"), "加密结果应包含 enc: 前缀"

    recovered = decrypt_email_secret(token)
    assert recovered == plaintext


def test_encrypt_empty_string_returns_empty(monkeypatch):
    """空字符串不参与加密，直接返回空字符串。"""
    monkeypatch.setenv("CONFIGFLOW_EMAIL_SECRET_KEY", "test-secret-key")
    assert encrypt_email_secret("") == ""


def test_decrypt_plaintext_without_prefix_no_key(monkeypatch):
    """非 enc: 前缀的值在没有密钥时也应原样返回（兼容明文配置）。"""
    monkeypatch.delenv("CONFIGFLOW_EMAIL_SECRET_KEY", raising=False)
    assert decrypt_email_secret("plain@example.com") == "plain@example.com"


def test_encrypt_requires_secret_key(monkeypatch):
    """没有环境变量密钥时，加密应抛出 EmailCryptoError。"""
    monkeypatch.delenv("CONFIGFLOW_EMAIL_SECRET_KEY", raising=False)
    with pytest.raises(EmailCryptoError):
        encrypt_email_secret("need-key")


def test_decrypt_invalid_token_raises(monkeypatch):
    """解密非法 enc: 值时应抛出 EmailCryptoError。"""
    monkeypatch.setenv("CONFIGFLOW_EMAIL_SECRET_KEY", "test-secret-key")
    with pytest.raises(EmailCryptoError):
        decrypt_email_secret("enc:!!!!not-base64!!!!")


def test_decrypt_empty_and_none(monkeypatch):
    """空字符串或 None 解密结果应为空字符串。"""
    monkeypatch.setenv("CONFIGFLOW_EMAIL_SECRET_KEY", "test-secret-key")
    assert decrypt_email_secret("") == ""
    assert decrypt_email_secret(None) == ""  # type: ignore[arg-type]
