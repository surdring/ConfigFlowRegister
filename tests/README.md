# tests 目录说明

本目录包含本项目的单元测试和集成测试。

目前与“邮箱验证码（OTP）”相关的测试文件如下：

## 1. `test_email_crypto_unit.py`（单元测试）

**测试目标：**
- 覆盖 `src/utils/email_crypto.py` 中的加解密逻辑：
  - `encrypt_email_secret`
  - `decrypt_email_secret`
  - `EmailCryptoError`

**主要用例：**
- 加密 + 解密的闭环是否正确（`enc:...` → 还原成原始明文）。
- 空字符串不参与加密，直接返回空字符串。
- 在没有环境变量 `CONFIGFLOW_EMAIL_SECRET_KEY` 时，加密必须抛出 `EmailCryptoError`。
- 非 `enc:` 前缀的值在没有密钥时应原样返回（兼容明文配置）。
- 对非法 `enc:` 值解密时应抛出 `EmailCryptoError`。

**运行方式：**

```bash
python -m pytest tests/test_email_crypto_unit.py -vv
```

---

## 2. `test_email_otp_unit.py`（单元测试）

**测试目标：**
- 覆盖 `src/utils/email_otp_fetcher.py` 中的核心纯逻辑：
  - `extract_otp_from_subject`：从邮件标题中提取 6 位验证码。
  - `_build_mailbox_config`：从配置字典构造 `OtpMailboxConfig`，包括明文和 `enc:` 加密场景。
  - `build_and_fetch_from_dict` 在配置不完整时不应触发 IMAP 网络调用。
  - `fetch_otp_for_account` 在 `account_email` 为空时应立即返回。

**运行方式：**

```bash
python -m pytest tests/test_email_otp_unit.py -vv
```

---

## 3. `test_email_otp_integration.py`（集成测试）

**测试目标：**
- 通过真实 IMAP 连接，从配置好的 OTP 邮箱中为账号
  `oc1ddmeebp8s57x@yaoshangxian.top` 拉取验证码。
- 验证 `build_and_fetch_from_dict` + `fetch_otp_for_account` 在真实邮箱环境中的行为，包括：
  - 轮询未读邮件和最新 10 封邮件；
  - 根据收件人和标题关键字过滤；
  - 成功提取 6 位验证码并通过回调返回。

**前置条件：**

1. 项目根目录存在 `config.json`，且 `email` 段已配置：
   - `address` / `password` 为 `enc:` 加密后的邮箱账号和授权码；
   - `imap_server` / `imap_port` 正确；
   - `subject_keywords` 与标题规律一致（例如 `["verify", "windsurf"]`）。

2. 环境变量已设置（以 Windows PowerShell 为例）：

   ```powershell
   $env:CONFIGFLOW_EMAIL_SECRET_KEY="windsurf"      # 与 enc: 加密时使用的密钥一致
   $env:OTP_INTEGRATION_ENABLED="1"               # 打开集成测试开关
   ```

3. OTP 邮箱中，在 `email.time_window_seconds` 规定的时间窗口内，存在一封：
   - `To` 包含 `oc1ddmeebp8s57x@yaoshangxian.top`；
   - 标题类似 `604688 - Verify your Email with Windsurf` 的验证码邮件。

**运行方式：**

建议使用 `-vv -s` 以便查看详细日志：

```bash
python -m pytest tests/test_email_otp_integration.py -vv -s
```

典型输出步骤包括：
- `[integration] ===== OTP 集成测试开始 =====`
- 打印环境变量、使用的 `config.json` 路径和 OTP 邮箱配置概要；
- `[integration] 调用 build_and_fetch_from_dict 开始监听 OTP 邮箱...`
- `[integration] 监听结束，准备断言是否收到验证码`
- 成功时会打印：
  `"[integration] OTP for account oc1ddmeebp8s57x@yaoshangxian.top is: 123456"`

> 注意：项目当前启用了全局覆盖率阈值（如 `--cov-fail-under=80`），
> 仅运行部分测试时可能会因为“总覆盖率不足 80%”导致 pytest 最终返回非零退出码，
> 但不影响你从输出中判断集成测试本身是否成功拉取到验证码。
