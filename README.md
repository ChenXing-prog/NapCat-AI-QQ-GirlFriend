<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python">
  <img src="https://img.shields.io/badge/LLM-Kimi%20k2.6-purple?style=for-the-badge">
  <img src="https://img.shields.io/badge/QQ-NapCatQQ%20v4-green?style=for-the-badge">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge">
</p>

<h1 align="center">💕 QQ AI 女友机器人</h1>
<h3 align="center">基于 Kimi k2.6 + NapCatQQ v4 的智能女友聊天机器人</h3>

<p align="center">
  <b>6 种学生人设 · 30 分类表情包 · 自适应消息缓冲 · 情绪感知 · 主动关心</b>
</p>

---

## 项目简介

一个运行在 QQ 上的 AI 女友聊天机器人。她会**主动关心你**、**记得你说过的话**、**感知你的情绪**、在恰当的时机**自然发表情包**。

> 用户只需添加 QQ 好友即可使用，无需下载 App。

---

## 核心特性

### 🎭 6 种学生人设

所有人设统一为学生身份，有真实的背景故事、性格矛盾、个人底线。

| # | 人设 | 名字 | 身份 | 风格 |
|---|------|------|------|------|
| 1 | 温柔女友 | 洛琪希 | 大三设计系 | 温暖有主见，不是烂好人 |
| 2 | 傲娇青梅 | 洛琪希 | 大二计算机系 | 嘴硬心软，在做独立游戏 |
| 3 | 元气学妹 | 洛琪希 | 大一新生 | 高能量但会考试焦虑 |
| 4 | 御姐前辈 | 洛琪希 | 大四实验室 | 成熟但赶论文会暴躁 |
| 5 | 二次元同好 | 洛琪希 | 大三 | Steam 300+ 游戏，社恐但对线不怂 |
| 6 | 码农女友 | 洛琪希 | 大三计算机系 | 社恐但会帮你 debug，养了只仓鼠叫 Null |

聊天中说 **「换人设」** 即可切换。

### 🖼️ 30 分类智能表情包

- LLM 从 30 种情绪分类中自动选择，支持末尾/中间/纯图三种位置
- **洗牌队列**：同分类内轮流使用，不会连续重复
- **降级机制**：LLM 选了空分类时自动换相似标签（pat→hug, caring→love 等）
- **标签别名**：LLM 输出 [heart] 自动映射到 [love]，[happy]→[smile] 等 39 个别名
- **catch-all 清理**：LLM 自我发明的标签（[coffee][爱][◍•ᴗ•◍]）自动剥离，不会出现在文本里
- **用户拉黑**：说「不喜欢这个表情包」即永久拉黑该图
- **管理员添加**：发图给 Bot，Kimi Vision 自动识别分类入库

### 💬 自适应消息缓冲

多条短消息自动合并为一次回复，等你说完再回应。

```
msg1 "今天" → msg2 "好累" → msg3 "不想说话"
        ↓ 等待 N 秒（自适应）
    合并为一条："今天\n好累\n不想说话" → LLM 一次回复
```

- 默认等待 10s，根据你的历史打字速度动态调整（1.5× 缓冲余量）
- **倾诉模式**：单独发 `/` 进入，再发 `/` 结束，中间所有消息合并
- 指令（换人设、拉黑表情包等）立即响应，不走缓冲

### 🧠 情绪感知引擎

18 种情绪维度（7 种宅男专属：游戏破防、社恐发作、二次元感动...），关键词 + LLM 混合检测，情绪轨迹追踪。

### 📅 主动联系调度

早安/晚安问候、静默检测、事件回访。三种黏人度：黏人/正常/佛系。

### 🔥 反迎合设计

她不是你的镜子。有自己的口味、观点、心情。可以不同意你、调侃你、偶尔不想说话。像真人一样有情绪波动。

---

## 系统架构

```
┌──────────┐      ┌──────────────┐      ┌─────────────────────┐
│  QQ 客户端 │ ←──→ │  NapCatQQ v4 │ ←──→ │   Python FastAPI    │
│ (用户手机) │      │  (协议桥接)   │      │   (gf/main.py)      │
└──────────┘      └──────────────┘      └──────────┬──────────┘
                                                    │
          ┌─────────────────────────────────────────┼───────────────────┐
          │                                         │                   │
    ┌─────▼──────┐   ┌──────────────┐   ┌──────────▼─────┐   ┌───────▼──────┐
    │ Kimi k2.6  │   │  表情包引擎    │   │   用户记忆系统   │   │  定时调度器   │
    │ (文本+视觉) │   │ 30分类+洗牌+  │   │  JSON 持久化    │   │ 早安/晚安/   │
    │            │   │ 降级+别名+清理 │   │ +自适应打字间隔 │   │ 静默检测     │
    └────────────┘   └──────────────┘   └────────────────┘   └──────────────┘
```

### 消息处理流程

```
用户发消息 → WS 事件 → handle_private_message()
  ├─ 指令检测（换人设/拉黑表情包/倾诉模式/管理员命令）
  ├─ 自适应缓冲（N秒内连续消息合并）
  ├─ 情绪分析（18维度关键词检测）
  ├─ 事件提取（LLM 异步）
  ├─ 加载用户记忆 + 选择人设
  ├─ 构建反迎合 System Prompt
  ├─ LLM chat_multi() → 拆分为 MessagePart 列表
  │    ├─ text          → 纯文字
  │    ├─ sticker_mid   → 先图后文
  │    ├─ sticker_end   → 先文后图
  │    └─ sticker_only  → 纯图（强情绪）
  ├─ catch-all 清理残留 []
  └─ 逐条发送（0.8-2.5s间隔）+ 表情包洗牌选图
```

---

## 目录结构

