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

## 虚拟环境配置（推荐）

使用虚拟环境隔离项目依赖，避免与系统 Python 环境冲突。

### 创建并激活虚拟环境

**Linux/macOS:**
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

**Windows (CMD):**
```cmd
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate.bat

# 安装依赖
pip install -r requirements.txt
```

### 退出虚拟环境
```bash
deactivate
```

## 分支切换

本项目使用 `linux-code` 分支作为 Linux 平台的主要开发分支。

### 切换到 linux-code 分支

```bash
# 查看所有分支
git branch -a

# 切换到 linux-code 分支
git checkout linux-code

# 如果本地没有该分支，先拉取远程分支
git fetch origin linux-code
git checkout -b linux-code origin/linux-code
```

### 保持分支同步

```bash
# 拉取最新更新
git pull origin linux-code
```

## 运行方式

### GUI 模式
1. 在 `config.json` 中设置默认 Flow（已提供模板 `config.json.template`）：
```json
{
  "flow": { "file": "flows/windsurf_register.toml" }
}
```
2. 运行 GUI：
```bash
python src/main.py
```
3. 在 GUI 中开始任务，流程会按 TOML 执行，遇到 `pause_for_manual` 时可点击“✓ 手动继续”。

### CLI 模式
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
  - 成功：0 / 配置/文件错误：1 / 执行失败：2 / 用户中断（Ctrl+C）：130
- **注意**
  - 无头模式（headless）下验证码通过率很低，建议关闭 headless。
  - Linux 无桌面时可用 `xvfb-run` 提供虚拟显示，但仍建议有头运行以提高通过率。

### Flow 校验（可选）
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
    1. 设置加密密钥（优先从 `.env` 文件读取，也可用环境变量）：
       - 方式一（推荐）：在项目根目录或可执行文件同级目录创建 `.env` 文件：
         ```bash
         # .env
         CONFIGFLOW_EMAIL_SECRET_KEY=你的密钥
         ```
       - 方式二：通过环境变量设置：
         - Windows PowerShell：
           ```powershell
           $env:CONFIGFLOW_EMAIL_SECRET_KEY="你的强密码"
           ```
         - Linux/macOS：
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

- **数据目录**
  - 开发环境：使用项目根目录 `data/`
  - 打包后：使用 `dist/data/`（与 `dist/ConfigFlowRegisterGUI/` 同级，避免被 PyInstaller 清除）
  - **注意**：首次打包后需手动创建 `dist/data/` 并复制旧数据

## Linux 使用说明

### 安装 Chrome 浏览器
```bash
# Debian/Ubuntu
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
sudo apt update
sudo apt install google-chrome-stable

# 或直接使用包管理器（某些发行版）
# sudo apt install google-chrome-stable
```

### 安装 tkinter（GUI 版必需）
```bash
# tkinter 是系统级 C 扩展，pip 无法安装
sudo apt install python3-tk
```

### 无桌面环境运行
```bash
sudo apt install xvfb
xvfb-run python src/main.py
```

### 检查清单

| 检查项 | 命令 |
|-------|------|
| Chrome 是否安装 | `google-chrome --version` |
| tkinter 是否可用 | `python -c "import tkinter; print('OK')"` |
| ChromeDriver 自动管理 | 无需手动安装，`undetected-chromedriver` 首次运行会自动下载 |

**注意**：
- `undetected-chromedriver` 会自动下载匹配的 ChromeDriver 到 `~/.local/share/undetected_chromedriver/`，无需手动配置
- 首次运行会自动迁移旧版 JSON 数据到 SQLite


## 打包构建（PyInstaller）

- **准备环境**
  ```powershell
  python -m pip install -U pyinstaller
  ```

- **Windows PowerShell 注意事项**
  - 若你的 Python 安装在带空格的路径（例如 `C:\Program Files\Python311\python.exe`），在 PowerShell 里需要使用 `&` 调用运算符：
    ```powershell
    & "C:\Program Files\Python311\python.exe" -m pip install -r .\requirements.txt
    & "C:\Program Files\Python311\python.exe" -m PyInstaller --clean --noconfirm configflow_gui.spec
    ```
  - 建议始终用同一个解释器执行 `-m pip` 与 `-m PyInstaller`，避免出现 `No module named PyInstaller`（安装到了别的环境/用户目录）。

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


### Linux 打包构建

