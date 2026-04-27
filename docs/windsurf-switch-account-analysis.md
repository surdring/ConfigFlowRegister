# Windsurf 一键切号集成方案分析报告

## 1. 调研概述

### 1.1 目标
- 参考 `WindsurfAPI-master` 项目的账号管理机制
- 在 `account-pool-gui`（Tauri + Rust 桌面应用）中集成"一键切号"功能
- 解决当前用户需要在网页/IDE 上手动切换 Windsurf 账号的痛点

### 1.2 调研范围
- `WindsurfAPI-master` 源码分析（认证流程、账号池轮询）
- Windsurf 桌面端（Linux）本地认证数据存储机制
- 一键切号的技术可行性与实现路径

---

## 2. WindsurfAPI 项目分析

### 2.1 项目定位
WindsurfAPI 是一个 Node.js 服务端代理，它将 Windsurf 的 AI 模型能力封装为两套标准 API：
- `POST /v1/chat/completions`（OpenAI 兼容）
- `POST /v1/messages`（Anthropic 兼容）

### 2.2 认证流程（核心参考）

源码位置：`WindsurfAPI-master/src/dashboard/windsurf-login.js`

Windsurf 的登录支持两条认证链路：

#### 链路 A：Auth1 密码登录（新账号）
```
1. POST https://windsurf.com/_devin-auth/connections
   → 查询账号支持的认证方式

2. POST https://windsurf.com/_devin-auth/password/login
   → 邮箱+密码登录，获取 auth1Token

3. POST https://server.self-serve.windsurf.com/.../WindsurfPostAuth
   → 用 auth1Token 换取 sessionToken

4. POST https://server.self-serve.windsurf.com/.../GetOneTimeAuthToken
   → 用 sessionToken 换取一次性 authToken

5. POST https://api.codeium.com/register_user/
   → 用 authToken 注册 Codeium，获取 api_key
```

#### 链路 B：Firebase 密码登录（旧账号）
```
1. POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword
   → 邮箱+密码登录 Firebase，获取 idToken

2. POST https://api.codeium.com/register_user/
   → 用 idToken 注册 Codeium，获取 api_key
```

#### 自动回退机制
WindsurfAPI 的 `windsurfLogin()` 函数会先尝试 Auth1，失败后自动回退到 Firebase。

### 2.3 账号池管理

源码位置：`WindsurfAPI-master/src/auth.js`

- **存储格式**：`accounts.json`，每个账号包含 `id`, `email`, `apiKey`, `apiServerUrl`, `tier`, `capabilities`, `refreshToken` 等
- **轮询策略**：Round Robin + 按 tier 的 RPM 限制加权
- **健康追踪**：error count, auto-disable, rate limiting
- **持久化**：原子写入（write to .tmp then rename）

### 2.4 对 account-pool-gui 的启示

WindsurfAPI 的账号池管理是**服务端级别**的：它维护多个账号的 apiKey，在收到 API 请求时自动轮询选择一个可用账号，然后通过本地 Language Server 转发给 Windsurf 云端。

**它并不直接操作 Windsurf IDE 客户端的登录状态**——这是它与 account-pool-gui 场景的关键差异。

---

## 3. Windsurf 桌面端认证数据存储分析

### 3.1 关键目录定位（Linux）

通过系统扫描，确定 Windsurf 桌面端在 Linux 上的数据存储位置：

| 目录 | 用途 | 关键程度 |
|------|------|---------|
| `~/.config/Windsurf/User/globalStorage/state.vscdb` | VS Code globalStorage SQLite 数据库，包含 Windsurf 核心认证状态 | ⭐⭐⭐ 最高 |
| `~/.config/Windsurf/Cookies` | Chromium Cookies SQLite 数据库 | ⭐⭐⭐ 高 |
| `~/.config/Windsurf/Local Storage/leveldb/` | Electron localStorage，包含 unleash/feature flag 等 | ⭐⭐ 中 |
| `~/.config/Windsurf/Session Storage/` | Electron sessionStorage | ⭐⭐ 中 |
| `~/.codeium/windsurf/user_settings.pb` | Protobuf 用户偏好设置（模型选择等） | ⭐ 低 |

### 3.2 state.vscdb 认证数据结构

通过对 `~/.config/Windsurf/User/globalStorage/state.vscdb` 的 SQLite 查询，发现以下关键键值：

