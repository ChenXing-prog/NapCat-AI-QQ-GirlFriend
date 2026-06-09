<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/LLM-Kimi%20Moonshot-purple?style=for-the-badge" alt="Kimi">
  <img src="https://img.shields.io/badge/QQ-NapCatQQ%20v4-green?style=for-the-badge" alt="NapCatQQ">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License">
</p>

<h1 align="center">💕 QQ AI 女友机器人</h1>
<h3 align="center">基于 Kimi 大模型 + NapCatQQ 的智能女友聊天机器人</h3>

<p align="center">
  <b>温柔体贴 · 主动关心 · 情绪感知 · 表情包大师 · 多角色人设</b>
</p>

---

## 📖 项目简介

一个运行在 QQ 上的 AI 女友聊天机器人。她不是冷冰冰的客服，而是会**主动关心你**、**记得你说过的话**、**感知你的情绪**、**在恰当的时机发表情包**的虚拟恋人。

> 用户只需添加 QQ 好友即可使用，无需下载 App。

### 🌟 核心特色

<table>
<tr>
  <td width="50%">

  **🧠 情绪感知引擎**
  
  18 种情绪维度（7 种宅男专属：游戏破防、社恐发作、二次元感动...），
  关键词 + LLM 混合检测，情绪轨迹追踪。

  </td>
  <td width="50%">

  **🎭 5 种人设自由切换**
  
  | 温柔女友 | 傲娇青梅 | 元气学妹 | 御姐前辈 | 二次元同好 |
  
  每种人设有独立的性格、说话风格、颜文字偏好、表情包权重。

  </td>
</tr>
<tr>
  <td>

  **💬 多消息逐条发送**
  
  像真人一样拆成 2-4 条短消息逐条发送，间隔随机，附带思考延迟。

  </td>
  <td>

  **🖼️ 30 分类智能表情包**
  
  LLM 根据情绪从 30 种分类中自动选择，支持末尾/中间/纯图三种位置，0-2 张/轮。

  </td>
</tr>
<tr>
  <td>

  **📅 主动联系调度**
  
  早安/晚安问候、静默检测、事件回访。三种黏人度：黏人/正常/佛系。

  </td>
  <td>

  **🧹 表情包管理**
  
  用户聊天指令拉黑不喜欢的图；管理员发图自动 Kimi Vision 识别分类入库。

  </td>
</tr>
</table>

---

## 🏗️ 系统架构

```
┌──────────┐      ┌──────────────┐      ┌─────────────────────┐
│  QQ 客户端 │ ←──→ │  NapCatQQ v4 │ ←──→ │   Python FastAPI    │
│ (用户手机) │      │  (协议桥接)   │      │   (gf/main.py)      │
└──────────┘      └──────────────┘      └──────────┬──────────┘
                                                    │
          ┌─────────────────────────────────────────┼───────────────────┐
          │                                         │                   │
    ┌─────▼──────┐   ┌──────────────┐   ┌──────────▼─────┐   ┌───────▼──────┐
    │  Kimi LLM  │   │  表情包引擎    │   │   用户记忆系统   │   │  定时调度器   │
    │ (文本+视觉) │   │ 30分类随机选图 │   │  JSON 持久化    │   │ 早安/晚安/   │
    └────────────┘   └──────────────┘   └────────────────┘   │ 静默检测     │
                                                             └──────────────┘
```

### 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Web 框架 | FastAPI + Uvicorn |
| LLM | **Kimi Moonshot** (moonshot-v1-8k + vision-preview) |
| QQ 协议 | **NapCatQQ v4** (HTTP API + WebSocket) |
| 部署 | Systemd 服务 / Docker Compose |
| 图片处理 | Pillow + imagehash (去重) + Kimi Vision (分类) |

### 消息处理流程

```
用户发消息 → NapCatQQ WS 推送 → handle_private_message()
  ├─ 情绪分析 (18维度关键词检测)
  ├─ 事件提取 (LLM 异步)
  ├─ 加载用户记忆 + 选择人设
  ├─ 构建 System Prompt (人设 + 30表情包指南 + 情绪上下文)
  ├─ LLM chat_multi() → 拆分为 MessagePart 列表
  │    ├─ text          → 纯文字
  │    ├─ sticker_mid   → 先图后文
  │    ├─ sticker_end   → 先文后图
  │    └─ sticker_only  → 纯图(强情绪)
  └─ 逐条发送 (0.8-2.5s间隔) + 表情包随机选图
```

