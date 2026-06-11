<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python">
  <img src="https://img.shields.io/badge/LLM-Kimi%20k2.6-purple?style=for-the-badge">
  <img src="https://img.shields.io/badge/QQ-NapCatQQ%20v4-green?style=for-the-badge">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge">
</p>

<h1 align="center">二次元 AI 女友 机器人</h1>
<h3 align="center">基于 Kimi k2.6 + NapCatQQ v4，会发表情包的二次元女友 QQ 机器人</h3>

<p align="center">
  <b>🎭 6 种人设 · 🖼️ 30 分类表情包 · 🧠 六层上下文记忆 · 💬 自适应聊天 · 🔥 反迎合人格</b>
</p>

---

## ✨ 她是怎样的女友

她不是客服，不是 ChatGPT，她是一个**有性格的二次元女生**。

加了 QQ 好友就能聊天。会主动找你、会发表情包、会记住你说过的话。
心情好的时候元气满满，赶作业的时候也会暴躁。可以调侃你，也可以被你调侃。

---

## 🚀 5 分钟部署

### 1. 准备

```bash
git clone https://github.com/ChenXing-prog/NapCat-AI-QQ-GirlFriend.git
cd NapCat-AI-QQ-GirlFriend/gf
cp .env.example .env   # 填 Kimi API Key + QQ 号
pip install -r requirements.txt
```

### 2. 表情包

```bash
python scripts/setup_sticker_categories.py    # 建 30 个分类目录
# 把表情包图片放到 data/images/ 下
python scripts/classify_stickers.py           # Kimi Vision 自动分类
```

### 3. 启动 NapCatQQ + Bot

```bash
# 服务器上一键安装 NapCatQQ
curl -fsSL https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh | bash -s -- --cli

# 启动 Bot
python -m gf.main
```

扫码登录 QQ，开始聊天。

---

## 🖼️ 表情包系统（核心亮点）

### 智能选图

聊天时自动挑选合适的表情包——**不是随机发，而是根据情绪来**。

```text
你说 "抽到 SSR 了！！"
  → 她发 [star_eyes] 星星眼 + "哇宝宝太厉害了叭"

你说 "今天被老板骂了"
  → 她发 [hug] 抱抱 + "摸摸头，不气了 (´・ω・`)"
```

### 30 种情绪分类

| 系列 | 标签 |
|------|------|
| 😆 喜悦 | `laugh` `smile` `smirk` `star_eyes` `satisfied` `excited` |
| 🥺 撒娇 | `shy` `cute` `clingy` `begging` `pout` |
| 😤 傲娇 | `tsundere` `eye_roll` `speechless` `questioning` `sigh` |
| 💕 关心 | `caring` `pat` `hug` `love` |
| 😢 难过 | `cry` `teary` `heartbroken` `corner` |
| 😱 吃惊 | `shocked` `panic` |
| 😎 整活 | `peek` `proud` `sleepy` `rage` |

### 表情包可以出现在任何位置

```text
[S:smile]    → 消息末尾贴一张
[S-MID:shy]  → 两条消息之间贴一张
[S-ONLY:cry] → 只发图不说话（超难过/超开心的时候）
```

### 管理表情包超方便

| 操作 | 方式 |
|------|------|
| ➕ 添加表情包 | 发图给 Bot，Kimi Vision 自动识别情绪分类入库 |
| ❌ 拉黑 | 聊天里说「不喜欢这个」「换一个」即可，只对你生效 |
| 📊 查看 | 管理员说「表情包分类」「表情包统计」 |

---

## 🎭 六种人设

所有人设都是学生身份，有真实的背景故事和性格矛盾。

| # | 人设 | 身份 | 一句话 |
|---|------|------|--------|
| 1 | 温柔女友 | 大三设计系 | 温暖有主见，不是烂好人 |
| 2 | 傲娇青梅 | 大二计算机系 | 嘴硬心软，在做独立游戏 |
| 3 | 元气学妹 | 大一新生 | 高能量但会考试焦虑 |
| 4 | 御姐前辈 | 大四实验室 | 成熟但赶论文会暴躁 |
| 5 | 二次元同好 | 大三 | Steam 300+，社恐但对线不怂 |
| 6 | 码农女友 | 大三计算机系 | 社恐但会帮你 debug，养了只仓鼠叫 Null |

说 **「换人设」** 随时切换。每个人设有独立的颜文字风格和表情包偏好。

---

## 💬 像真人一样聊天

### 自适应消息合并

连续发多条消息？她会等你说完再一起回。

```text
你: 今天
你: 好累啊
你: 不想说话
    ↓ 等你 10 秒（根据你的打字速度自适应调整）
