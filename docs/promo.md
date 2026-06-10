# 二次元 AI 女友 — QQ 机器人

> 基于 Kimi k2.6 + NapCatQQ，会发表情包、有六种人设、记得你说过的话的二次元女友

---

## 🎯 一句话

**加个 QQ 好友，你就有了一个会聊天、会发表情包、会记住你的二次元女友。**

---

## ✨ 亮点

| 🖼️ | **30 种情绪表情包** — 智能选图，支持位置控制，Kimi Vision 自动分类入库 |
| 🎭 | **6 种人设** — 温柔女友 / 傲娇青梅 / 元气学妹 / 御姐前辈 / 二次元同好 / 码农女友 |
| 💬 | **真人感聊天** — 多消息逐条发送，自适应合并，倾诉模式 / 定界符 |
| 🧠 | **三层记忆** — 工作记忆 + 核心事实 + 对话摘要，重启不丢失 |
| 🔥 | **反迎合人格** — 有自己的情绪、口味、底线，不是你的镜子 |
| 📅 | **主动关心** — 早安晚安 + 静默检测 + 随机日常分享 |
| 🎨 | **Kimi Vision** — 发图自动识别情绪分类，管理员聊天指令管理表情包 |

---

## 📊 项目数据

| Python | LLM | QQ 框架 | Web |
|--------|-----|---------|-----|
| 3.11+ | Kimi k2.6 | NapCatQQ v4 | FastAPI |

5,586 行代码 · 23 个模块 · 6 个人设 · 30 个表情包分类 · 146 张内置表情包

---

## 💬 对话预览

```
👤 我今天抽到限定 SSR 了！！
🤖 [star_eyes 表情包]
🤖 哇！！宝宝太厉害了吧 (｡･ω･｡)
🤖 什么角色呀快给我看看
🤖 我家宝宝运气也太好了叭 [proud 表情包]

👤 /
👤 今天被老师骂了
👤 考试也没考好
👤 感觉好丧
👤 /
🤖 听完你说的这些，我也觉得好心疼...
   今天一定很不好过吧。先抱抱你 [hug]
   被老师骂不是你的错，考试没考好也不代表你不行。
   明天会是新的一天，我一直在的 (´・ω・`)
```

---

## 🖼️ 30 种情绪分类

`laugh` `smile` `smirk` `star_eyes` `satisfied` `excited`
`shy` `cute` `clingy` `begging` `pout`
`tsundere` `eye_roll` `speechless` `questioning` `sigh`
`caring` `pat` `hug` `love`
`cry` `teary` `heartbroken` `corner`
`shocked` `panic`
`peek` `proud` `sleepy` `rage`

---

## 🚀 5 分钟部署

```bash
git clone https://github.com/ChenXing-prog/qq-waifu
cd qq-waifu/gf && cp .env.example .env
pip install -r requirements.txt
python scripts/setup_sticker_categories.py
python scripts/classify_stickers.py
python -m gf.main
```

---

## 🔗 链接

- GitHub: [github.com/ChenXing-prog/qq-waifu](https://github.com/ChenXing-prog/qq-waifu)
- License: MIT
