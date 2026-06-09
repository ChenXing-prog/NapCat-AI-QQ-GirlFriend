# 表情包初始分类需求文档

> 状态：待实现 | 优先级：P0（表情包系统重构的前置依赖）

---

## 一、背景与目标

### 1.1 现状

`data/images/` 下有 **146 张**表情包图片，全部使用 SHA256 哈希命名（例如 `A9D8868A4A19F402FD7BDE2BB5CEA6EE.jpg`）。文件名不包含任何语义信息，无法根据文件名推断图片内容。

文件特征：
- 总数量：146 张
- 格式：144 张 `.jpg` + 2 张 `.gif`（`995B4EDBF1F38745BF8740F5BC3B3641.gif`、`5DE328F5641C49B70E48C76C4BDFFBC1.gif`）
- 大小范围：9.6 KB ~ 2.0 MB
- 当前结构：全部平铺在一个文件夹，无子目录，无分类

### 1.2 目标

将这 146 张图片按照**情绪/情感**自动分类到 30 个预定义类别中，输出到 `stickers/` 目录结构：

```
stickers/
├── laugh/       # 大笑
├── smile/       # 微笑
├── smirk/       # 坏笑
├── star_eyes/   # 星星眼
├── satisfied/   # 满足
├── excited/     # 兴奋
├── shy/         # 害羞
├── cute/        # 卖萌
├── clingy/      # 黏人
├── begging/     # 求求了
├── pout/        # 撅嘴
├── tsundere/    # 傲娇
├── eye_roll/    # 嫌弃/翻白眼
├── speechless/  # 无语
├── questioning/ # 问号
├── sigh/        # 叹气
├── caring/      # 关心
├── pat/         # 摸摸头
├── hug/         # 抱抱
├── love/        # 比心/爱你
├── cry/         # 大哭
├── teary/       # 委屈
├── heartbroken/ # 心碎
├── corner/      # 蹲角落
├── shocked/     # 震惊
├── panic/       # 慌张
├── peek/        # 暗中观察
├── proud/       # 得意
├── sleepy/      # 困了/晚安
└── rage/        # 暴怒
```

### 1.3 为什么用外部 Vision API

DeepSeek 当前版本不支持多模态（vision），无法直接识别图片内容。Kimi（Moonshot）支持 Vision，可以理解图片内容并返回结构化 JSON，适合批量自动分类。

---

## 二、技术方案

### 2.1 整体流程

```
┌─────────────────┐
│ data/images/    │  146 张哈希命名图片
│ (平铺)          │
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│ 1. 预处理       │  去重、格式校验、损坏检测
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│ 2. Kimi Vision  │  逐张 base64 编码 → API 分类
│ API 批量分类    │  返回 JSON: {tag, description}
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│ 3. 结果处理     │  移动图片到 stickers/{tag}/
│                 │  生成分类报告
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│ 4. 人工复核     │  抽查分类结果，修正错误
│ (可选)          │
└─────────────────┘
```

### 2.2 步骤一：预处理

#### 2.2.1 图片去重

使用感知哈希（Perceptual Hash / `phash`）检测近似重复的图片：

```python
# 伪代码
hashes = {}
for img in images:
    ph = compute_phash(img)  # 如 imagehash 库
    hamming_dist = min(hamming(ph, h) for h in hashes)
    if hamming_dist <= 5:     # 阈值 5：近似重复
        mark_as_duplicate(img) # 移到 _duplicates/ 或删除
    else:
        hashes[img] = ph
```

**目的**：同一张表情包的不同压缩/裁剪版本只保留一张，避免 API 重复调用的费用，也让分类后各文件夹内容更干净。

#### 2.2.2 格式校验

- 只支持 `image/jpeg`、`image/png`、`image/gif`、`image/webp`
- 读取文件头魔数验证是否为有效图片
- `gif` 动画取第一帧用于分类（Kimi Vision 对 GIF 只识别第一帧）

#### 2.2.3 损坏检测

- 用 Pillow 尝试打开每张图片
- 打开失败的移动到 `data/images/_corrupted/` 并记录日志
- 打开成功但尺寸异常（< 20x20 或 > 8000x8000）的标记为异常

#### 2.2.4 预处理输出

```
data/images/_duplicates/   ← 近似重复的图片（可删除或手动复审）
data/images/_corrupted/     ← 损坏/异常图片，人工处理
data/images/                ← 通过校验的图片，进入分类流程
```

### 2.3 步骤二：Kimi Vision API 批量分类

#### 2.3.1 API 配置

