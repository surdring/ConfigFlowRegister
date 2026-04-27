# 账号池管理工具 (Rust + Tauri)

基于 Windsurf Usage 页面的配额机制，设计的跨平台账号池管理工具，帮助用户管理多个免费 Windsurf 账号，实现配额轮换使用。

## 特性

- **一键登录**：支持 Auth1 / Firebase 双通道登录，自动切换 Windsurf 账号
- **额度管理**：登录后自动注册 Codeium 获取 apiKey，查询并显示 plan / 日额度 / 周额度百分比
- **自动耗尽**：额度刷新后自动标记日/周耗尽（百分比 ≤ 0 即视为耗尽），顶部统计实时更新
- **手动刷新**：每行 ⟳ 按钮可单独刷新额度；未登录账号会提示先登录
- **检查重置**：一键重置配额 + 批量刷新所有账号额度，显示刷新结果
- **CLI 备选**：Rust 登录失败时可通过 Python 脚本备选登录（仅登录+打开URI，快速响应）
- **代理自适应**：自动检测系统代理环境变量，代理不可达时直连
- **配额管理**：每日 16:00 GMT+8 重置日配额，每周六同时重置周配额
- **状态追踪**：支持手动标记账号的日配额/周配额耗尽状态
- **批量导入**：支持从 JSON 文件或文本批量导入账号
- **搜索过滤**：支持按邮箱搜索、按状态筛选（可用/日耗尽/周耗尽）
- **虚拟列表**：使用 react-virtuoso 实现高性能虚拟滚动，万级账号流畅渲染
- **服务端分页**：后端分页查询 + SQLite 索引优化，减少前端内存占用
- **数据库迁移**：自动检测并添加新列，旧数据库无缝升级
- **跨平台**：Windows、Linux、macOS 原生支持

## 技术栈

- **后端**：Rust + SQLite + Tauri
- **前端**：React + TypeScript + Tailwind CSS + react-virtuoso
- **构建**：Tauri CLI

## 项目结构

```
account-pool-gui/
├── src-tauri/          # Rust 后端代码
│   ├── src/
│   │   ├── main.rs     # 程序入口
│   │   ├── lib.rs      # 库入口
│   │   ├── models.rs   # 数据模型
│   │   ├── database.rs # SQLite 数据库操作
│   │   ├── pool.rs     # 账号池核心逻辑
│   │   └── commands.rs # Tauri 命令
│   ├── Cargo.toml
│   └── tauri.conf.json # Tauri 配置
├── src/                # 前端 React 代码
│   ├── App.tsx         # 主组件
│   ├── types.ts        # TypeScript 类型
│   ├── main.tsx        # 前端入口
│   └── index.css       # 样式
├── package.json        # 前端依赖
├── Cargo.toml          # 工作区配置
└── README.md
```

## 开发环境

### 前置要求

1. **Rust** (1.77+)
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

2. **Node.js** (18+)
   ```bash
   # 使用 nvm 安装
   nvm install 18
   nvm use 18
   ```

3. **Tauri CLI**（已包含在 npm 依赖中，无需单独安装）
   ```bash
   # 如需全局安装（可选）
   cargo install tauri-cli
   ```

4. **系统依赖** (Linux 必需)

   **Ubuntu 24.04 (Noble) 及更新版本：**
   ```bash
   sudo apt update
   sudo apt install -y libgtk-3-dev libwebkit2gtk-4.1-dev libglib2.0-dev pkg-config librsvg2-dev patchelf
   # 注：Ubuntu 24.04 使用 webkit2gtk-4.1，且 libappindicator 已被 libayatana-appindicator 替代
   ```

   **Ubuntu 22.04/Debian 11 及更早版本：**
   ```bash
   sudo apt update
   sudo apt install -y libgtk-3-dev libwebkit2gtk-4.0-dev libappindicator3-dev librsvg2-dev patchelf
   ```

   **Fedora:**
   ```bash
   sudo dnf install gtk3-devel webkit2gtk4.1-devel librsvg2-devel
   ```

   **Arch Linux:**
   ```bash
   sudo pacman -S gtk3 webkit2gtk-4.1 librsvg
   ```

### 开发运行

```bash
# 安装前端依赖（首次）
npm install

# 启动开发服务器（热重载）
npm run tauri dev

# 或使用全局 tauri-cli（需先 cargo install tauri-cli）
# cargo tauri dev
```

### 构建发布版本

```bash
# 构建
npm run tauri build

# 输出位置
# 可执行文件: target/release/account-pool-gui
# DEB 包: target/release/bundle/deb/account-pool-gui_0.1.0_amd64.deb
# RPM 包: target/release/bundle/rpm/account-pool-gui-0.1.0-1.x86_64.rpm
```

