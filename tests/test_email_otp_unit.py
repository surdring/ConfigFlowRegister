import pytest

from src.utils.email_otp_fetcher import (
    extract_otp_from_subject,
    build_and_fetch_from_dict,
    _build_mailbox_config,
    OtpMailboxConfig,
    fetch_otp_for_account,
)
from src import utils as _utils_pkg  # 只是为了 monkeypatch 方便


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("604688 - Verify your Email with Windsurf", "604688"),
        ("您的验证码是 123456 ，请在 5 分钟内使用", "123456"),
        ("No digits here", None),
        # 当前实现只匹配连续 6 位数字，因此该例应返回 None
        ("Code: 12 3456", None),
    ],
)
def test_extract_otp_from_subject(subject, expected):
    assert extract_otp_from_subject(subject) == expected


def test_build_and_fetch_from_dict_incomplete_config_does_not_call_network(monkeypatch):
    """
    当 email 配置不完整（缺少 address/password）时，
    build_and_fetch_from_dict 应该直接返回，不调用 fetch_otp_for_account。
    """
    called = {"count": 0}

    # 注意：这里从 email_otp_fetcher 模块本身 monkeypatch fetch_otp_for_account
    import src.utils.email_otp_fetcher as email_otp_fetcher

    def _fake_fetch(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr(email_otp_fetcher, "fetch_otp_for_account", _fake_fetch)

    cfg = {
        # 故意缺少 address/password
        "imap_server": "imap.qq.com",
        "imap_port": 993,
    }

    def _on_code(_code: str):
        called["count"] += 100  # 如果被调用就明显出错

    build_and_fetch_from_dict(cfg, "someone@example.com", _on_code)

    # 不应该触发网络层
    assert called["count"] == 0


def test_build_mailbox_config_with_plain_values():
    """完整的明文配置应生成有效的 OtpMailboxConfig，并填充默认字段。"""
    cfg = {
        "address": "user@example.com",
        "password": "app-pass",
        # 其他字段留空，使用默认值
    }
    mailbox_cfg = _build_mailbox_config(cfg)
    assert isinstance(mailbox_cfg, OtpMailboxConfig)
    assert mailbox_cfg.address == "user@example.com"
    assert mailbox_cfg.password == "app-pass"
    # 默认 IMAP 配置
    assert mailbox_cfg.imap_server == "imap.qq.com"
    assert mailbox_cfg.imap_port == 993


def test_build_mailbox_config_with_encrypted_values(monkeypatch):
    """当 address/password 为 enc: 前缀时，应通过 decrypt_email_secret 解密。"""
    import src.utils.email_otp_fetcher as email_otp_fetcher

    called = {"addr": None, "pwd": None}

    def _fake_decrypt(val: str) -> str:
        # 直接标记解密过的值，便于断言
        if val == "enc:addr":
            called["addr"] = val
            return "decrypted-addr"
        if val == "enc:pwd":
            called["pwd"] = val
            return "decrypted-pwd"
        return val

    monkeypatch.setattr(email_otp_fetcher, "decrypt_email_secret", _fake_decrypt)

    cfg = {
        "address": "enc:addr",
        "password": "enc:pwd",
    }

    mailbox_cfg = _build_mailbox_config(cfg)
    assert isinstance(mailbox_cfg, OtpMailboxConfig)
    assert mailbox_cfg.address == "decrypted-addr"
    assert mailbox_cfg.password == "decrypted-pwd"
    # 确保 fake 解密函数被调用
    assert called["addr"] == "enc:addr"
    assert called["pwd"] == "enc:pwd"


def test_fetch_otp_for_account_empty_email_noop():
    """当 account_email 为空时，fetch_otp_for_account 应立即返回，不触发回调。"""
    mailbox_cfg = OtpMailboxConfig(
        address="user@example.com",
        password="app-pass",
        imap_server="imap.qq.com",
        imap_port=993,
        sender_pattern="",
        subject_keywords=[],
        time_window_seconds=10,
    )

    called = {"code": None}

    def _on_code(code: str):
        called["code"] = code

    # account_email 为空，函数应直接返回
    fetch_otp_for_account(mailbox_cfg, "", _on_code)
    assert called["code"] is None