**环境准备**
```bash
# 1. 安装 tkinter（参见 Linux 使用说明）
sudo apt install python3-tk

# 2. 创建虚拟环境并安装依赖（参见上方「虚拟环境配置」）
#    强烈建议使用虚拟环境打包，否则 PyInstaller 会将系统 Python 的 55+ 依赖全部打包，
#    导致产物过大（>200MB 对比 ~91MB）

# 3. 确保 Chrome 已安装
google-chrome --version
```

**构建 GUI 版**
```bash
python -m PyInstaller --clean --noconfirm configflow_gui.spec
```
- 产物目录：`dist/ConfigFlowRegisterGUI/`
- 启动：
  ```bash
  cd ~/workspace/ConfigFlowRegister && ./dist/ConfigFlowRegisterGUI.bin
  ```

**构建 CLI 版**
```bash
python -m PyInstaller --clean --noconfirm configflow.spec
```
- 产物：`dist/ConfigFlowRegister.bin`
- 运行：
  ```bash
  ./dist/ConfigFlowRegister.bin --flow flows/windsurf_register.toml --count 1
  ```

**打包后资源放置**
- `config.json`：与可执行文件同级（首次运行自动生成）
- Flow 文件：打包时自动包含在 `_internal/flows/` 目录下；也可手动放在可执行文件同级或 `flows/` 子目录
- **PyInstaller 6 one-dir 布局**：数据文件位于 `_internal/` 子目录，程序会自动从 `_internal/` 查找资源

**Linux 打包注意事项**
- **虚拟环境**：强烈建议创建虚拟环境打包，否则 PyInstaller 会将系统 Python 的 55+ 依赖全部打包，导致产物过大（>200MB 对比 ~91MB）
- **tkinter 依赖**：打包前需安装系统包 `sudo apt install python3-tk`（pip 无法安装此 C 扩展）
- **无需包含 Chrome**：目标机器需要自行安装 Chrome，`undetected-chromedriver` 会在运行时自动下载匹配的 ChromeDriver
- **ChromeDriver 手动安装（备用）**：若 UC 自动下载失败（如 Chrome 142+ 版本），可手动下载对应版本到 `~/.local/share/undetected_chromedriver/` 或系统 PATH
  ```bash
  # 示例：手动下载 ChromeDriver 142
  wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/142.0.7444.175/linux64/chromedriver-linux64.zip
  unzip chromedriver-linux64.zip && mv chromedriver-linux64/chromedriver ~/.local/share/undetected_chromedriver/
  sudo ln -s ~/.local/share/undetected_chromedriver/chromedriver /usr/local/bin/chromedriver
  ```
- **图形环境**：确保目标机器有图形环境（X11 或 Wayland），或使用 `xvfb` 虚拟显示
- **文件权限**：打包后的可执行文件已含执行权限，如需手动添加：`chmod +x ./dist/ConfigFlowRegisterGUI/ConfigFlowRegisterGUI.bin`


## 性能优化记录

### 页面加载优化
- **pageLoadStrategy = `eager`**：浏览器启动时设置页面加载策略为 `eager`，HTML 解析完即返回，不等待图片、第三方 JS 等资源加载完成，大幅减少 `navigate` 步骤的等待时间。
- **implicitly_wait 缩短**：从 5 秒缩短为 2 秒，减少元素查找的默认等待。

### OTP 验证码邮件获取优化
- **只搜索未读邮件**：IMAP 搜索条件从 `ALL` 改为 `UNSEEN`，避免遍历大量历史邮件。
- **每轮最多检查 5 封最新邮件**：按 ID 降序取最新 5 封，不再逐一遍历所有未读邮件。
- **标记已读**：不匹配的邮件和已提取验证码的邮件都会被标记为已读（`\\Seen`），避免未读邮件堆积导致重复检查。

### OTP 输入与页面跳转优化
- **验证码输入无多余动作**：`type_otp_digits` 逐位输入 6 位验证码后不再发送 `Keys.RETURN`，由页面自动提交。
- **移除 sleep 等待**：TOML 中移除了验证码输入后的 `sleep 5000` 步骤。
- **简化 `wait_onboarding_source`**：
  - 输入验证码后直接等待页面跳转到 `https://windsurf.com/profile`（最多 30 秒）。
  - 跳转成功后等待 2 秒，然后开始新一轮注册。
  - 超时则标记失败，重启浏览器继续下个账号。

### 账号数量限制
- 最大注册账号数量从 200 提升到 500（GUI Spinbox、配置验证、数据管理均已同步更新）。