#### 直接运行

```bash
# 构建后直接运行
./target/release/account-pool-gui

# 或安装 DEB 包（自动处理依赖），如果已安装先卸载
sudo dpkg -r account-pool-gui
sudo dpkg -i target/release/bundle/deb/account-pool-gui_0.1.0_amd64.deb
sudo apt-get install -f
```

#### 图标准备

构建需要应用图标，将图标文件放入 `src-tauri/icons/` 目录：

```
src-tauri/icons/
├── 32x32.png      # 窗口图标
├── 128x128.png    # 应用商店图标
├── 128x128@2x.png # Retina 图标
├── icon.icns      # macOS 图标
└── icon.ico       # Windows 图标
```

你可以使用 Tauri CLI 自动生成图标：

```bash
# 从源图标生成所有尺寸 (需要 512x512+ 正方形源图，透明背景最佳)
npx tauri icon app-icon.png
```

**图标要求：**
- 尺寸：512x512 像素或更大
- 比例：必须是正方形（1:1）
- 背景：推荐透明背景（PNG with alpha），这样在各种主题下显示效果更好
- 如果源图有背景，可用 ImageMagick 处理：
```bash
convert "Generated Image April 25, 2026 - 10_30AM.png" \
  -fill none -fuzz 15% -draw "matte 0,0 floodfill" \
  -trim +repage \
  -resize 512x512 \
  -background none -gravity center -extent 512x512 \
  app-icon.png
```

如果暂时不需要图标，可以删除 `tauri.conf.json` 中的 `bundle.icon` 配置（仅用于开发测试）。

## 核心功能

### 1. 一键登录
- 点击"登录"按钮，自动尝试 Auth1 登录，失败回退 Firebase
- 登录成功后自动通过 `windsurf://` URI 切换 Windsurf IDE 账号
- 自动更新上次使用时间和使用次数
- 后台自动注册 Codeium 获取 apiKey 并查询额度
- 额度 ≤ 0% 自动标记日/周耗尽，顶部统计实时更新
- 支持 CLI 脚本备选登录（点击 CLI 按钮，仅登录+打开URI，快速响应）

### 2. 账号取用
- 点击"取用账号"按钮
- 系统自动选择下一个可用账号并一键登录切换
- 支持一键复制邮箱

### 3. 额度管理
- 登录后自动获取：plan 名称、日额度百分比、周额度百分比
- 点击 ⟳ 按钮手动刷新单个账号额度
- 点击"检查重置"按钮批量刷新所有有 apiKey 的账号额度
- 额度颜色提示：>50% 绿色、20-50% 黄色、<20% 红色
- 百分比 ≤ 0 自动标记为耗尽，无需手动操作

### 4. 配额标记
- 日配额耗尽：标记后账号当日不再被取用
- 周配额耗尽：标记后账号本周不再被取用
- 取消标记：恢复账号可用状态
- 支持手动标记和额度自动标记两种方式

### 5. 检查重置
- 点击"检查重置"按钮，先重置配额再批量刷新额度
- 每天 16:00 GMT+8 自动重置日配额，每周六同时重置周配额
- 启动时自动检查并执行配额重置
- 批量刷新结果显示："配额已重置，额度已刷新: X 成功, Y 失败"

### 6. 批量导入
- 从 JSON 文件导入（邮箱数组格式）
- 从文本框粘贴导入（每行一个邮箱）
- 自动去重，已存在的账号会被跳过

### 7. 批量操作
- 支持多选账号
- 批量标记配额状态
- 批量删除账号

## 导入格式

### JSON 文件格式

导入的 JSON 文件应为邮箱数组：

```json
[
  "user1@example.com",
  "user2@example.com",
  "user3@example.com"
]
```

或者从本项目的注册结果导出文件导入（经过清理只剩邮箱）

### 文本格式

在"导入账号"弹窗中，直接粘贴邮箱列表，每行一个：

```
user1@example.com
user2@example.com
user3@example.com
```

## 数据存储

数据存储在系统应用数据目录（由 Tauri `identifier` 决定）：
- **Linux**: `~/.local/share/com.accountpool.gui/`
- **Windows**: `%APPDATA%/com.accountpool.gui/`
- **macOS**: `~/Library/Application Support/com.accountpool.gui/`

数据库文件：`account_pool.db` (SQLite)

CLI 备选脚本：`switch_windsurf_account.py`（需手动放到数据目录下）

## 界面说明

