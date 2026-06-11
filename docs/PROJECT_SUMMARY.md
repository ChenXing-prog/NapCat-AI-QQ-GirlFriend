# 二次元 AI 女友 — 项目完整总结

> 基于 Kimi k2.6 + NapCatQQ v4 的 QQ 聊天机器人  
> 5,586 行 Python · 23 模块 · 6 人设 · 30 表情包分类 · 六层记忆  
> 最后更新：2026-06-11

---

## 一、架构概览

```
QQ 客户端 ←→ NapCatQQ v4 ←→ Python FastAPI (gf/main.py)
                                │
                ┌───────────────┼───────────────┐
                │               │               │
           Kimi k2.6      六层记忆系统      表情包引擎
           (文本LLM)      (JSON/JSONL)   30分类+洗牌+降级
                │               │               │
           DuckDuckGo      主动调度器      moonshot-vision
           (联网搜索)     (asyncio协程)   (图片识别)
```

### 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 聊天 LLM | Kimi k2.6（temperature=1.0, max_tokens=1024） |
| 记忆提取 LLM | moonshot-v1-8k（temperature=0, JSON稳定） |
| 视觉 LLM | moonshot-v1-8k-vision-preview |
| QQ 协议 | NapCatQQ v4（HTTP API + WebSocket） |
| 搜索 | DuckDuckGo（LLM 前置判断自动触发） |
| 存储 | JSON（用户数据）+ JSONL（archive 永久记忆） |
| 部署 | Systemd（ExecStartPre 杀僵尸） |

---

## 二、消息处理流程

```
QQ消息 → WebSocket事件 → handle_private_message()
  │
  ├─ 图片检测 → NapCat get_file → vision描述 → 注入上下文
  ├─ 指令检测（//菜单 / //提高一档 / 换人设 ...）→ 立即处理
  ├─ 倾诉模式（/ 定界符）→ 专用prompt → 长回复
  ├─ 普通消息 → 自适应缓冲（10s默认，1.5×自适应）→ 合并
  │
  └─ _real_handle_message()
       ├─ 联网搜索判断（moonshot-v1-8k → DuckDuckGo）
       ├─ 六层记忆注入（~1950 tokens）
       ├─ LLM chat_multi() → MessagePart 列表
       ├─ catch-all 清理残留 []
       ├─ 逐条发送（0.8-2.5s人类感间隔）
       └─ 后台异步：记忆提取 + 事件提取 + 情感记录
```

### 输出 Token 分配

| 模式 | max_tokens | 说明 |
|------|-----------|------|
| 普通聊天 | 1024 | 3-4条短消息 |
| 倾诉模式 | 8192 | 1-2条长回复 |

---

## 三、六层记忆系统

### 3.1 存储架构

```
data/
├── users/{QQ号}.json          # 主文件 ~30KB（工作记忆+事实+摘要+情感+瞬间）
└── users/{QQ号}_archive.jsonl # Archive 独立文件（永久追加，不设上限）
```

### 3.2 各层详解

| 层级 | 存储 | 触发 | 注入量 | 容量 |
|------|------|------|--------|------|
| 💬 工作记忆 | `recent_messages` | 每条消息追加 | 最近 20 条 | 40条滚动 |
| 📌 核心事实 | `core_facts`（5类型） | 每~25条 LLM 提取 | 17 user + 2 me（类型加权） | 50条，超限合并 |
| 📝 对话摘要 | `summaries` | 每~30条 LLM 压缩 | 最近 3 批 | 10批，超限二次压缩 |
| 🌡️ 情感轨迹 | `emotion_log` | 每~15条 LLM 记录 | 最近 7 天 | 30天滚动 |
| 💎 核心记忆 | `archive.jsonl`（独立） | 摘要+瞬间+倾诉 | 1条（触发式） | 永久追加 |
| 🎯 共同瞬间 | `shared_moments` | 每~15条 + 里程碑 | 1条（20%概率） | 50条滚动 |

### 3.3 事实分类（5 类型）

| 类型 | 权重 | 注入量 | 示例 |
|------|------|--------|------|
| profile | 1.5× | 全取 | "叫冉佳轩，大三计算机系" |
| preference | 1.2× | top 5 | "喜欢FPS游戏，讨厌香菜" |
| relationship | 1.2× | top 5 | "和妈妈关系紧张" |
| event | 0.8× | top 2 | "6月10日去了漫展" |
| behavior | 0.8× | top 2 | "总是在凌晨发消息" |

