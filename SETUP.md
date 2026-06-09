# AI 女友 QQ 机器人 — 部署指南

## 架构概览

```
你的 QQ ←→ 腾讯服务器 ←→ NapCatQQ (Docker) ←→ gf 后端 (Python)
                               ↓ HTTP:3000 + WS:3001
                        [扫码登录一次，长期在线]
```

## 步骤 1：安装 Docker Desktop

NapCatQQ 通过 Docker 运行。macOS 需要安装 Docker Desktop（免费）：

```bash
brew install --cask docker
```

安装后启动 Docker Desktop（Applications → Docker），等菜单栏图标变绿。

## 步骤 2：启动 NapCatQQ

```bash
cd ~/AIGirlFriend

# 启动 NapCatQQ 容器
docker compose up -d
```

## 步骤 3：扫码登录 QQ

打开浏览器访问：**http://localhost:6099**

会看到一个 Linux 桌面（VNC），里面有 QQ 登录界面。用**手机 QQ 扫码**登录。

> ⚠️ 用**小号**登录！新号可能被风控，建议用一个注册超过 3 个月的 QQ 号。

登录成功后可以关闭浏览器，QQ 会一直在线。

## 步骤 4：配置并测试连接

### 4.1 填入 Bot QQ 号

```bash
cd gf
# 编辑 .env，把 BOT_QQ 改成你刚登录的 QQ 号
```

### 4.2 测试 NapCatQQ 连接

```bash
python -m gf.bot.test_napcat
```

输出应该是：
```
✅ Connected!
QQ: 你的QQ号
昵称: 你的昵称
✅ Test message sent. Check your QQ!
```

## 步骤 5：启动 AI Bot

```bash
cd ~/AIGirlFriend/gf
python -m gf.main
```

输出：
```
Starting 小暖 on 127.0.0.1:8000
Connected to NapCatQQ WebSocket
```

现在用另一个 QQ 给 Bot 发消息，就会收到 AI 女友的回复了！

## 步骤 6：添加表情包（可选）

把表情包图片放到对应情绪文件夹：

```
stickers/
├── happy/    ← 放开心/可爱的图 (.png .jpg .gif)
├── shy/      ← 放害羞/脸红的图
├── caring/   ← 放关心/摸摸头的图
...
```

放完图片后 Bot 会自动随机选取。

## 常用命令

```bash
# 查看日志
docker logs -f napcat

# 重启 NapCatQQ
docker compose restart

# 停止
docker compose down

# 查看 Bot 聊过的用户
curl http://localhost:8000/users

# 查看表情包状态
curl http://localhost:8000/stickers
```

## 目录结构

```
AIGirlFriend/
├── docker-compose.yml       # NapCatQQ 容器
├── napcat-data/             # QQ 登录状态 (勿删)
├── gf/                      # 后端代码
│   ├── .env                 # 你的配置
│   └── main.py              # 主程序
├── stickers/                # 表情包图片
└── data/                    # 用户聊天记忆
```