- 统计卡片：显示总数、可用、日耗尽、周耗尽数量（耗尽>0 时数字变红）
- 重置倒计时：显示下次日重置和周重置时间
- 搜索过滤：邮箱搜索框 + 状态下拉筛选（可用/日耗尽/周耗尽）
- 虚拟列表：高性能滚动渲染，斑马纹 + hover 高亮
- 额度列：显示 plan 名称 + 日/周额度百分比，颜色随额度变化
- 操作列：登录 / CLI / ⟳刷新额度 三个按钮
- 检查重置按钮：点击后显示 loading，完成后 toast 提示结果
- 批量操作：全选/多选 + 批量标记/删除
- 服务端分页：支持切换每页条数（20/50/100）

## 使用流程示例

### 场景1：一键登录轮换使用

1. 打开程序，查看"可用"账号数量和下次重置倒计时
2. 点击"取用账号"，系统自动登录并切换 Windsurf IDE
3. 后台自动获取额度信息，额度 ≤ 0 自动标记耗尽
4. 也可对单个账号点"登录"按钮切换，点 ⟳ 刷新额度
5. 额度耗尽后，再次"取用账号"获取下一个可用账号

### 场景2：批量导入新账号

1. 完成一批账号注册（如100个）
2. 导出结果为 JSON（已自动清理密码，只剩邮箱）
3. 在账号池 Tab 点击"导入账号"
4. 选择 `dist/exports/windsurf-accounts-xxx.json`
5. 新账号自动添加到池尾，状态为 `available`

### 场景3：每日重置

1. 第二天早上打开程序
2. 自动检测到今天日期 > 上次检查日期
3. 所有 `daily_exhausted=true` 的账号自动恢复
4. 如果是周六，同时重置 `weekly_exhausted`
5. 可用账号数量恢复，继续轮换

## 常见问题

### Q: 构建时报错缺少 `icon.ico` 或其他图标文件？

A: 需要准备应用图标。最简单的方法是：
- 准备一个 1024x1024 的 PNG 图标
- 安装 `cargo install tauri-icon`
- 运行 `tauri-icon icon.png` 生成所有尺寸

### Q: 如何在开发时跳过图标检查？

A: 编辑 `src-tauri/tauri.conf.json`，删除或注释掉 `bundle.icon` 字段：
```json
"bundle": {
  "active": true,
  "targets": "all"
  // 暂时移除 icon 配置
}
```

### Q: Linux 构建失败，提示缺少 webkit2gtk？

A: 根据 Ubuntu 版本安装对应的包：

**Ubuntu 24.04+:**
```bash
sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev
```

**Ubuntu 22.04 及更早:**
```bash
sudo apt install libwebkit2gtk-4.0-dev libgtk-3-dev
```

### Q: 数据存储在哪里？如何备份？

A: 数据库存储在系统应用数据目录的 `account_pool.db` 文件中：
- Linux: `~/.local/share/com.accountpool.gui/account_pool.db`
- Windows: `%APPDATA%/com.accountpool.gui/account_pool.db`

直接复制这个文件即可备份。

### Q: 密码在哪里存储？

A: **密码不存储**。根据设计，账号池只存储邮箱，密码与邮箱相同，使用时用户自行知晓。这样设计是为了安全，即使数据库泄露也不会暴露密码。

### Q: 如何重置所有账号状态？

A: 点击"检查重置"按钮，系统会：
1. 根据当前时间重置配额（跨天重置日配额，周六同时重置周配额）
2. 批量刷新所有有 apiKey 的账号额度
3. 显示刷新结果（成功/失败数量）

### Q: 额度信息是怎么获取的？

A: 登录成功后，后台自动：
1. 用 token 调用 Codeium 注册接口获取 apiKey
2. 用 apiKey 调用 `GetUserStatus` 获取 plan / 日额度 / 周额度
3. 存入数据库，额度 ≤ 0 自动标记耗尽

之后可随时点 ⟳ 按钮手动刷新。

### Q: 旧数据库升级后报错 "no such column: api_key"？

A: v0.1.0+ 已内置自动迁移，启动时检测缺失列并自动添加。如仍报错，请确认使用的是最新版本。

### Q: 登录失败怎么办？

A: 系统自动尝试 Auth1 → Firebase 双通道。如均失败，可点 CLI 按钮使用 Python 脚本备选登录。

CLI 脚本需放在数据目录下（如 Linux: `~/.local/share/com.accountpool.gui/switch_windsurf_account.py`），以 `--login-only --open` 模式运行，仅做登录+打开URI，快速响应。

### Q: 网络请求失败（额度刷新/登录报错）？

A: 系统自动检测 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量，代理不可达时直连。如需代理访问 Google API，确保：
1. 代理服务已启动
2. 环境变量已设置（`export HTTPS_PROXY=http://127.0.0.1:7897`）
3. 从终端启动应用以继承环境变量（`npm run tauri dev`）

## 许可证

MIT