### 3.4 Archive 衰减检索

```
retrieval_score = base × decay × recall_bonus

base         = importance/10
decay        = 1/(1 + months × (1 - base))
recall_bonus = 1 + min(recalled_count, 10) × 0.15
阈值         = 0.3（低于此值功能上已遗忘）
```

| importance | 1个月 | 6个月 | 1年 | 10年 |
|-----------|------|------|-----|------|
| 10 | 100% | 100% | 83% | 50% |
| 8 | 83% | 45% | 29% | ~10% |
| 5 | 33% | 7% | — | — |

### 3.5 Archive 触发机制

| 触发 | 条件 | 概率 |
|------|------|------|
| 关键词 | 用户消息命中 archive 的 content/context | 每次 |
| 情绪共鸣 | 今日氛围与 archive 同组（柔软组/温暖组） | 30% |
| 深夜 | 23:00-6:00 | 翻倍至 40% |
| 倾诉后 | 倾诉刚结束 | 50% |
| 里程碑 | 500/1000条 | 回顾最早3条 |

---

## 四、人设系统

### 4.1 六种人设

| # | ID | 名字 | 身份 | 核心特质 |
|---|-----|------|------|---------|
| 1 | gentle | 温柔女友 | 大三设计系 | 温暖有主见，不是烂好人 |
| 2 | tsundere | 傲娇青梅 | 大二计算机系 | 嘴硬心软，做独立游戏 |
| 3 | genki | 元气学妹 | 大一新生 | 高能量但考试焦虑 |
| 4 | oneesan | 御姐前辈 | 大四实验室 | 成熟但赶论文暴躁 |
| 5 | otaku | 二次元同好 | 大三 | Steam300+，社恐但对线不怂 |
| 6 | coder | 码农女友 | 大三计算机系 | 社恐但会debug，养仓鼠叫Null |

### 4.2 Persona 数据结构

```python
@dataclass
class Persona:
    # 身份
    id, name, display_name, tagline
    # 心理深度
    deepest_want, core_fear, contradictions
    # 性格与风格
    personality, backstory, speaking_style, emoji_style
    self_reference, partner_address
    # 底线与反应
    boundaries, reaction_rules
    # 情绪
    mood_range
    # 表情包
    sticker_weight: dict[str, float]
    # 二次元
    otaku_level, otaku_topics
    # 对话
    message_length, proactive_style, teasing_frequency
    # 日常
    daily_topics: list[str]
```

---

## 五、表情包系统

### 5.1 30 分类

| 系列 | 标签 |
|------|------|
| 喜悦 | laugh smile smirk star_eyes satisfied excited |
| 撒娇 | shy cute clingy begging pout |
| 傲娇 | tsundere eye_roll speechless questioning sigh |
| 关心 | caring pat hug love |
| 难过 | cry teary heartbroken corner |
| 吃惊 | shocked panic |
| 整活 | peek proud sleepy rage |

### 5.2 引擎特性

- **洗牌队列**：同分类循环使用，不重复
- **降级映射**：空分类自动跳到相似有图分类
- **别名归一化**：`[heart]→[love]` 等 39 个别名
- **catch-all 清理**：`[爱][◍•ᴗ•◍][coffee]` 自动剥离
- **标签格式**：`[S:love]`=末尾 `[S-MID:cute]`=中间 `[S-ONLY:cry]`=纯图
- **用户拉黑**："不喜欢这个"→永久拉黑
- **管理员添加**：发图→Kimi Vision 自动分类入库

### 5.3 图片识别

用户发图 → `vision.py` 提取 file_id → NapCat get_file 查本地路径 → Pillow 读取 → moonshot vision 描述 → 注入 LLM 上下文。file_id 缓存避免重复请求。

---

## 六、主动联系系统

### 6.1 定时问候

- 早安：7:00-10:00 随机（±15分钟抖动）
- 晚安：21:00-0:00 随机

### 6.2 六档黏人度

| 档位 | 静默阈值 | 每天上限 | 追发次数 |
|------|---------|---------|---------|
| 1 佛系 | 8h | 1 | 0 |
| 2 正常 | 5h | 3 | 1 |
| 3 黏人 | 3h | 5 | 1 |
| 4 超黏 | 1.5h | 8 | 2 |
| 5 话痨 | 45min | 12 | 2 |
| 6 夺命 | 20min | 20 | 3 |

