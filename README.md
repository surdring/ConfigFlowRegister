# ConfigFlowRegister

配置驱动的通用网站批量注册引擎（Python + Selenium + undetected-chromedriver + Tkinter GUI）。

## 特性
- **配置驱动**：使用 TOML 定义流程（URL、选择器、步骤）。
- **半自动模式**：`pause_for_manual` + GUI “手动继续”。
- **反检测增强**：临时用户目录、隐藏 `navigator.webdriver`、伪装指纹。
- **统一日志**：控制台 + 文件 + GUI 面板。

## 目录结构
- `flows/`：Flow TOML（示例：`windsurf_register.toml`）
- `src/engine/`：引擎（FlowLoader/FlowRunner/VariableResolver/actions）
- `src/browser/`：浏览器提供者（反检测）
- `src/gui/`：Tkinter GUI（与引擎对接）
- `src/utils/`：配置、日志、异常、路径工具

## 运行方式

### 1) 旧入口（向后兼容）
保留 `src/main.py` 作为启动入口（内部使用新引擎/GUI）。

```bash
python src/main.py
```

### 2) 配置驱动（通过 GUI 使用新引擎）
1. 在 `config.json` 中设置默认 Flow（已提供模板 `config.json.template`）：
```json
{
  "flow": { "file": "flows/windsurf_register.toml" }
}
```
2. 运行 GUI（旧入口不变）。
3. 在 GUI 中开始任务，流程会按 TOML 执行，遇到 `pause_for_manual` 时可点击“✓ 手动继续”。

### 3) Flow 校验（可选）
```bash
python scripts/validate_flow.py --flow flows/windsurf_register.toml \
  --account '{"email":"test@example.com","password":"P@ssw0rd","first_name":"A","last_name":"B"}'
```

## Flow 示例（节选）
```toml
[flow]
name = "WindSurf Register (MVP)"
start_url = "https://windsurf.com/account/register"
timeout_ms = 10000

[selectors.email]
by = "id"
value = "email"

[[steps]]
action = "navigate"

[[steps]]
action = "type"
target = "email"
value = "{account.email}"

[[steps]]
action = "pause_for_manual"
message = "请完成人机验证后点击 GUI 的 '手动继续'"
```

## 反检测确认
启动后在日志中确认：
- `navigator.webdriver 已隐藏`
- `✓ 增强反检测脚本完成`

## 迁移指南
请阅读 `docs/MIGRATION.md`：
- 如何将硬编码流程迁移到 TOML
- 变量系统与选择器/步骤对照
- 运行与校验方式

## CLI 使用（跨平台）

- **查看帮助**
```bash
python -m src.cli --help
```

- **按配置默认 Flow 运行**
```bash
python -m src.cli
```

- **指定 Flow、数量与间隔**
```bash
python -m src.cli --flow flows/windsurf_register.toml --count 3 --interval 2
```

- **环境变量占位符**（`{env.*}` 由引擎自动解析）
  - Windows PowerShell：
    ```powershell
    $env:REG_EMAIL="test@example.com"
    python -m src.cli --flow flows/windsurf_register.toml
    ```
  - Linux/macOS：
    ```bash
    export REG_EMAIL="test@example.com"
    python -m src.cli --flow flows/windsurf_register.toml
    ```

- **退出码约定**
  - 成功：0
  - 配置/文件错误：1
  - 执行失败：2
  - 用户中断（Ctrl+C）：130

- **注意**
  - 无头模式（headless）下验证码通过率很低，建议关闭 headless。
  - Linux 无桌面时可用 `xvfb-run` 提供虚拟显示，但仍建议有头运行以提高通过率。

## 邮箱验证码与加密配置

- **OTP 邮箱角色**
  - `config.json` 中的 `email` 段配置的是**收取验证码的专用邮箱**（例如 QQ 邮箱），
    而不是注册用的 `@yaoshangxian.top` 账号。
  - 程序会在注册开始时，通过 IMAP 轮询该 OTP 邮箱，按邮件主题和收件人匹配当前注册账号的验证码邮件。

