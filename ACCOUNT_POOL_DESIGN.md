# 账号池功能设计文档

## 概述

基于 Windsurf Usage 页面的配额机制，设计一个跨平台的账号池管理工具，帮助用户管理多个免费 Windsurf 账号，实现配额轮换使用。

## 核心机制（来自 Windsurf Usage 页面）

| 配额类型 | 重置时间 | 说明 |
|---------|---------|------|
| **每日配额** | 每天 16:00 GMT+8 | 日配额用完后，当日无法使用高级模型 |
| **每周配额** | 每周六 16:00 GMT+8 | 周配额与日配额独立，日配额用完周配额可能还有 |

## 数据模型

### 账号池文件：`data/account_pool.db`

使用 **SQLite** 数据库存储，包含三张表：

#### 1. `accounts` - 账号数据表

```sql
CREATE TABLE accounts (
    email TEXT PRIMARY KEY NOT NULL,
    status TEXT DEFAULT 'available',
    daily_exhausted INTEGER DEFAULT 0,
    weekly_exhausted INTEGER DEFAULT 0,
    last_used_at TEXT DEFAULT '',
    total_uses INTEGER DEFAULT 0,
    notes TEXT DEFAULT ''
);

-- 索引
CREATE INDEX idx_status ON accounts(status);
CREATE INDEX idx_daily ON accounts(daily_exhausted);
```

#### 2. `pool_config` - 配置表（单条记录）

```sql
CREATE TABLE pool_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    reset_timezone TEXT DEFAULT 'Asia/Shanghai',
    reset_hour INTEGER DEFAULT 16,
    strategy TEXT DEFAULT 'round_robin',
    version INTEGER DEFAULT 1
);
```

#### 3. `pool_state` - 运行状态表（单条记录）

```sql
CREATE TABLE pool_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_index INTEGER DEFAULT 0,
    last_reset_check TEXT DEFAULT ''
);
```

### 字段说明

| 字段 | 类型 | 说明 |
|-----|------|------|
| `config.reset_timezone` | string | 配额重置时区，固定为 `Asia/Shanghai` |
| `config.reset_hour` | int | 重置小时，固定为 16（北京时间下午4点）|
| `config.strategy` | string | 轮换策略：`round_robin`（依次轮换）|
| `state.next_index` | int | Round Robin 指针，下次取用的账号索引 |
| `state.last_reset_check` | date | 上次检查重置的日期 |
| `email` | string | 邮箱地址（密码与邮箱相同，不单独存储）|
| `status` | enum | `available`（可用）、`exhausted`（耗尽）|
| `daily_exhausted` | bool | 日配额是否耗尽 |
| `weekly_exhausted` | bool | 周配额是否耗尽 |
| `last_used_at` | datetime | 上次使用时间 |
| `total_uses` | int | 累计取用次数（用于统计）|
| `notes` | string | 用户备注 |

## 状态流转

```
                    ┌─────────────┐
    注册成功导入 ──▶  │  available  │
                    └──────┬──────┘
                           │ 取用
                           ▼
                    ┌─────────────┐
    标记日配额耗尽 ──▶│daily_exhausted=true│
                    └──────┬──────┘
                           │ 每日 16:00 重置
                           ▼
                    ┌─────────────┐
    标记周配额耗尽 ──▶│weekly_exhausted=true│
                    └──────┬──────┘
                           │ 每周六 16:00 重置
                           ▼
                    ┌─────────────┐
                           │  available  │
                           └─────────────┘
```

## 核心操作

### 1. 取用账号

**触发**：用户点击"取用账号"

**流程**：
1. 检查是否需要重置（对比当前时间与上次 `last_reset_check`）
2. 找到下一个 `available` 且非 `daily_exhausted` 的账号
3. 弹出窗口显示邮箱，提供"复制邮箱"按钮
4. 更新 `last_used_at`、`total_uses += 1`
5. `next_index` 移动到下一个

**弹窗内容**：
```
┌─ 取用账号 ──────────────────┐
│                              │
│ 邮箱: user123@d.com          │
│                              │
│ 密码与邮箱相同               │
│                              │
│ [复制邮箱] [标记日配额耗尽]  │
│                              │
└──────────────────────────────┘
```

### 2. 标记配额状态

**触发**：用户发现配额耗尽，点击标记

**操作**：
- **标记日配额耗尽**：设置 `daily_exhausted = true`
- **标记周配额耗尽**：设置 `weekly_exhausted = true`
- **取消标记**：恢复为 `false`，状态回到 `available`

### 3. 自动重置检查

**触发**：每次打开程序或点击"检查重置"