指令：`//提高一档` `//降低一档` `//当前档位`

### 6.3 随机日常分享

每天 2-3 次，活跃时段（9:00-23:00）。内容由 LLM 生成，注入六层记忆，上下文驱动动机选择（想你/关心/陪伴/分享）。独立计数器，不受定时问候上限限制。

### 6.4 实现

ProactiveScheduler — asyncio 协程，每 60 秒扫描所有用户，检查各触发条件。

---

## 七、用户管理

### 7.1 三级用户

| 等级 | 消息/时 | 图片/时 | 权限 |
|------|--------|--------|------|
| admin | 无限 | 无限 | 管理指令+表情包+用户管理 |
| vip | 60 | 20 | 正常聊天 |
| normal | 20 | 3 | 正常聊天（默认） |

指令：`//设为VIP {QQ}` `//拉黑 {QQ}` `//用户列表`

### 7.2 所有指令

发 `//菜单` 查看完整指令列表。

---

## 八、LLM 调用方式

### 8.1 调用点

| 位置 | 模型 | 用途 | 频率 |
|------|------|------|------|
| 聊天回复 | kimi-k2.6 | chat_multi() → 多消息+表情包 | 每条消息 |
| 记忆提取 | moonshot-v1-8k | 5类型事实 / 摘要 / 情感 / 瞬间 | 后台异步 |
| Archive 归档 | moonshot-v1-8k | 摘要提取时附带 | 同摘要 |
| 搜索判断 | moonshot-v1-8k | should_search() | 每条消息 |
| 图片识别 | moonshot-v1-8k-vision | describe_image() | 发图片时 |
| 主动分享 | kimi-k2.6 | build_share_prompt → chat() | 每天2-3次 |
| Archive 排序 | moonshot-v1-8k | _rank_archive() | archive触发时 |
| 查询改写 | moonshot-v1-8k | _rewrite_query() | archive搜索时 |

### 8.2 核心接口

```python
# LLMClient (gf/ai/llm.py)
await llm.chat(messages)           # 单条回复 → (text, sticker_tag)
await llm.chat_multi(messages)     # 多条回复 → (MessagePart[], sticker_tag)
# MessagePart = {"type": "text"|"sticker_mid"|"sticker_end"|"sticker_only", ...}

# 记忆提取用独立客户端 (gf/ai/memory.py)
await _lite_chat(system_prompt, user_content, max_tokens)  # moonshot-v1-8k, temperature=0
```

---

## 九、文件结构

```
gf/
├── main.py                    # 主入口（协调层）
├── config.py                  # 配置管理（.env）
├── scheduler.py               # 主动调度器（asyncio协程）
├── handlers/
│   ├── buffer.py              # 自适应缓冲 + 频率限制
│   └── commands.py            # 所有指令处理
├── ai/
│   ├── llm.py                 # LLM客户端（标签解析+别名+清理）
│   ├── persona.py             # System Prompt + 分享Prompt
│   ├── personas.py            # 6人设定义
│   ├── emotion.py             # 18维情绪引擎
│   ├── events.py              # 事件提取+回访
│   ├── memory.py              # 记忆提取（事实/摘要/情感/瞬间）
│   ├── search.py              # 联网搜索
│   ├── vision.py              # 图片识别
│   └── sticker_meta.py        # 表情包元数据（动态加载）
├── bot/
│   ├── adapter.py             # NapCatQQ WebSocket适配器
│   └── client.py              # NapCatQQ HTTP客户端
├── memory/
│   └── store.py               # JSON存储 + Archive JSONL + 衰减检索
└── stickers/
    └── engine.py              # 洗牌队列+降级+黑名单
```

---

## 十、VTuber 集成接口

当前 Bot 的输出是文字。要接入 VTuber（TTS + Live2D），只需要在**消息发送前**加一层 hook：

```python
# main.py _real_handle_message 中，发送消息之前
text = part.get("content", "")
await _qq_client.send_private_msg(user_id, text)  # 现有：发QQ消息
# ↓ 新增：同时输出给TTS
await tts.speak(text)  # 念出来
```

输入侧也可以用 STT 替文字输入。不需要改动记忆、人设、表情包、调度器等任何其他模块。Bot 的"脑子"完全不变，只换输入输出的"嘴巴和耳朵"。
