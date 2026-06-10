<h1 align="center">二次元 AI 女友 — 项目详解</h1>

> 一份会聊天、会发表情包、有记忆、有人设的 QQ 机器人。  
> 5,586 行 Python，23 个模块，6 个人设，30 种情绪表情包。

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [消息处理流程](#3-消息处理流程)
4. [人设系统](#4-人设系统)
5. [表情包系统](#5-表情包系统)
6. [记忆系统](#6-记忆系统)
7. [情绪感知](#7-情绪感知)
8. [自适应消息缓冲](#8-自适应消息缓冲)
9. [倾诉模式](#9-倾诉模式)
10. [主动联系调度](#10-主动联系调度)
11. [事件提取与回访](#11-事件提取与回访)
12. [配置参考](#12-配置参考)
13. [部署指南](#13-部署指南)
14. [目录结构](#14-目录结构)
15. [开发原则](#15-开发原则)

---

## 1. 项目概述

### 一句话

加个 QQ 好友，你就有了一个**会聊天、会发表情包、会记住你说过的话**的二次元 AI 女友。

### 核心特性

- 🎭 **6 种人设**可切换，学生身份，有真实背景故事和性格矛盾
- 🖼️ **30 种情绪表情包**，LLM 智能选图，支持位置控制
- 💬 **真人感聊天**，多消息逐条发送，自适应合并
- 🧠 **三层记忆**：工作记忆 + 核心事实 + 对话摘要
- 🔥 **反迎合人格**，有自己的情绪、口味、底线
- 📅 **主动关心**，早安晚安 + 静默检测 + 日常分享
- 🎨 **Kimi Vision 自动分类**，发图自动识别情绪入库

### 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ | 类型安全，异步支持 |
| LLM 文本 | Kimi k2.6 | 100 万上下文，temperature=1 |
| LLM 视觉 | moonshot-v1-8k-vision-preview | 表情包自动分类 |
| QQ 协议 | NapCatQQ v4 | HTTP API + WebSocket |
| Web | FastAPI + Uvicorn | 异步 Web 服务 |
| 存储 | JSON 文件 | 每用户独立，轻量零依赖 |
| 部署 | Systemd | 崩溃自动拉起 |

---

## 2. 系统架构

```
┌──────────┐      ┌──────────────┐      ┌─────────────────────┐
│  QQ 客户端 │ ←──→ │  NapCatQQ v4 │ ←──→ │   Python FastAPI    │
│ (用户手机) │      │  (协议桥接)   │      │   (gf/main.py)      │
└──────────┘      └──────────────┘      └──────────┬──────────┘
                                                    │
          ┌─────────────────────────────────────────┼───────────────────┐
          │                                         │                   │
    ┌─────▼──────┐   ┌──────────────┐   ┌──────────▼─────┐   ┌───────▼──────┐
    │ Kimi k2.6  │   │  表情包引擎    │   │   三层记忆系统   │   │  定时调度器   │
    │            │   │ 30分类+洗牌+  │   │ working+facts+  │   │ 早安/晚安/   │
    │ 文本+视觉   │   │ 降级+别名+清理 │   │ summaries      │   │ 静默/分享    │
    └─────┬──────┘   └──────────────┘   └────────────────┘   └──────────────┘
          │
    ┌─────▼──────────────────────────────────────────────┐
    │                    gf/ai/                           │
    │  persona.py   — System Prompt (反迎合 + 自我表露)    │
    │  personas.py  — 6 个人设定义 (学生+心理深度)         │
    │  emotion.py   — 18 维情绪感知 (7 种宅男专属)         │
    │  events.py    — LLM 事件提取 + 回访时机计算           │
    │  memory.py    — 事实提取 + 对话摘要                  │
    │  llm.py       — LLM 客户端 (标签解析+别名+清理)       │
    └────────────────────────────────────────────────────┘
```

---

## 3. 消息处理流程

```
QQ 消息 → WebSocket 事件
  │
  ├─ 是指令？─────────────────→ handlers/commands.py 处理 → 立即回复
  │   (换人设 / 拉黑表情包 / 管理员命令)
  │
  ├─ 是倾诉模式 "/"？─────────→ handlers/buffer.py 收集 → 等第二个 "/"
  │                                                → 专用 prompt → 长回复
  │
  └─ 普通消息 ────────────────→ handlers/buffer.py 缓冲
        │                       ├─ 记录打字间隔 (自适应算法)
        │                       ├─ 等待 N 秒 (根据用户历史动态计算)
        │                       └─ 超时 → 合并为一条
        │
        ▼
  _real_handle_message()
        │
        ├─ 1. 加载用户记忆 (facts + summaries)
        ├─ 2. 情绪分析 (18 维关键词检测)
        ├─ 3. 构建 System Prompt (人设 + 情绪 + 记忆)
        ├─ 4. LLM chat_multi() → 拆分为 MessagePart
        │      ├─ text          → 纯文字
        │      ├─ sticker_mid   → 先图后文
        │      ├─ sticker_end   → 先文后图
        │      └─ sticker_only  → 纯图
        ├─ 5. catch-all 清理残留 []
        ├─ 6. 逐条发送 (0.8-2.5s 人类感间隔)
        └─ 7. 后台触发 memory extraction + event extraction
```

---

## 4. 人设系统

### 设计理念

每个人设不只是「形容词的堆砌」，而是有**心理深度**的完整角色。

每个 Persona 包含：
- **基础身份**：名字、年龄、专业
- **深层心理**：最深渴望 (deepest_want)、核心恐惧 (core_fear)
- **矛盾** (contradictions)：让她立体的对立特质
- **背景故事** (backstory)：具体的生活细节
- **个人底线** (boundaries)：讨厌什么、什么会让她不舒服
- **反应规则** (reaction_rules)：特定场景下的行为模式
- **情绪范围** (mood_range)：不是永远同一个状态
- **日常话题** (daily_topics)：主动分享的生活片段

### 六种人设

| # | ID | 名字 | 身份 | 核心特质 |
|---|-----|------|------|---------|
| 1 | `gentle` | 温柔女友 | 大三设计系 | 温暖有主见，讨厌被当成情绪垃圾桶 |
| 2 | `tsundere` | 傲娇青梅 | 大二计算机系 | 嘴上嫌弃行动关心，在做独立游戏 |
| 3 | `genki` | 元气学妹 | 大一新生 | 高能量但会考试焦虑，需要被当成大人 |
| 4 | `oneesan` | 御姐前辈 | 大四实验室 | 成熟理性但赶论文会暴躁，偶尔调戏你 |
| 5 | `otaku` | 二次元同好 | 大三 | Steam 300+ 游戏，社恐但对线不怂 |
| 6 | `coder` | 码农女友 | 大三计算机系 | 社恐但会帮你 debug，养仓鼠叫 Null |

### 切换方式

聊天中说「换人设」即可，Bot 会列出选项。也可以直接说「我要傲娇青梅」。

### 代码位置

`gf/ai/personas.py` — Persona 类定义 + PERSONAS 字典
`gf/ai/persona.py` — System Prompt 构建器

---

## 5. 表情包系统

### 架构

```
LLM 输出标签 → chat_multi() 解析 → StickerEngine 选图 → QQClient 发图
                    │                      │
              ┌─────┴──────┐        ┌──────┴──────┐
              │ 正则匹配     │        │ 洗牌队列     │
              │ 别名归一化   │        │ 降级映射     │
              │ catch-all   │        │ 黑名单过滤   │
              └────────────┘        └─────────────┘
```

### 标签格式

| 格式 | 行为 | 示例 |
|------|------|------|
| `[love]` 或 `[S:love]` | 消息末尾贴图 | `最喜欢你了 [love]` |
| `[S-MID:star_eyes]` | 两条文字之间 | `[S-MID:star_eyes] 太厉害了！` |
| `[S-ONLY:cry]` | 纯图，不发文字 | 超难过或超开心时 |

### 智能处理

**别名映射**：LLM 说 `[heart]` → 自动转 `[love]`，`[happy]` → `[smile]`。39 个别名覆盖常见 LLM 说法。

**catch-all 清理**：LLM 发明的 `[咖啡]` `[◍•ᴗ•◍]` 等非标准标签，自动剥离不显示为文字。

**降级机制**：LLM 选了空分类（如 `pat` 无图）→ 自动换相似标签（`hug` → `cute` → `shy`）。

**洗牌队列**：每个分类内部打乱顺序循环使用，同一张图不会连续出现两次。

### 表情包管理

| 操作 | 方式 | 权限 |
|------|------|------|
| 添加 | 发图片给 Bot，Kimi Vision 自动识别情绪并分类入库 | 管理员 |
| 拉黑 | 说「不喜欢这个」「换一个」，永久对该用户生效 | 任何人 |
| 查看 | 说「表情包分类」或「表情包统计」 | 管理员 |
| 删除 | 说「删除表情包」 | 管理员 |

### 代码位置

`gf/stickers/engine.py` — 引擎（洗牌 + 降级 + 黑名单）
`gf/ai/llm.py` — 标签解析（别名 + catch-all）
`gf/ai/sticker_meta.py` — 动态加载 stickers/*/meta.json

---

## 6. 记忆系统

### 三层架构

```
用户消息 → 流水记录 → 后台触发

Layer 1: Working Memory (实时)
  └─ 最近 20 条对话，每次 LLM 请求注入
  └─ 实现：recent_messages list

Layer 2: Core Facts (每 ~25 条触发)
  └─ LLM 提取关键信息：喜好、经历、健康、人际关系
  └─ 存储：{category, content, importance, created_at, last_accessed, access_count}
  └─ 检索：importance × recency × access_count 排序，取 top 12

Layer 3: Summaries (每 ~30 条触发)
  └─ LLM 压缩对话批次为摘要
  └─ 存储：{date_range, summary, key_topics, message_count}
  └─ 检索：取最近 3 批；超过 10 批自动二次压缩
```

### 存储

每个用户的记忆独立存储为 JSON 文件：`data/users/{QQ号}.json`

每用户约 20-30KB，5000 用户约 150MB。零外部依赖。

### 代码位置

`gf/memory/store.py` — UserProfile 定义 + CRUD 方法
`gf/ai/memory.py` — FactExtractor + SummaryCompressor（LLM 提取）

---

## 7. 情绪感知

### 18 种情绪维度

| 类别 | 情绪 |
|------|------|
| 通用 | 😊 开心 · 😢 难过 · 😡 生气 · 😰 焦虑 · 😴 疲惫 · 😐 无聊 · 😢 孤独 |
| 游戏 | 🎮 破防 · 高光 · 肝 |
| 二次元 | 📺 感动 · 兴奋 |
| 社交 | 🏠 社恐 · 宅家舒适 · 自我怀疑 |
| 其他 | 感动 · 自豪 · 松了口气 |

### 检测方式

**关键词匹配**（快速，零成本）→ 命中 → 直接返回结果
**情绪轨迹**（5 条滑动窗口）→ 判断趋势（好转/恶化/稳定/波动）

### 响应策略

每种情绪有对应的回复策略：
- **语气调整**：伤心时更温柔，生气时先认同感受
- **推荐表情包**：伤心 → [caring]、生气 → [caring]（降级后为 [hug]）
- **避开话题**：社恐时不说「多出门」，自我怀疑时不说「你应该…」

### 代码位置

`gf/ai/emotion.py` — 18 维情绪引擎 + 轨迹追踪

---

## 8. 自适应消息缓冲

### 问题

用户常连续发多条短消息，每条都回复很不自然。

### 方案

**缓冲 + 自适应定时器**：每条消息先放进缓冲区，等待一段时间。期间有新消息就重置定时器。定时器超时后合并所有消息一次发送。

### 自适应算法

```
wait = 0.7 × 当前对话间隔平均 + 0.3 × 历史间隔平均
wait = wait × 1.5 (缓冲余量)
wait = clamp(wait, 3s, 20s)
```

- 新用户默认 10 秒
- 记录最近 50 条历史间隔 + 10 条当前会话间隔
- 超过 5 分钟不说话 → 重置当前会话统计

### 代码位置

`gf/handlers/buffer.py` — 缓冲逻辑 + 自适应算法

---

## 9. 倾诉模式

### 用法

单独发 `/` 进入倾诉模式，再发 `/` 结束。

```
👤 /
👤 今天发生了好多事
👤 被老师骂了
👤 考试也没考好
👤 /
🤖 （读完全部内容后的 1-2 段认真回复，带 1-2 个表情包）
```

### 与普通聊天的区别

| | 普通聊天 | 倾诉模式 |
|---|---------|---------|
| 回复条数 | 2-4 条短消息 | 1-2 条长消息 |
| 语气 | 日常轻快 | 认真读完再回应 |
| 表情包 | 0-2 个 | 1-2 个 |
| 性格 | 正常女友模式 | 仍然是女友，但更专注 |

### 代码位置

`gf/handlers/buffer.py` — confide_start/confide_end/confide_collect
`gf/ai/persona.py` — build_confide_prompt()

---

## 10. 主动联系调度

### 定时触发

- **早安**：每天 7:00-10:00 随机时间（±15 分钟抖动）
- **晚安**：每天 21:00-0:00 随机时间
- **静默检测**：用户 N 小时不说话 → 主动关心

### 黏人度

| 等级 | 静默阈值 | 每日上限 |
|------|---------|---------|
| 黏人 | 2h | 5 条 |
| 正常 | 5h | 3 条 |
| 佛系 | 8h | 1 条 |

新用户默认「正常」，可通过对话调整。

### 日常分享（规划中）

每个人设有独立的话题池，随机在活跃时段触发 1-2 次/天。

### 代码位置

`gf/scheduler.py` — ProactiveScheduler

---

## 11. 事件提取与回访

LLM 从对话中提取值得记住的事件：考试、面试、生病、旅行、新游戏...

根据事件类型自动设置回访时间：
- 考试/面试 → 24h 后问
- 生病 → 6h 后关心
- 旅行 → 一周后问

到期时自动注入 System Prompt：「你之前知道对方有考试，可以问一下怎么样了」。

### 代码位置

`gf/ai/events.py` — EventExtractor + 回访上下文构建

---

## 12. 配置参考

关键环境变量（`.env`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL` | kimi-k2.6 | 文本模型 |
| `LLM_VISION_MODEL` | moonshot-v1-8k-vision-preview | 视觉模型（表情包分类） |
| `LLM_TEMPERATURE` | 1.0 | k2.6 固定为 1 |
| `LLM_MAX_TOKENS` | 4096 | 最大输出 token |
| `BOT_NAME` | 洛琪希 | Bot 显示名 |
| `BOT_QQ` | — | Bot 的 QQ 号 |
| `ADMIN_QQ` | — | 管理员 QQ（可管理表情包） |
| `STICKER_FREQUENCY` | 0.4 | 全局表情包概率 |
| `SCHEDULER_ENABLED` | true | 主动联系开关 |
| `DEFAULT_CLINGINESS` | normal | 默认黏人度 |
| `NAPCAT_BASE_URL` | http://127.0.0.1:3000 | NapCatQQ 地址 |
| `DATA_DIR` | ./data | 用户数据存储目录 |
| `STICKERS_DIR` | ./stickers | 表情包目录 |

---

## 13. 部署指南

### 前置条件

- Python 3.11+
- Kimi API Key ([platform.moonshot.cn](https://platform.moonshot.cn))
- QQ 号（建议用小号）

### 快速部署

```bash
# 1. 克隆
git clone https://github.com/ChenXing-prog/NapCat-AI-QQ-Girlfriend.git
cd NapCat-AI-QQ-Girlfriend

# 2. 配置
cd gf && cp .env.example .env
# 编辑 .env：填 LLM_API_KEY、BOT_QQ

# 3. 安装
pip install -r requirements.txt

# 4. 表情包
python scripts/setup_sticker_categories.py
# (可选) 把图片放 data/images/ 后：
python scripts/classify_stickers.py

# 5. 安装 NapCatQQ
curl -fsSL https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh | bash -s -- --cli

# 6. 启动
python -m gf.main
```

### Systemd 服务

```ini
[Unit]
Description=AI Girlfriend QQ Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/aigf
ExecStart=/usr/bin/python3 -m gf.main
Restart=no

[Install]
WantedBy=multi-user.target
```

---

## 14. 目录结构

```
NapCat-AI-QQ-Girlfriend/
├── gf/                              # 后端核心
│   ├── main.py                      # 主入口 (350行, 协调层)
│   ├── config.py                    # 配置管理
│   ├── scheduler.py                 # 主动联系调度
│   ├── handlers/
│   │   ├── commands.py              # 聊天指令 (人设切换/表情包管理)
│   │   └── buffer.py                # 消息缓冲 (自适应算法)
│   ├── ai/
│   │   ├── llm.py                   # LLM 客户端 (标签解析+别名+清理)
│   │   ├── persona.py               # System Prompt (反迎合+自我表露)
│   │   ├── personas.py              # 6 个人设定义 (学生+心理深度)
│   │   ├── emotion.py               # 18 维情绪引擎+轨迹
│   │   ├── events.py                # 事件提取+回访
│   │   ├── memory.py                # 事实提取+对话摘要
│   │   └── sticker_meta.py          # 表情包元数据 (动态加载30分类)
│   ├── bot/
│   │   ├── adapter.py               # WebSocket 适配器
│   │   └── client.py                # HTTP 客户端
│   ├── memory/
│   │   └── store.py                 # JSON 用户存储 (含三层记忆)
│   └── stickers/
│       └── engine.py                # 洗牌队列+降级+黑名单
├── stickers/                        # 30 个分类文件夹 + meta.json
├── scripts/                         # 表情包分类/管理脚本
│   ├── classify_stickers.py         # Kimi Vision 自动分类 (断点续传)
│   ├── setup_sticker_categories.py  # 创建30分类目录
│   ├── rename_stickers.py           # 批量重命名编号
│   └── restore_duplicates.py        # 恢复去重图片
├── docs/
│   ├── PROJECT.md                   # 本文件 - 项目详解
│   ├── promo.md                     # 宣传介绍
│   └── sticker-classification.md    # 表情包分类详细需求
├── docker-compose.yml               # Docker 部署
├── SETUP.md                         # 部署指南
└── README.md                        # 项目首页
```

## 15. 开发原则

本项目遵循以下原则：

- **OCP**（开闭原则）：命令、缓冲、记忆等独立关注点拆分到 handlers/ 和 ai/，修改一个模块不影响其他
- **轻量**：零数据库依赖，JSON 文件存储，5 分钟部署
- **异步优先**：所有 I/O 操作异步，后台任务 fire-and-forget
- **用户隔离**：每个用户独立 JSON 文件，互不干扰