**逻辑**：
```python
def check_reset():
    now = datetime.now(tz=Asia/Shanghai)
    last_check = state.last_reset_check
    
    # 跨天检查：现在日期 > 上次检查日期
    if now.date() > last_check:
        # 每日配额重置
        for acc in accounts:
            acc.daily_exhausted = false
            if acc.weekly_exhausted and now.weekday() == 5:  # 周六
                acc.weekly_exhausted = false
            if not acc.weekly_exhausted:
                acc.status = "available"
        
        state.last_reset_check = now.date()
```

### 4. 批量导入

**来源**：从 `dist/exports/*.json` 导入

**流程**：
1. 选择 JSON 文件（邮箱数组格式）
2. 解析邮箱列表
3. 去重（已存在的跳过）
4. 新账号默认状态：`available`, `daily_exhausted=false`, `weekly_exhausted=false`

## GUI 设计

### 账号池 Tab 布局

```
┌─ 账号池管理 ──────────────────────────────────────────────────────┐
│                                                                   │
│  [导入账号] [取用账号] [检查重置]  策略: round_robin▼              │
│                                                                   │
│  统计: 总数 500 | 可用 380 | 日耗尽 85 | 周耗尽 30                │
│                                                                   │
│  下次日重置: 今天 16:00 (2小时15分后)                             │
│  下次周重置: 周六 16:00 (3天2小时后)                              │
│                                                                   │
│ ┌────┬─────────────────┬────────┬──────────┬──────────┬────────┐│
│ │ 选 │ 邮箱            │ 状态   │ 日配额   │ 周配额   │ 上次使用││
│ ├────┼─────────────────┼────────┼──────────┼──────────┼────────┤│
│ │ ☑  │ user1@d.com     │ 🟢可用  │ ✓ 有     │ ✓ 有     │ 15:30  ││
│ │ ☑  │ user2@d.com     │ 🟡日耗尽│ ✗ 无     │ ✓ 有     │ 14:20  ││
│ │ ☑  │ user3@d.com     │ 周耗尽│ ✓ 有     │ ✗ 无     │ 昨天   ││
│ └────┴─────────────────┴────────┴──────────┴──────────┴────────┘│
│                                                                   │
│  [标记日配额耗尽] [标记周配额耗尽] [取消标记] [删除]            │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### 状态图标

| 图标 | 含义 |
|-----|------|
| 🟢 | `available`，日配额和周配额都可用 |
| 🟡 | `daily_exhausted=true`，日配额用完，周配额还有 |
| 🟠 | `weekly_exhausted=true`，周配额用完 |

## 与现有系统集成

### 注册流程衔接

```
注册成功账号
    ↓
自动添加到账号池（status=available）
    ↓
保存到 account_pool.db
```

### 文件位置

| 文件 | 路径 | 说明 |
|-----|------|------|
| 账号池数据 | `data/account_pool.db` | SQLite 数据库 |
| 旧数据（迁移后删除） | `data/account_pool.json` | 旧版 JSON 文件（自动迁移到 SQLite 后删除） |
| 导入源 | `dist/exports/*.json` | 注册结果导出文件 |

## 技术实现要点

### 跨平台兼容性

- **Tkinter**：Python 标准库，Windows/Linux 都支持
- **时区处理**：使用 `pytz` 或 Python 3.9+ 的 `zoneinfo`
- **文件路径**：使用 `pathlib.Path`，自动处理 `/` 和 `\`

### 数据持久化

- **SQLite 数据库**：使用 `sqlite3` 标准库，无需额外依赖
- **自动迁移**：启动时自动检测并迁移旧版 `account_pool.json` 数据到 SQLite
- **事务保证**：关键操作使用事务，确保数据一致性
- **索引优化**：对 `status` 和 `daily_exhausted` 字段建立索引，提升查询效率

### 并发安全

- 单用户单实例，不需要复杂锁机制
- 简单的文件读写即可

## 使用流程示例

### 场景1：日常轮换使用

1. 打开程序，点击"账号池" Tab
2. 查看"可用"账号数量和下次重置倒计时
3. 点击"取用账号"，复制邮箱去 Windsurf IDE 登录
4. 使用一段时间后，发现日配额耗尽
5. 回到程序，点击"标记日配额耗尽"
6. 再次点击"取用账号"，获取下一个可用账号

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

## 未来扩展（暂不实现）

1. **使用阈值预估**：根据 `total_uses` 统计，预估每个账号平均使用几次后耗尽
2. **智能推荐**：优先推荐 `total_uses` 少的账号，实现负载均衡
3. **API 集成**：如果 Windsurf 开放配额查询 API，自动同步真实配额状态
4. **多平台支持**：macOS 打包