| 配置项 | 值 |
|--------|-----|
| API 地址 | `https://api.moonshot.cn/v1` |
| 模型 | `moonshot-v1-8k-vision-preview`（或最新 vision 模型）|
| 鉴权 | `Authorization: Bearer $MOONSHOT_API_KEY` |
| 单张耗时 | 约 2-5 秒（含网络） |
| 单张成本 | 约 ¥0.03-0.06（视图片大小） |
| **146 张总成本** | **约 ¥5-9** |

环境变量：`MOONSHOT_API_KEY=sk-xxxxxxxx`

#### 2.3.2 API 请求格式

```json
{
  "model": "moonshot-v1-8k-vision-preview",
  "messages": [
    {
      "role": "system",
      "content": "你是一个表情包分类器。用户会给你一张表情包图片，你需要判断这张图表达的情绪，从给定的分类中选择最匹配的一个。只输出 JSON，不要其他文字。"
    },
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,/9j/4AAQ..."
          }
        },
        {
          "type": "text",
          "text": "请判断这张表情包的情绪分类。\n\n可选分类（只能选一个）：\n- laugh：大笑、笑死、爆笑\n- smile：微笑、开心、温馨\n- smirk：坏笑、嘿嘿嘿、有小九九\n- star_eyes：星星眼、崇拜、好厉害\n- satisfied：满足、吃饱了、爽\n- excited：兴奋、太好了、耶\n- shy：害羞、脸红、不好意思\n- cute：卖萌、求关注、可爱\n- clingy：黏人、别走、陪陪我\n- begging：求求了、拜托、跪求\n- pout：撅嘴、哼、不乐意\n- tsundere：傲娇、才不是为你、口是心非\n- eye_roll：嫌弃、翻白眼\n- speechless：无语、不想说话\n- questioning：问号、黑人问号、啥？？\n- sigh：叹气、心累、唉\n- caring：关心、体贴、担心\n- pat：摸摸头、安慰、乖\n- hug：抱抱、想要拥抱\n- love：比心、爱你、喜欢你\n- cry：大哭、哭死、爆哭\n- teary：委屈、含泪、被冤枉\n- heartbroken：心碎、受伤了\n- corner：蹲角落、自闭、别理我\n- shocked：震惊、什么情况\n- panic：慌张、完了完了\n- peek：暗中观察、让我看看\n- proud：得意、哼我厉害吧\n- sleepy：困了、晚安、睡觉\n- rage：暴怒、掀桌、气炸\n\n输出 JSON 格式：\n{\"tag\": \"分类标签\", \"confidence\": 0.0-1.0, \"description\": \"中文简短描述（10字内）\"}"
        }
      ]
    }
  ],
  "temperature": 0.3,
  "max_tokens": 100
}
```

#### 2.3.3 期望响应

```json
{
  "tag": "shy",
  "confidence": 0.92,
  "description": "脸红害羞捂脸"
}
```

#### 2.3.4 低置信度处理

| 置信度范围 | 处理方式 |
|-----------|---------|
| ≥ 0.8 | 直接分类到 `stickers/{tag}/` |
| 0.5 - 0.8 | 分类到 `stickers/{tag}/`，标记为需要抽查（写入报告） |
| < 0.5 或 API 失败 | 移到 `stickers/_review/`，等待人工分类 |

#### 2.3.5 API 调用策略

- **并发控制**：最多 3 个并发请求（避免触发 API 频控），使用 `asyncio.Semaphore(3)`
- **重试机制**：失败最多重试 2 次，间隔 3 秒
- **进度持久化**：每完成一张，写入 `scripts/classification_progress.json`，支持中断后恢复
- **日志记录**：每次 API 调用记录时间、耗时、消耗 token 数

### 2.4 步骤三：结果处理

#### 2.4.1 移动文件

```python
for result in classified:
    src = Path("data/images") / result["filename"]
    dst = Path("stickers") / result["tag"] / result["filename"]
    shutil.move(src, dst)
```

#### 2.4.2 生成报告

输出 `scripts/classification_report.md`：

```markdown
# 表情包分类报告

生成时间：2026-06-09 14:30
API 模型：moonshot-v1-8k-vision-preview
总数量：146 张
成功分类：138 张
需人工复审：6 张（低置信度）
失败：2 张（原因：...）

## 分类分布

| 分类 | 数量 | 占比 |
|------|------|------|
| cute | 12 | 8.2% |
| laugh | 10 | 6.8% |
| shy | 9 | 6.2% |
| ... | ... | ... |

## 需复审

| 文件名 | 置信度 | 建议分类 | 描述 |
|--------|--------|----------|------|
| xxx.jpg | 0.45 | shocked | Kimi 不确定是震惊还是慌张 |
...

## 失败列表

| 文件名 | 错误 | 
|--------|------|
| xxx.gif | API 超时（重试2次） |
```

