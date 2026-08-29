# panhub-cli

> 命令行版 PanHub 网盘聚合搜索 — 给 AI agent 和终端用户用的 JSON 友好接口。
>
> A command-line interface for [PanHub](https://github.com/wu529778790/panhub.shenzjd.com) — aggregate netdisk search, agent-friendly JSON output, no node/browser required.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](.python-version)
[![PyPI](https://img.shields.io/pypi/v/panhub-cli.svg)](https://pypi.org/project/panhub-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero deps](https://img.shields.io/badge/dependencies-zero-green.svg)]()

## 它是什么

[PanHub](https://panhub.shenzjd.com) 是一个网盘资源聚合搜索引擎（夸克 / 阿里云盘 / 百度 / 115 / 迅雷 / Telegram 频道等 18+ 源）。`panhub-cli` 是它的命令行封装：

- **`pip install panhub-cli` 一行装好**（PyPI 官方包，Python 3.10+，零运行时依赖）
- **JSON 输出**到 stdout，agent / 脚本可直接消费
- **支持搜索、健康检查、热搜、榜单**等命令
- **优雅解决 Cloudflare "bot forbidden"**：复用浏览器 cookie 即可

## 安装

```bash
# 方式 A：pip 安装（推荐）
pip install panhub-cli
panhub search "纪录片 中东战争"

# 方式 B：源码软链（零依赖、无需 pip、无需 sudo）
git clone https://github.com/hpsh0rk/panhub-cli.git
cd panhub-cli
mkdir -p ~/.local/bin
ln -sf "$(pwd)/bin/panhub" ~/.local/bin/panhub
panhub --version
```

> 境内网络 pip 可能被镜像 SSL 问题卡住（`pip config set global.index-url https://pypi.org/simple/` 可换官方源），
> 或直接用方式 B — `bin/panhub` 自包含，只需 Python 3.10+。

**要求**：Python 3.10+，无第三方依赖。

## 凭据获取（首次使用必读）

> ⚠️ **重要：wxauth-token 和 cf_clearance 是真凭据**，泄漏等同于你的 PanHub 账号被他人长期使用。**绝不**在 issue / 聊天 / 公开仓库 / 任何会被日志记录的地方贴出来。

### 推荐：粘一条完整 cookie（最简单）

`panhub init` 默认走这条路 — 你只需要**一行** `document.cookie`，不用自己拆字段：

1. 打开 https://panhub.shenzjd.com 并**完成登录**（首次：扫描页面上的公众号二维码并关注）
2. 按 `F12` 打开 DevTools → **Console** 标签
3. 输入 `document.cookie` 并回车
4. 复制**整行输出**（形如 `wxauth-token=...; cf_clearance=...; 其他=...`）
5. 运行 `panhub init`，提示时粘贴进去（输入隐藏）

CLI 自己解析出需要的 `wxauth-token` + `cf_clearance`，**其余 cookie 自动忽略**。

```bash
panhub init
# → 提示 "paste cookie string:"
# → 粘贴 → 回车 → 写入 ~/.panhub/credentials.json (mode 600)
# → panhub auth-check 验证
```

### 脚本 / agent 用法（无交互）

```bash
# 方式 1：cookie 文件
echo "wxauth-token=...; cf_clearance=..." > /tmp/panhub.cookie
panhub init --cookie-file /tmp/panhub.cookie --no-prompt
rm /tmp/panhub.cookie

# 方式 2：环境变量（cron 友好）
export PANHUB_COOKIE='wxauth-token=...; cf_clearance=...'
panhub init --no-prompt
```

### 高级：分开填字段（默认 UA 不适合你时才用）

如果你的 `cf_clearance` 来自一个 UA 跟默认 Chrome 152 / macOS 不同的浏览器：

```bash
panhub init --advanced
# 依次输入 wxauth-token / cf_clearance / user-agent
```

或者手动创建 `~/.panhub/credentials.json`（然后 `chmod 600`）：

```json
{
  "wxauth_token": "oXXXXX...XXX.1787932820.XXXXX...",
  "cf_clearance": "W_ys_6vlizG0Kgn8...XXX",
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
}
```

> **为什么 UA 默认是固定的？** Cloudflare 把 `cf_clearance` 绑定到颁发时的浏览器指纹（UA + IP + TLS）。**随机切换 UA 只会触发风控** — UA 必须跟拿 `cf_clearance` 的那个浏览器一致。默认值覆盖最常见的 Chrome/macOS 场景；不一致时才需要 override。

### 凭据寿命

| 凭据 | 寿命 | 失效后 |
|---|---|---|
| `cf_clearance` | Cloudflare 默认 30 天 | 重新打开网页过一次 Turnstile |
| `wxauth-token` | 关注态保持即有效；HMAC 段是会话级密钥签的 | 取关公众号、或服务器换密钥 → 重新关注 + 重新登录 |

`panhub auth-check` 命令会探测凭据有效性，过期时清晰报错。

## 快速开始（30 秒）

```bash
# 1. 装
pip install panhub-cli

# 2. 粘 cookie 一次性配置（从 DevTools Console 跑 document.cookie，复制整行）
panhub init

# 3. 搜
panhub search "三体" --limit 5
```

## 用法

```bash
# 搜索（默认 JSON 输出到 stdout）
panhub search "三体"
panhub search "三体" --source baidu,quark  # 指定网盘源
panhub search "三体" --limit 20            # 限制结果数

# 健康检查（公开端点，无需凭据）
panhub health

# 鉴权检查（探测 wxauth-token + cf_clearance 是否仍有效）
panhub auth-check

# 凭据初始化（首次使用或刷新 cookie）
panhub init                                  # 粘一行 document.cookie
panhub init --advanced                       # 分开填三个字段
panhub init --cookie-file /tmp/cookie.txt    # 脚本无交互模式
PANHUB_COOKIE='...' panhub init --no-prompt  # 环境变量

# 热搜 / 榜单（如果线上站提供）
panhub hot
panhub trending
```

### JSON 输出格式

```json
{
  "query": "三体",
  "total": 18,
  "sources": ["aliyun", "xunlei", "baidu", "quark"],
  "results": [
    {
      "source": "aliyun",
      "url": "https://www.aliyundrive.com/s/...",
      "password": "",
      "note": "三体 (2023) 全三季",
      "datetime": "2025-09-16T11:15:52+08:00"
    }
  ]
}
```

## 架构

```
┌────────────────┐    HTTPS + SSE     ┌──────────────────────────┐
│   panhub CLI   │ ─────────────────► │ panhub.shenzjd.com       │
│   (本机)       │  wxauth-token      │  /api/search.stream      │
│                │  cf_clearance      │  ↑ Cloudflare 边缘       │
│                │  browser headers   │  ↑ Turnstile 验证        │
└────────────────┘                    └──────────────────────────┘
```

**关键洞察**：PanHub 本身的鉴权极弱（不验证任何 token），真正的"防 agent 门槛"是 **Cloudflare**。`cf_clearance` + `wxauth-token` + 完整浏览器头三件套足以匿名 server-to-server 调用。

## 适用 / 不适用

| 场景 | 适合 |
|---|---|
| 在终端 / 脚本里跑网盘搜索 | ✅ |
| 让 AI agent 调 PanHub 搜索 | ✅ |
| 高频次 / 高并发爬取 | ❌ 会被 Cloudflare 限流 |
| 商业用途 | ❌ PanHub 仓库禁止 |

## 致谢

- [PanHub](https://github.com/wu529778790/panhub.shenzjd.com) — 原项目，MIT
- 本项目非 PanHub 官方，由社区封装

## License

MIT
