# panhub-cli

> 命令行版 PanHub 网盘聚合搜索 — 给 AI agent 和终端用户用的 JSON 友好接口。
>
> A command-line interface for [PanHub](https://github.com/wu529778790/panhub.shenzjd.com) — aggregate netdisk search, agent-friendly JSON output, no node/browser required.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](.python-version)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero deps](https://img.shields.io/badge/dependencies-zero-green.svg)]()

## 它是什么

[PanHub](https://panhub.shenzjd.com) 是一个网盘资源聚合搜索引擎（夸克 / 阿里云盘 / 百度 / 115 / 迅雷 / Telegram 频道等 18+ 源）。`panhub-cli` 是它的命令行封装：

- **纯 Python stdlib**，零外部依赖，`python3 panhub.py` 就能跑
- **JSON 输出**到 stdout，agent / 脚本可直接消费
- **支持搜索、健康检查、热搜、榜单**等命令
- **优雅解决 Cloudflare "bot forbidden"**：复用浏览器 cookie 即可

## 安装

```bash
git clone https://github.com/sh0rk/panhub-cli.git
cd panhub-cli

# 方式 A：直接用（推荐，零安装）
python3 bin/panhub search "纪录片 中东战争"

# 方式 B：pip install -e .（装到当前环境）
pip install -e .
panhub search "纪录片 中东战争"
```

**要求**：Python 3.10+，无第三方依赖。

## 凭据获取（首次使用必读）

> ⚠️ **重要：wxauth-token 和 cf_clearance 是真凭据**，泄漏等同于你的 PanHub 账号被他人长期使用。**绝不**在 issue / 聊天 / 公开仓库 / 任何会被日志记录的地方贴出来。

`panhub` 不会自动获取凭据 — 你需要从已登录 PanHub 的浏览器手动复制 2 个 cookie：

### 步骤

1. 打开 https://panhub.shenzjd.com 并**完成登录**（首次：扫描页面上的公众号二维码并关注）
2. 按 `F12` 打开 DevTools → `Application` 标签 → `Cookies` → `https://panhub.shenzjd.com`
3. 找到这两个值并复制：
   - **`wxauth-token`**（值是 `openid.timestamp.hmac_sig` 格式）
   - **`cf_clearance`**（Cloudflare 颁发的"已通过验证"凭证）
4. 同时复制你的浏览器 **`User-Agent`**（DevTools → `Console` → 输入 `navigator.userAgent`）

### 初始化

```bash
panhub init
# 交互提示你粘三个值：wxauth-token / cf_clearance / user-agent
# 写入 ~/.panhub/credentials.json (权限 600)
```

或者手动创建 `~/.panhub/credentials.json`：

```json
{
  "wxauth_token": "oXXXXX...XXX.1787932820.XXXXX...",
  "cf_clearance": "W_ys_6vlizG0Kgn8...XXX",
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
}
```

然后 `chmod 600 ~/.panhub/credentials.json`。

### 凭据寿命

| 凭据 | 寿命 | 失效后 |
|---|---|---|
| `cf_clearance` | Cloudflare 默认 30 天 | 重新打开网页过一次 Turnstile |
| `wxauth-token` | 关注态保持即有效；HMAC 段是会话级密钥签的 | 取关公众号、或服务器换密钥 → 重新关注 + 重新登录 |

`panhub auth-check` 命令会探测凭据有效性，过期时清晰报错。

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