#### 明文认证数据
```sql
-- key: windsurfAuthStatus
-- value: {"apiKey":"devin-session-token$eyJhbGciOiJIUzI1NiIs..."}
```
- `apiKey` 是一个 JWT 格式的 session token（以 `devin-session-token$` 为前缀）
- 这是 Windsurf 扩展在 `codeium.windsurf` 中使用的核心认证凭据

#### 扩展配置
```sql
-- key: codeium.windsurf
-- value: {"installationId":"...","apiServerUrl":"https://server.self-serve.windsurf.com",...}
```

#### 加密 Secret 存储
```sql
-- key: secret://{"extensionId":"codeium.windsurf","key":"windsurf_auth.sessions"}
-- key: secret://{"extensionId":"codeium.windsurf","key":"windsurf_auth.apiServerUrl"}
```
- 使用 VS Code Secret Storage 机制加密存储
- Linux 上依赖 `gnome-keyring` / `libsecret`
- **同一台机器上，不同账号的加密值可以互换**（因为 keyring 主密钥相同）

#### 套餐信息
```sql
-- key: windsurf.settings.cachedPlanInfo
-- value: {"planName":"Free","startTimestamp":...,"endTimestamp":...,"usage":{...}}
```

### 3.3 认证切换的核心发现

**关键结论**：`state.vscdb` 是整个 Windsurf 桌面端认证态的"单一事实来源"。只要替换该文件中的认证相关记录，并配合 `Cookies` 文件，即可实现账号切换。

---

## 4. 一键切号技术方案对比

### 方案 A：配置文件快照（Profile Snapshot）

**思路**：为每个账号保存一套 Windsurf 本地配置文件的快照，切换时替换文件并重启 Windsurf。

**快照内容**：
- `~/.config/Windsurf/User/globalStorage/state.vscdb`（核心）
- `~/.config/Windsurf/Cookies`（网站态）
- `~/.config/Windsurf/Local Storage/leveldb/`（localStorage）
- `~/.config/Windsurf/Session Storage/`（sessionStorage）
- `~/.codeium/windsurf/user_settings.pb`（用户偏好）

**操作流程**：
1. 用户在 Windsurf 桌面端登录账号 A
2. 在 account-pool-gui 中点击「保存当前登录态」→ 关联到账号 A
3. 后续点击「一键切号」→ 账号 B：
   - 检测并关闭 Windsurf 进程
   - 将账号 B 的快照恢复到原配置目录
   - 重新启动 Windsurf

**优点**：
- 实现简单，不需要逆向 secret storage 加密算法
- 可靠性强，100% 还原登录态
- 不依赖网络（纯本地文件操作）

**缺点**：
- 需要用户先手动登录每个账号并保存一次快照
- 切换时需要重启 Windsurf（体验有中断）
- UI 状态（sidebar 大小、主题等）也会被一起切换
- 无法跨机器使用（加密值与 keyring 绑定）

**风险**：
- 替换 SQLite 数据库时若 Windsurf 未完全退出，可能导致数据损坏
- 需要妥善处理文件权限和原子写入

---

### 方案 B：API 自动化登录（参考 WindsurfAPI）

**思路**：在 account-pool-gui 中集成 WindsurfAPI 的 `windsurfLogin()` 逻辑，直接通过网络 API 获取每个账号的 token/apiKey，然后写入 Windsurf 的 state.vscdb。

**操作流程**：
1. account-pool-gui 中已存储邮箱和密码（需要扩展数据模型）
2. 点击「一键切号」→ 调用 Auth1/Firebase 登录 API → 获取 token → Codeium 注册 → 获取 apiKey
3. 将 apiKey 写入 `state.vscdb` 的 `windsurfAuthStatus` 和 `secret://...` 记录
4. 重启 Windsurf

**优点**：
- 用户体验好：不需要先手动登录每个账号
- 首次配置即可切号
- 可在 account-pool-gui 中集中管理密码

**缺点**：
- 实现复杂度高，需要完整移植 WindsurfAPI 的认证逻辑到 Rust
- 需要处理网络请求、代理、fingerprint 随机化等
- VS Code Secret Storage 的加密写入机制不透明，直接写入原始值可能无法被正确解密
- Windsurf 可能升级认证流程，需要持续维护
- 密码需要安全存储（当前 account-pool-gui 设计为不存密码）

**风险**：
- secret storage 加密机制复杂，可能导致 Windsurf 无法识别写入的凭据
- 可能违反 Windsurf ToS
- 网络登录有频率限制和风控

---

### 方案 C：Web 自动化（浏览器操作）

**思路**：在 account-pool-gui 中嵌入浏览器自动化（如 headless Chrome），自动打开 windsurf.com 网页版进行登录/退出。

