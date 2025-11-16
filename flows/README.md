# flows 目录

本目录存放各网站的 Flow 配置（TOML）。

- Flow 规范请查看 `docs/FLOW_SPEC.md`
- 示例：`flows/windsurf_register.toml`

## 校验方式（TOML + 变量占位符）

提供脚本 `scripts/validate_flow.py` 用于快速校验：

```bash
python scripts/validate_flow.py --flow flows/windsurf_register.toml --config config.json \
  --account '{"email":"test@example.com","password":"P@ssw0rd","first_name":"A","last_name":"B"}'
```

预期：
- 成功解析 TOML
- 检查 `flow/steps/selectors` 结构合法
- 检查 `{config.*}/{account.*}/{env.*}/{flow.*}` 变量可解析
- 输出步骤与选择器统计

## 配置指南（TOML 结构）

```toml
[flow]
name = "Your Flow Name"
start_url = "https://example.com/register"
timeout_ms = 10000

[selectors.email]
by = "id"            # id | css | xpath
value = "email"

[selectors.submit]
by = "css"
value = "button[type=submit]"

[[steps]]
action = "navigate"  # 访问 start_url

[[steps]]
action = "type"
target = "email"
value = "{account.email}"

[[steps]]
action = "pause_for_manual"
message = "请完成人机验证后点击 GUI 的 '手动继续'"
```

### 支持的动作（actions）
- `navigate`：导航到 URL（默认 `flow.start_url`）
- `wait`：等待元素（`state` 支持 `present|visible|clickable`）
- `type`：输入文本（`value` 可用变量）
- `click`：点击元素
- `sleep`：休眠毫秒
- `expect`：断言状态（失败抛错）
- `pause_for_manual`：等待用户手动继续（GUI）

### 变量系统（variables）
- `{config.*}`：来自 `config.json`（如 `{config.registration.domain}`）
- `{account.*}`：当前账号上下文（email/password/first_name/last_name）
- `{env.*}`：环境变量（如 `{env.HOME}`），未设置会报错
- `{flow.*}`：来自 `[flow]` 与 `[variables]`（如 `{flow.start_url}`）

### 最佳实践
- 将稳定元素抽到 `[selectors]`，避免硬编码在步骤里
- 输入文本前先 `wait` 相应元素为 `visible`/`clickable`
- 人机验证前可适当 `sleep`，降低触发频率

## 打包后的文件放置
- Flow 文件可放在：
  - `EXE 同级根目录`：如 `dist/YourApp/windsurf_register.toml`
  - `flows/ 子目录`：如 `dist/YourApp/flows/windsurf_register.toml`
- `config.json` 与 EXE 同级（首次运行自动生成模板）

## 常见问题
- 找不到 Flow：检查路径是否放在 EXE 同级或 `flows/` 子目录
- 变量解析失败：确认 `config.json`/环境变量是否存在对应键
- 验证码通过率低：关闭 headless，使用临时目录（默认已启用），减少打开频率