```
.
├── gf/                          # 后端代码
│   ├── main.py                  # 主入口（FastAPI + 消息处理 + 缓冲）
│   ├── config.py                # 配置管理
│   ├── scheduler.py             # 主动联系调度器
│   ├── ai/
│   │   ├── llm.py               # LLM 客户端（Kimi, 标签解析+别名+清理）
│   │   ├── persona.py           # 系统 Prompt 构建器（反迎合版）
│   │   ├── personas.py          # 6 种人设定义（学生身份+心理深度）
│   │   ├── emotion.py           # 18 维度情绪感知引擎
│   │   ├── events.py            # 事件提取与回访
│   │   └── sticker_meta.py      # 表情包元数据（动态加载 30 分类）
│   ├── bot/
│   │   ├── adapter.py           # NapCatQQ WebSocket 适配器
│   │   ├── client.py            # NapCatQQ v4 HTTP 客户端
│   │   └── test_napcat.py       # 连接测试工具
│   ├── memory/
│   │   └── store.py             # JSON 用户记忆（含打字间隔记录）
│   └── stickers/
│       └── engine.py            # 表情包引擎（洗牌队列+降级+黑名单）
├── stickers/                    # 30 个表情包分类文件夹
│   ├── cute/ (66张)  pout/ (12张)  shy/ (10张)  sleepy/ (11张)
│   ├── speechless/ (12张)  cry/ (6张)  questioning/ (5张)
│   └── ... 共 19 个有图分类 + 11 个待补充
├── scripts/
│   ├── classify_stickers.py     # Kimi Vision 自动分类脚本（断点续传）
│   ├── setup_sticker_categories.py  # 创建 30 分类目录
│   ├── rename_stickers.py       # 批量重命名编号
│   └── restore_duplicates.py    # 恢复去重图片
├── docs/
│   └── sticker-classification.md  # 表情包分类详细需求文档
├── docker-compose.yml           # NapCatQQ Docker 部署
└── SETUP.md                     # 快速部署指南
```

---

## 快速开始

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
LLM_PROVIDER=kimi
LLM_API_KEY=sk-your-key-here
LLM_MODEL=kimi-k2.6
LLM_VISION_MODEL=moonshot-v1-8k-vision-preview
LLM_TEMPERATURE=1.0

BOT_QQ=你的QQ号
BOT_NAME=洛琪希
ADMIN_QQ=你的QQ号

NAPCAT_BASE_URL=http://127.0.0.1:3000
NAPCAT_WS_URL=ws://127.0.0.1:3001

STICKER_FREQUENCY=0.4
SCHEDULER_ENABLED=true
DEFAULT_CLINGINESS=normal
```

### 2. 安装依赖

```bash
pip install -r gf/requirements.txt
```

### 3. 准备表情包

```bash
python scripts/setup_sticker_categories.py

# [可选] 用 Kimi Vision 自动分类图片
# 1. 把图片放到 data/images/
# 2. 配置 scripts/.env 中的 MOONSHOT_API_KEY
python scripts/classify_stickers.py
```

### 4. 安装 NapCatQQ

```bash
# Linux 一键安装
curl -fsSL https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh | bash -s -- --cli

# 或 Docker
docker compose up -d
# 打开 http://localhost:6099 扫码登录 QQ
```

### 5. 启动 Bot

```bash
cd gf
python -m gf.main
```

---

## 表情包系统

### 30 分类标签

| 系列 | 标签 | 数量 |
|------|------|------|
| 喜悦 | `laugh` `smile` `smirk` `star_eyes` `satisfied` `excited` | 6 种 |
| 撒娇 | `shy` `cute` `clingy` `begging` `pout` | 5 种 |
| 傲娇 | `tsundere` `eye_roll` `speechless` `questioning` `sigh` | 5 种 |
| 关心 | `caring` `pat` `hug` `love` | 4 种 |
| 难过 | `cry` `teary` `heartbroken` `corner` | 4 种 |
| 吃惊 | `shocked` `panic` | 2 种 |
| 整活 | `peek` `proud` `sleepy` `rage` | 4 种 |

### 位置标签

```
[hug]          → 消息末尾贴图
[S-MID:cute]   → 两条消息中间
[S-ONLY:cry]   → 纯图，不发文字
```

### 用户指令

| 指令 | 效果 |
|------|------|
| `不喜欢这个` `换一个` | 拉黑刚才发的表情包 |
| `分类到 {tag}` (发图后) | 管理员添加表情包，Kimi Vision 自动分类 |

---

## 💬 对话示例

```
👤 我今天好累
🤖 哎呀，宝宝辛苦了～ ||| 我也是，今天设计课的作业做到现在。 ||| 要不你先躺一会儿？[hug]
     → 📎 随机发一张 hug 表情包

👤 /
  [进入倾诉模式]
👤 今天被老板骂了
👤 回家路上又下雨
👤 感觉好倒霉
👤 /
  [退出倾诉模式]
🤖 听起来今天真的很糟... ||| 来，抱一个 [hug] ||| 明天会更好的，我陪你(｡･ω･｡)
```

---

## 配置参考

全部配置通过 `.env` 环境变量管理，详见 `gf/.env.example`。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL` | kimi-k2.6 | LLM 模型 |
| `LLM_TEMPERATURE` | 1.0 | k2.6 固定为 1 |
| `BOT_NAME` | 洛琪希 | Bot 名字 |
| `STICKER_FREQUENCY` | 0.4 | 表情包发送概率 |
| `ADMIN_QQ` | (空) | 管理员 QQ |
| `SCHEDULER_ENABLED` | true | 主动联系 |
| `DEFAULT_CLINGINESS` | normal | 黏人度 |

---

## 许可证

MIT License

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/ChenXing-prog">ChenXing-prog</a></sub>
</p>