**缺点**：
- 只适用于网页版，不影响桌面端 Windsurf IDE 的登录态
- 实现重、依赖多
- 网页版和桌面端的登录态并不完全互通

**结论**：不推荐。

---

### 方案 D：混合方案（推荐）

**思路**：以方案 A（配置文件快照）为基础，在账号池 GUI 中增加「自动登录」扩展功能作为高级选项。

**核心流程**：
1. **默认路径**：用户首次登录 Windsurf → 在 GUI 中「保存当前登录态」→ 后续「一键切号」
2. **高级路径**（可选）：输入密码 → 调用 Auth1/Firebase API → 自动获取 token → 写入配置 → 保存快照

**优点**：
- 默认路径简单可靠，用户可立即使用
- 高级路径可逐步迭代开发
- 符合当前 account-pool-gui 不存密码的设计哲学

---

## 5. 推荐实现方案（方案 A 详细设计）

### 5.1 数据模型扩展

在 SQLite 中新增 `account_sessions` 表：

```sql
CREATE TABLE account_sessions (
    email TEXT PRIMARY KEY NOT NULL,
    has_session INTEGER DEFAULT 0,
    saved_at TEXT DEFAULT NULL,
    session_path TEXT DEFAULT NULL  -- 快照存储路径
);
```

### 5.2 Rust 后端模块设计

新增 `windsurf_session.rs` 模块，职责：

| 函数 | 说明 |
|------|------|
| `get_windsurf_config_paths()` | 获取 Windsurf 配置目录路径 |
| `save_session(email, session_dir)` | 复制关键配置文件到快照目录 |
| `restore_session(email, session_dir)` | 从快照目录恢复配置文件 |
| `kill_windsurf_processes()` | 查找并终止 Windsurf 进程 |
| `launch_windsurf()` | 启动 Windsurf 桌面端 |
| `read_current_email_from_state()` | 从 `state.vscdb` 中解析当前登录的邮箱/token |

### 5.3 关键文件快照清单

快照目录结构（`app_data_dir/windsurf_sessions/{email_hash}/`）：

```
windsurf_sessions/
└── a1b2c3d4/  # SHA256(email) 前8位
    ├── state.vscdb          # ~/.config/Windsurf/User/globalStorage/state.vscdb
    ├── Cookies              # ~/.config/Windsurf/Cookies
    ├── local_storage/       # ~/.config/Windsurf/Local Storage/leveldb/
    ├── session_storage/     # ~/.config/Windsurf/Session Storage/
    └── user_settings.pb     # ~/.codeium/windsurf/user_settings.pb
```

### 5.4 一键切号操作流程

```
用户点击「一键切号」→ 账号 B
  │
  ├─ 1. 检查账号 B 是否有已保存的快照
  │     └─ 否 → 提示用户先「保存当前登录态」
  │
  ├─ 2. 检测 Windsurf 进程是否运行
  │     ├─ 是 → 提示"Windsurf 将被关闭以切换账号"
  │     └─ 否 → 继续
  │
  ├─ 3. 关闭 Windsurf 进程（发送 SIGTERM，超时后 SIGKILL）
  │
  ├─ 4. 等待 500ms 确保进程退出和文件句柄释放
  │
  ├─ 5. 备份当前配置文件（可选，到 .backup/ 目录）
  │
  ├─ 6. 将账号 B 的快照文件复制回原配置目录
  │     ├─ 复制前校验文件完整性（文件大小、存在性）
  │     └─ 使用原子写入策略（写入 .tmp 后 rename）
  │
  ├─ 7. 更新数据库：记录最后切换时间和当前活跃账号
  │
  └─ 8. 启动 Windsurf（/usr/share/windsurf/windsurf）
        └─ 后台启动，不阻塞 GUI
```

### 5.5 前端 UI 设计

在现有 `App.tsx` 账号列表中扩展：

1. **每行增加操作按钮**：
   - 「保存登录态」图标按钮（仅当该账号无快照时显示）
   - 「一键切号」主按钮（带播放图标）
   - 已保存快照的账号显示绿色标记

2. **顶部状态栏增加**：
   - 当前 Windsurf 登录账号显示（通过读取 state.vscdb 实时检测）
   - 「一键切号」下拉菜单（快速选择可用账号）

3. **批量操作扩展**：
   - 全选后「批量保存登录态」（对每个选中账号依次提示"请先在 Windsurf 中登录此账号"）

### 5.6 安全与风险处理