#### 2.4.3 清理

分类完成后：
- `data/images/` 清空（所有图片已移动）
- `data/images/_duplicates/` 清空（重复图片可安全删除）
- `data/images/_corrupted/` 保留（人工确认后删除）

### 2.5 步骤四：人工复核

1. **抽查**：从每个分类随机抽 2-3 张，确认分类准确
2. **修正**：把分错的图手动移到正确文件夹
3. **复审 `_review/` 目录**：手动或借助其他工具分类
4. 复查 `stickers/` 下 30 个文件夹，删除空的（该分类没有图片）
5. 最终确认后删除 `scripts/classification_progress.json`

---

## 三、输出物

### 3.1 脚本

| 文件 | 功能 |
|------|------|
| `scripts/classify_stickers.py` | 主脚本：预处理 → Kimi 分类 → 移动 → 报告 |

### 3.2 数据文件

| 文件 | 说明 |
|------|------|
| `scripts/classification_progress.json` | 进度文件（支持断点续传） |
| `scripts/classification_report.md` | 分类结果报告 |

### 3.3 最终目录结构

```
stickers/
├── laugh/       meta.json + N 张图
├── smile/       meta.json + N 张图
├── ...          30 个分类文件夹
├── _review/     低置信度图片（待人工复核，复核后删除）
└── _empty/      空分类（该分类无图片，后续可删除或手动补图）
```

### 3.4 后续依赖

分类完成后：
- `stickers/` 成为表情包引擎的「源文件夹」
- 引擎初始化 `StickerEngine(Path("./stickers"))`
- 原有 `data/images/` 不再使用（可删除）

---

## 四、脚本设计要点

### 4.1 `classify_stickers.py` 命令行接口

```bash
# 完整运行：预处理 → 分类 → 移动 → 报告
python scripts/classify_stickers.py

# 只做预处理（去重 + 校验）
python scripts/classify_stickers.py --step preprocess

# 只做分类（需要 MOONSHOT_API_KEY，支持断点续传）
python scripts/classify_stickers.py --step classify

# 只生成报告（不调 API）
python scripts/classify_stickers.py --step report

# 干跑（不实际移动文件，只输出计划）
python scripts/classify_stickers.py --dry-run
```

### 4.2 断点续传

`classification_progress.json` 格式：

```json
{
  "started_at": "2026-06-09T14:00:00",
  "total": 146,
  "completed": ["A9D886...jpg", "A61FFA...jpg", ...],
  "failed": {"xxx.gif": "timeout"},
  "results": {
    "A9D886...jpg": {"tag": "shy", "confidence": 0.92, "description": "脸红害羞"},
    ...
  }
}
```

中断后重新运行 `--step classify`，自动跳过 `completed` 中的文件。

### 4.3 错误处理

| 错误类型 | 处理策略 |
|---------|---------|
| API 超时（30s） | 重试 2 次，间隔 3s |
| API 429 限频 | 等待 10s 后重试，指数退避 |
| API 5xx 服务错误 | 重试 2 次，间隔 5s |
| 图片 base64 > 20MB | 压缩到 800px 宽再编码 |
| 图片无法打开 | 移到 `_corrupted/`，记录日志 |
| JSON 解析失败 | 重试一次（temperature=0.1），仍失败则移到 `_review/` |

---

## 五、环境依赖

### 5.1 Python 包

```txt
# requirements-sticker-tools.txt
moonshot>=0.3.0          # Kimi SDK (或直接用 httpx 调 REST API)
httpx>=0.28.0            # HTTP client
Pillow>=10.0.0           # 图片处理
imagehash>=4.3.1         # 感知哈希去重
python-dotenv>=1.0.0     # 环境变量（MOONSHOT_API_KEY）
```

### 5.2 环境变量

创建 `scripts/.env`：

```bash
MOONSHOT_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 六、执行 CHECKLIST

- [ ] 安装依赖：`pip install httpx Pillow imagehash python-dotenv`
- [ ] 获取 Kimi API Key，写入 `scripts/.env`
- [ ] 运行预处理：`python scripts/classify_stickers.py --step preprocess`
- [ ] 检查 `_duplicates/` 和 `_corrupted/`，确认无重要图片被误删
- [ ] 运行分类：`python scripts/classify_stickers.py --step classify`
- [ ] 查看报告：`cat scripts/classification_report.md`
- [ ] 抽查各分类文件夹，确认无重大分类错误
- [ ] 手动处理 `_review/` 和 `_empty/`
- [ ] 确认后删除 `data/images/`