- **加密存储邮箱账号和授权码**
  - 模板 `config.json.template` 中的示例：
    ```json
    "email": {
      "address": "enc:your_encrypted_email_here",
      "password": "enc:your_encrypted_app_password_here",
      ...
    }
    ```
  - 实际使用时：
    1. 在运行环境设置加密密钥（以 Windows PowerShell 为例）：
       ```powershell
       $env:CONFIGFLOW_EMAIL_SECRET_KEY="你的强密码"
       ```
       Linux/macOS：
       ```bash
       export CONFIGFLOW_EMAIL_SECRET_KEY="你的强密码"
       ```
    2. 使用一行命令直接生成加密后的邮箱地址和授权码：
       - Windows PowerShell：
         ```powershell
         python -c "from src.utils.email_crypto import encrypt_email_secret as enc; print(enc('your_email@qq.com'))"
         python -c "from src.utils.email_crypto import encrypt_email_secret as enc; print(enc('ofumbhmnvzkzcbaa'))"
         ```
       - Linux/macOS：
         ```bash
         python -c "from src.utils.email_crypto import encrypt_email_secret as enc; print(enc('your_email@qq.com'))"
         python -c "from src.utils.email_crypto import encrypt_email_secret as enc; print(enc('your_app_specific_password'))"
         ```
    3. 也可以在 Python 交互环境中调用：
       ```python
       from src.utils.email_crypto import encrypt_email_secret

       encrypt_email_secret("your_email@qq.com")
       encrypt_email_secret("your_app_specific_password")
       ```
    4. 将上面命令打印出来的 `enc:...` 文本分别填入 `email.address` 和 `email.password`。
  - 运行时会自动解密到内存中用于 IMAP 登录，**不会**把明文写回配置文件或日志。
  - 若仍使用明文地址/密码（不以 `enc:` 开头），系统也能工作，但不推荐在生产环境中使用。

- **GUI 中的验证码显示与复制**
  - 当为某个账号成功拉取到验证码（例如主题 `604688 - Verify your Email with Windsurf`），日志会输出：
    `📧 账号{id}({email})收到验证码: 604688`。
  - GUI “进度”区域下方会显示“当前账号验证码”，并启用“复制验证码”按钮。
  - 点击“复制验证码”后：
    - 验证码会被写入系统剪贴板；
    - 日志会记录“已复制账号 {email} 的验证码”。

## 打包构建（PyInstaller）

- **准备环境**
  ```powershell
  python -m pip install -U pyinstaller
  ```

- **构建 CLI 版（控制台应用）**
  ```powershell
  python -m PyInstaller --clean --noconfirm configflow.spec
  ```
  - 产物：`dist/ConfigFlowRegister.exe`
  - 运行：
    ```powershell
    .\dist\ConfigFlowRegister.exe --flow flows\windsurf_register.toml --count 1 --interval 0
    ```

- **构建 GUI 版（GUI + 控制台日志）**
  ```powershell
  python -m PyInstaller --clean --noconfirm configflow_gui.spec
  ```
  - 产物目录：`dist/ConfigFlowRegisterGUI/`
  - 启动：
    ```powershell
    .\dist\ConfigFlowRegisterGUI\ConfigFlowRegisterGUI.exe
    ```

- **资源放置说明（打包后）**
  - `config.json`：与 EXE 同级（首次运行自动生成）。
  - Flow 文件：支持放在以下任一位置（均可被识别）：
    - `EXE 同级根目录`，如：`dist/ConfigFlowRegisterGUI/windsurf_register.toml`
    - `flows/ 子目录`，如：`dist/ConfigFlowRegisterGUI/flows/windsurf_register.toml`

- **常见问题**
  - Chrome/Chromedriver：需安装 Chrome；系统路径存在不匹配时可临时移除 PATH 中的旧 chromedriver，让 UC 自动管理。
  - 权限：确保对 EXE 同级目录有写权限（日志、config.json、data/.）