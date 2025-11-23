import json
import os
from pathlib import Path

import pytest

from src.utils.email_otp_fetcher import build_and_fetch_from_dict


@pytest.mark.integration
def test_fetch_otp_for_oc1ddmeebp8s57x():
    """
    集成测试：通过真实 OTP 邮箱为账号 oc1ddmeebp8s57x@yaoshangxian.top 拉取验证码。

    运行前需要：
    - config.json 中 email 段配置好 enc: 加密后的 address/password。
    - 环境变量 CONFIGFLOW_EMAIL_SECRET_KEY 已设置为对应的密钥。
    - 目标 OTP 邮箱里在 time_window_seconds 内存在一封
      To 包含该账号，且标题类似 `NNNNNN - Verify your Email with Windsurf` 的邮件。
    """

    print("[integration] ===== OTP 集成测试开始 =====")

    # 通过开关环境变量控制是否运行集成测试，避免 CI 或普通环境失败
    flag = os.environ.get("OTP_INTEGRATION_ENABLED")
    print(f"[integration] OTP_INTEGRATION_ENABLED={flag!r}")
    if flag != "1":
        pytest.skip("设置 OTP_INTEGRATION_ENABLED=1 后再运行此集成测试")

    secret = os.environ.get("CONFIGFLOW_EMAIL_SECRET_KEY")
    print(f"[integration] CONFIGFLOW_EMAIL_SECRET_KEY 已设置: {bool(secret)}")
    if not secret:
        pytest.skip("未设置 CONFIGFLOW_EMAIL_SECRET_KEY，跳过集成测试")

    cfg_path = Path("config.json")
    print(f"[integration] 使用配置文件: {cfg_path.resolve()}")
    if not cfg_path.exists():
        pytest.skip("config.json 不存在，请先从模板生成并配置 OTP 邮箱")

    with cfg_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    email_cfg = config.get("email") or {}
    if not (email_cfg.get("address") and email_cfg.get("password")):
        pytest.skip("email 段未配置 address/password，跳过集成测试")

    # 打印邮箱配置概要（不输出敏感明文）
    print("[integration] OTP 邮箱配置概要:")
    print(f"  - imap_server: {email_cfg.get('imap_server')}")
    print(f"  - imap_port: {email_cfg.get('imap_port')}")
    print(f"  - subject_keywords: {email_cfg.get('subject_keywords')}")
    print(f"  - time_window_seconds: {email_cfg.get('time_window_seconds')}")

    target_account = "mz66c24cwegm0yd@yaoshangxian.top"
    print(f"[integration] 目标账号: {target_account}")
    received = {}

    def _on_code(code: str):
        # 收到验证码时记录下来
        received["code"] = code

    # 调用我们实现的 IMAP 拉取逻辑
    print("[integration] 调用 build_and_fetch_from_dict 开始监听 OTP 邮箱...")
    build_and_fetch_from_dict(email_cfg, target_account, _on_code)
    print("[integration] 监听结束，准备断言是否收到验证码")

    # 断言：在 time_window_seconds 内应该拿到一个 6 位数字验证码
    code = received.get("code")
    assert code is not None, "在时间窗口内未为指定账号收到验证码邮件，请确认邮件是否已发送到 OTP 邮箱"
    assert len(code) == 6 and code.isdigit(), f"验证码格式不正确: {code}"

    # 打印出来，方便你在测试输出中直接看到验证码
    print(f"[integration] OTP for account {target_account} is: {code}")