---

## 📂 目录结构

```
.
├── gf/                          # 后端代码
│   ├── main.py                  # 主入口（FastAPI + 消息处理）
│   ├── config.py                # 配置管理
│   ├── scheduler.py             # 主动联系调度器
│   ├── ai/
│   │   ├── llm.py               # LLM 客户端 (Kimi, OpenAI 兼容)
│   │   ├── persona.py           # 系统 Prompt 构建器
│   │   ├── personas.py          # 5 种人设定义
│   │   ├── emotion.py           # 18 维度情绪感知引擎
│   │   ├── events.py            # 事件提取与回访
│   │   └── sticker_meta.py      # 表情包元数据 (动态加载)
│   ├── bot/
│   │   ├── adapter.py           # NapCatQQ WebSocket 适配器
│   │   ├── client.py            # NapCatQQ HTTP 客户端
│   │   └── test_napcat.py       # 连接测试工具
│   ├── memory/
│   │   └── store.py             # JSON 文件用户记忆存储
│   └── stickers/
│       └── engine.py            # 表情包引擎 (随机选图/黑名单)
├── stickers/                    # 30 个表情包分类文件夹
│   ├── cute/   (66 张)  smile/  (3 张)   shy/    (10 张)
│   ├── pout/   (12 张) sleepy/ (11 张)  cry/    (6 张)
│   └── ... 共 19 个有图分类 + 11 个待补充
├── scripts/
│   ├── classify_stickers.py     # Kimi Vision 自动分类脚本
│   ├── setup_sticker_categories.py  # 创建 30 分类目录
│   ├── rename_stickers.py       # 批量重命名编号
│   └── restore_duplicates.py    # 恢复去重图片
├── docs/
│   └── sticker-classification.md  # 表情包分类详细需求文档
├── docker-compose.yml           # NapCatQQ Docker 部署 (本地开发)
└── SETUP.md                     # 快速部署指南
```

---

## 🚀 快速开始

### 前提条件