| 风险点 | 缓解措施 |
|--------|---------|
| 文件替换时 Windsurf 未退出 | 严格检测进程，SIGTERM → 等待 2s → SIGKILL |
| 快照文件被损坏/篡改 | 保存时记录文件大小 checksum（SHA256），恢复前校验 |
| 多账号快照互相污染 | 每个账号独立目录，使用 email hash 隔离 |
| 当前配置丢失 | 切换前自动备份当前配置到 `.backup/` |
| 路径在不同 Linux 发行版差异 | 使用 `dirs::home_dir()` + 固定相对路径，支持 `WINDSURF_CONFIG_DIR` 环境变量覆盖 |
| 跨平台（Windows/macOS） | 第一阶段仅支持 Linux，后续通过 `cfg(target_os)` 扩展路径 |

---

## 6. 开发任务清单

### Phase 1：MVP（最小可行产品）— windsurf:// URI 方案
- [x] 验证 Firebase ID token + windsurf:// URI 切换账号可行性
- [ ] Tauri 后端添加 `switch_windsurf_account` 命令（Rust HTTP 请求 Firebase + xdg-open）
- [ ] 前端添加"切换到该账号"按钮
- [ ] 基本错误处理（网络超时、Firebase 登录失败、xdg-open 失败）

### Phase 2：体验优化
- [ ] 自动检测 Windsurf 运行状态
- [ ] 切换后自动刷新 Windsurf（通过 IPC 或重启）
- [ ] 账号状态同步（当前活跃账号高亮）
- [ ] 快捷键支持（如 Ctrl+Shift+N 切换下一个账号）
- [ ] Auth1 登录作为 Firebase 的备选路径

### Phase 3：高级功能（可选）
- [ ] 批量预登录（提前获取 token 缓存）
- [ ] Token 缓存与自动刷新（Firebase token 有过期时间）
- [ ] 加密存储 token（防止其他用户读取）

---

## 7. 结论

**推荐采用方案 C（windsurf:// URI 注入）作为最终实现方案**，已验证可行！

### 方案 C：windsurf:// URI 注入（✅ 已验证）

**核心思路**：通过 API 获取 Firebase ID token，构造 `windsurf://codeium.windsurf/#access_token=TOKEN` URI，用 `xdg-open` 打开，让 Windsurf 自己完成认证存储（包括加密的 secret:// 记录）。

**验证结果**：
- ✅ Firebase 登录获取 ID token 成功
- ✅ `windsurf://` URI 触发 Windsurf 认证处理成功
- ✅ 账号切换成功（csmfxdoflfurqm6@yaoshangxian.top）
- ❌ OTT 格式（`ott$...`）不被 Windsurf 接受，必须用 Firebase ID token（JWT 格式，`eyJ...` 开头）

**优势**：
1. **无需逆向加密**：Windsurf 自己处理加密存储，完美解决 secret:// 记录问题
2. **可靠**：使用 Windsurf 官方认证路径，不会因加密格式变更而失效
3. **简单**：只需一次 API 调用（Firebase signInWithPassword）+ 一次 xdg-open
4. **通用**：Firebase 登录比 Auth1 更通用（部分账号 Auth1 失败但 Firebase 成功）

**实现脚本**：`docs/switch_windsurf_account.py`

**流程**：
```
1. Firebase signInWithPassword(email, password) → idToken
2. 构造 URI: windsurf://codeium.windsurf/#access_token={idToken}
3. xdg-open URI → Windsurf 自动完成 registerUser + login + 加密存储
4. 账号切换完成
```

**备选方案**（如果 Firebase 不可用）：
- Auth1 登录 → sessionToken 也可尝试作为 access_token
- 直接写入 state.vscdb 明文 apiKey（需配合加密记录，不推荐）

### 原方案对比

| 方案 | 状态 | 复杂度 | 可靠性 |
|------|------|--------|--------|
| A: 配置文件快照 | 可行但笨重 | 高 | 中 |
| B: SQLite Key 替换 | 部分可行（缺加密记录） | 中 | 低 |
| **C: windsurf:// URI 注入** | **✅ 已验证** | **低** | **高** |

WindsurfAPI 项目的最大参考价值在于：
- **认证流程逆向**：明确了 Auth1/Firebase → Codeium 注册的完整链路
- **账号池设计模式**：Round Robin + 健康追踪 + 原子持久化的设计可直接借鉴
- **错误码体系**：`ERR_INVALID_PASSWORD`, `ERR_NO_PASSWORD_SET` 等规范化错误处理