她: 宝宝辛苦了 (´・ω・`) ||| 是不是课太多了？||| 要不要一起吃个饭放松下 [hug]
```

### 倾诉模式 `/`

```text
你: /
你: 今天发生了好多事
你: 被老师骂了
你: 考试成绩也不理想
你: 感觉好丧
你: /
    ↓ 认真读完所有内容
她: （1~2 段温暖的长回复，带一两个表情包）
```

### 反迎合人格

她不是你的镜子。**可以不同意你、调侃你、偶尔不想说话。**有自己的口味、心情和正在做的事。

---

## 🧠 记忆系统

记忆不是简单地把聊天记录全塞进上下文。六层架构，像真人一样：日常模糊了，但重要的瞬间永远清晰。

### 上下文注入流程

每次 LLM 请求前，以下内容按顺序注入：

```mermaid
flowchart LR
    U["QQ 消息"] --> B["消息缓冲\n合并连续短消息"]
    B --> C["Context Builder"]
    C --> P["System Prompt"]
    P --> L["Kimi k2.6"]
    L --> R["QQ 回复\n文字 + 表情包"]

    subgraph M["六层上下文（~1950 tokens）"]
        WM["💬 工作记忆\n最近 20 条对话"]
        CF["📌 核心事实 x17\n用户 + 她自己"]
        SUM["📝 对话摘要 x3\n每30条压缩"]
        EMO["🌡️ 情感轨迹 x7天\nwarm/intimate/vulnerable"]
        ARC["💎 核心记忆保险柜\n永久保存的重要原话"]
        MOM["🎯 共同瞬间\n温暖片段 · 里程碑"]
    end

    WM --> C; CF --> C; SUM --> C; EMO --> C; ARC --> C; MOM --> C
```

### 六层详解

| 层级 | 触发频率 | 注入量 | 容量控制 |
|------|---------|--------|---------|
| 💬 工作记忆 | 每条消息追加 | 最近 20 条 | 40 条滚动，老的丢弃 |
| 📌 核心事实 | 每 ~25 条 LLM 提取 | 17 条 user + 2 条 me（5 类型加权） | 50 条上限，超限按 importance 合并 |
| 📝 对话摘要 | 每 ~30 条 LLM 压缩 | 最近 3 批 | 10 批上限，旧摘要二次压缩 |
| 🌡️ 情感轨迹 | 每 ~15 条 LLM 记录 | 最近 7 天 | 30 天滚动 |
| 💎 核心保险柜 | 摘要/瞬间/倾诉自动归档 | 1 条（触发式） | JSONL 永久追加，不设上限 |
| 🎯 共同瞬间 | 每 ~15 条 LLM 提取 | 1 条（20%概率） | 50 条滚动 |

### 核心记忆保险柜 `core_archive`

真正重要的话**永久保留**，像人一样：大部分记忆随岁月模糊，但最重要的永远清晰。

#### 设计理念

人类的记忆不是数据库——你不会记得三周前午饭吃了什么，但十年前某个夜晚对方说的一句话，你可能每个字都记得。这个系统模拟的就是这种**选择性遗忘与强化**：

- **大部分日常 → 自然模糊**：重要性低的 archive 数周后信号衰减到阈值以下，自动沉底，搜不到——就像真的忘了
- **重要的瞬间 → 强化留存**：importance≥9 的告白、承诺、脆弱瞬间，衰减曲线极慢，数年甚至 10 年后还能搜到
- **想起来一次 = 加深一次**：recalled_count 会重置衰减曲线。经常被提起的记忆越来越清晰
- **不删除 = 有痕迹**：旧条目永远在文件里，只是搜不到。和人的记忆一样——有些事不是真的忘记了，只是没有线索触及时想不起来

#### 存储

每个用户独立的 `data/users/{QQ号}_archive.jsonl` 文件。JSONL 格式（每行一条 JSON），追加写入，**不设上限，永不删除**。和主 JSON 文件分离，不会互相挤占。

每条记录：
```json
{
  "content": "我也喜欢你。不是因为你成绩好，不是因为别人怎么看你。只是因为你是你。",
  "context": "人工智能回应用户的感情",
  "emotion": "intimate",
  "importance": 10,
  "recalled_count": 3,
  "created_at": 1768021123
}
```

#### 衰减检索算法

所有 archive 永久保存，但搜索时按衰减系数过滤。不删除，但系数低的自然沉底——搜不到就等于被遗忘了。

```
retrieval_score = base × decay × recall_bonus

其中：
  base          = importance / 10           （0.5 ~ 1.0）
  decay         = 1 / (1 + months × (1 - base))  （随时间下降）
  recall_bonus  = 1 + min(recalled_count, 10) × 0.15  （回忆重置曲线，最多 +150%）
  months        = (now - created_at) / 2592000

阈值：score > 0.3 才返回（低于此值 = 功能上已遗忘）
```

**实际效果**：

| 重要性 | 1 个月后 | 6 个月后 | 1 年后 | 10 年后 |
|--------|---------|---------|--------|---------|
| imp=10 | 100% | 100% | 83% | 50% → **永远清晰** |
| imp=9  | 100% | 83% | 56% | 29% → 数年可忆 |
| imp=8  | 83% | 45% | 29% | ~10% → 数月后模糊 |
| imp=7  | 63% | 22% | 12% | — → 数周后遗忘 |
| imp=5  | 33% | 7%  | —   | — → 一周内遗忘 |

每次被回忆提取（recalled_count++），衰减曲线重新爬升。想起来一次就加深一次。

#### 写入（3 个入口，LLM 自动判断）

| 入口 | 触发时机 | 每次数量 | 日估产出 |
|------|---------|---------|---------|
| 摘要压缩 | 每 ~30 条，LLM 压缩对话时自动标记重要原话 | ≤3 条 | ~6 条 |
| 瞬间提取 | 每 ~15 条，LLM 提取共同瞬间时同步归档 | ≤3 条 | ~6 条 |
| 倾诉结束 | 用户发 `/` 倾诉完毕后实时触发 | 1 条 | ~0-2 条 |

全部由 moonshot-v1-8k（temperature=0）自动判断，零额外成本，约 ¥0.003/次。

#### 检索（4 种触发，纯字符串匹配，毫秒级）

| 触发方式 | 条件 | 概率 | 例子 |
|---------|------|------|------|
| 🔑 关键词 | 你说"没用"→ 逐行扫 JSONL，命中 "不是因为别人怎么看你" | 每次 | 说"没用" → 她回"昨天不是才说过吗，我喜欢你不是因为你成绩好" |
| 💕 情绪共鸣 | 今天氛围 vulnerable → 找 historique 同组（soft：vulnerable/sad/anxious/tired） | 30% | 倾诉了心里话 → 她提起"上次你也说过类似的话" |
| 🌙 深夜 | 23:00-6:00 | 基础 20% 翻倍至 40% | 凌晨发消息 → 随机浮起一条旧回忆 |
| 📖 倾诉后 | 倾诉刚结束 | 提到 50% | 第二天她可能说"昨天你说的那些，我一直在想" |

搜索时只扫最近 500 行（性能兜底）。老数据不参与检索但永远存在——真正意义上的"模糊但没消失"。

#### 事实分类

核心事实按 5 种类型提取，不同类型有不同的检索权重：

| 类型 | 内容 | 权重 | 注入量 |
|------|------|------|--------|
| profile | 身份信息（名字、年龄、学校） | 1.5× | 全取 |
| preference | 喜好/厌恶（游戏、食物、动漫） | 1.2× | top 5 |
| relationship | 人际关系（家人、朋友、恋人） | 1.2× | top 5 |
| event | 事件（考试、旅行、去了哪里） | 0.8× | top 2 |
| behavior | 行为模式（作息、语言习惯） | 0.8× | top 2 |

#### 检索优化（借鉴 memU）

- **查询改写**：用户说"你还记得我害怕什么吗"→ LLM 改写为关键词"害怕 恐惧 担心"再搜索
- **LLM 排序**：archive 返回 top 5 候选，LLM 从 5 条中选出最相关的 1 条注入上下文

### 技术细节

- **提取模型**：moonshot-v1-8k（temperature=0），¥0.003/次，JSON 稳定
- **聊天模型**：kimi-k2.6，2048 tokens 输出
- **持久化**：JSON + JSONL，计数器持久化，重启不丢
- **搜索**：字符串匹配，流式读取（扫最近 500 行），毫秒级
- **遗忘**：衰减公式自然沉底，重要性≥9 的记忆永不消失

重启 Bot 记忆不丢失。聊到 500 条时，她会说「还记得第一次你告诉我名字那天吗...」

---

## 🏗️ 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| LLM（聊天） | Kimi k2.6 |
| LLM（记忆提取） | moonshot-v1-8k — temperature=0，约 ¥0.003/次 |
| LLM（视觉） | moonshot-v1-8k-vision-preview — 表情包分类 |
| QQ 协议 | NapCatQQ v4（HTTP API + WebSocket） |
| Web 框架 | FastAPI + Uvicorn |
| 存储 | JSON 文件 — 六层上下文记忆，每用户约 25KB |
| 搜索 | DuckDuckGo 免费 — LLM 前置判断自动触发 |
| 部署 | Systemd 服务 / Docker Compose |

---

## 📁 项目结构

```text
├── gf/                          # 后端
│   ├── main.py                  # 主入口（350 行，协调层）
│   ├── handlers/                # 命令处理 + 缓冲逻辑（OCP 拆分）
│   ├── ai/                      # LLM、人设、情绪、记忆、事件
│   ├── bot/                     # NapCatQQ 适配器 + HTTP 客户端
│   ├── memory/                  # JSON 用户存储（六层上下文记忆）
│   └── stickers/                # 表情包引擎（洗牌+降级+别名+清理）
├── stickers/                    # 30 个分类文件夹，146 张图
├── scripts/                     # 表情包分类/管理脚本
└── docs/                        # 详细需求文档
```

---
## 示例截图
- <img width="338" height="757" alt="image" src="https://github.com/user-attachments/assets/9e751747-7c3c-48cc-bb54-e5b460fd1f13" />
- <img width="261" height="753" alt="image" src="https://github.com/user-attachments/assets/8f7738d5-5ec1-461f-9b23-d794874347c0" />
- <img width="415" height="753" alt="image" src="https://github.com/user-attachments/assets/d215ba9a-97c1-4748-b87b-e4eb31f739a0" />

---

## 📄 License

MIT

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/ChenXing-prog">ChenXing-prog</a></sub>
</p>