- Python 3.11+
- NapCatQQ（QQ 协议桥接，需单独安装）
- Kimi API Key（[platform.moonshot.cn](https://platform.moonshot.cn)）

### 1. 配置

```bash
cd gf
cp .env.example .env
# 编辑 .env 填入你的配置
```

关键配置项：

```bash
# LLM API (Kimi)
LLM_API_KEY=sk-your-key-here
LLM_MODEL=moonshot-v1-8k
LLM_VISION_MODEL=moonshot-v1-8k-vision-preview

# QQ Bot
BOT_QQ=你的QQ号
BOT_NAME=小暖

# NapCatQQ 地址
NAPCAT_BASE_URL=http://127.0.0.1:3000
NAPCAT_WS_URL=ws://127.0.0.1:3001

# 管理员 QQ（可管理表情包）
ADMIN_QQ=你的QQ号

# 表情包频率 (0.0-1.0)
STICKER_FREQUENCY=0.4
```

### 2. 安装依赖

```bash
pip install -r gf/requirements.txt
```

### 3. 准备表情包

```bash
# 创建 30 个分类目录
python scripts/setup_sticker_categories.py

# [可选] 用 Kimi Vision 自动分类图片
# 1. 把图片放到 data/images/
# 2. 配置 scripts/.env 中的 MOONSHOT_API_KEY
python scripts/classify_stickers.py
```

### 4. 安装 NapCatQQ

**Docker (推荐)**：
```bash
docker compose up -d
# 打开 http://localhost:6099 扫码登录 QQ
```

**Linux 一键安装**：
```bash
curl -fsSL https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh | bash -s -- --cli
```

### 5. 启动 Bot

```bash
cd gf
python -m gf.main
```

---

## 🎭 人设系统

对话中说「**换人设**」即可切换。每个人设有独立的性格、说话风格和表情包偏好：

| # | 人设 | 名字 | 风格特点 | 常用颜文字 |
|---|------|------|---------|-----------|
| 1 | **温柔女友** | 小暖 | 体贴关心，让人安心 | `(｡･ω･｡)` `(◍•ᴗ•◍)` |
| 2 | **傲娇青梅** | 小傲 | 嘴硬心软，口是心非 | `(￣へ￣)` `(*/ω＼*)` |
| 3 | **元气学妹** | 小元 | 活泼崇拜，永远捧场 | `ヽ(≧∀≦)ﾉ` `(๑•̀ㅂ•́)و✧` |
| 4 | **御姐前辈** | 小雅 | 成熟优雅，偶尔调戏 | `(￣▽￣)~*` `(¬‿¬)` |
| 5 | **二次元同好** | 小宅 | 宅友灵魂伴侣，接所有梗 | `(´・ω・\`)` `(╯°□°)╯︵ ┻━┻` |

---

## 🖼️ 表情包系统

### 30 分类标签

| 系列 | 标签 | 说明 |
|------|------|------|
| 喜悦 | `laugh` `smile` `smirk` `star_eyes` `satisfied` `excited` | 6 种 |
| 撒娇 | `shy` `cute` `clingy` `begging` `pout` | 5 种 |
| 傲娇 | `tsundere` `eye_roll` `speechless` `questioning` `sigh` | 5 种 |
| 关心 | `caring` `pat` `hug` `love` | 4 种 |
| 难过 | `cry` `teary` `heartbroken` `corner` | 4 种 |
| 吃惊 | `shocked` `panic` | 2 种 |
| 整活 | `peek` `proud` `sleepy` `rage` | 4 种 |

### 位置感知格式

```
[S:love]       贴在这条消息末尾
[S-MID:cute]   贴在消息中间（两条文字之间）
[S-ONLY:cry]   纯图，不发文字（仅强情绪）
```

### 用户管理

| 指令 | 效果 |
|------|------|
| `换一个` `不喜欢这个` `不要发这个了` | 拉黑最近发的表情包 |
| `分类到 {tag}` (发送图片后) | 管理员添加表情包并自动分类 |

---

## 💬 对话示例

```
👤 我今天抽到限定SSR了！！
🤖 [star_eyes 表情包]
🤖 哇！！宝宝太厉害了吧！(｡･ω･｡)
🤖 什么角色呀快给我看看
🤖 我家宝宝运气也太好了 [proud 表情包]
```

```
👤 被老板骂了，好难过
🤖 啊呀，宝宝受委屈了🥺
🤖 快过来让我抱抱～
🤖 工作上不开心就别想啦，我给你充充电 💕 [hug 表情包]
```

---

## 📊 情绪引擎

18 种情绪维度，其中 **7 种宅男专属**：

| 类别 | 情绪 |
|------|------|
| 游戏 | 🎮 破防 `gaming_rage` · 高光 `gaming_hype` · 肝 `gaming_grind` |
| 二次元 | 📺 感动 `anime_feels` · 兴奋 `nerd_excited` |
| 社交 | 🏠 社恐 `social_anxiety` · 宅家舒适 `comfort_zone` |
| 通用 | 😊 开心 · 😢 难过 · 😡 生气 · 😰 焦虑 · 😴 疲惫 · 😐 无聊 · 😢 孤独 · ... |

每种情绪有对应的回复策略：语气调整 + 推荐表情包 + 避开话题。

---

## ⚙️ 配置说明

全部配置通过 `.env` 环境变量管理，详见 `gf/.env.example`。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | kimi | LLM 提供商 |
| `LLM_MODEL` | moonshot-v1-8k | 文本模型 |
| `LLM_VISION_MODEL` | moonshot-v1-8k-vision-preview | 视觉模型（表情包分类） |
| `BOT_NAME` | 小暖 | Bot 默认名字 |
| `STICKER_FREQUENCY` | 0.4 | 全局表情包发送概率 |
| `ADMIN_QQ` | (空) | 管理员 QQ，可添加/删除表情包 |
| `SCHEDULER_ENABLED` | true | 主动联系开关 |
| `DEFAULT_CLINGINESS` | normal | 默认黏人度 (clingy/normal/chill) |

---

## 📄 许可证

MIT License

---

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/ChenXing-prog">ChenXing-prog</a></sub>
</p>
