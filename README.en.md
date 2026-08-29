# panhub-cli

> A command-line interface for [PanHub](https://github.com/wu529778790/panhub.shenzjd.com) — aggregate netdisk search, agent-friendly JSON output, no node/browser required.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](.python-version)
[![PyPI](https://img.shields.io/pypi/v/panhub-cli.svg)](https://pypi.org/project/panhub-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero deps](https://img.shields.io/badge/dependencies-zero-green.svg)]()

## What it is

[PanHub](https://panhub.shenzjd.com) is a netdisk-aggregator search engine
(Quark / Aliyundrive / Baidu / 115 / Xunlei / Telegram channels, 18+ sources).
`panhub-cli` is a thin command-line wrapper:

- **`pip install panhub-cli` and you're done** (official PyPI package, Python 3.10+, zero runtime dependencies)
- **JSON to stdout** — designed for AI agents and shell scripts
- Supports `search`, `health`, `auth-check`, `init`
- **Works around Cloudflare "bot forbidden"** by reusing browser session cookies

## Install

```bash
# Option A: pip (recommended)
pip install panhub-cli
panhub search "documentary"

# Option B: source + symlink (zero deps, no pip, no sudo)
git clone https://github.com/hpsh0rk/panhub-cli.git
cd panhub-cli
mkdir -p ~/.local/bin
ln -sf "$(pwd)/bin/panhub" ~/.local/bin/panhub
panhub --version
```

> Behind CN mirrors, pip can hit SSL errors
> (`pip config set global.index-url https://pypi.org/simple/` switches to the
> official index), or just use Option B — `bin/panhub` is self-contained and
> needs only Python 3.10+.

**Requires**: Python 3.10+. No third-party dependencies.

## Credentials (one-time setup)

> ⚠️ **`wxauth-token` and `cf_clearance` are real session credentials.**
> Leaking them is equivalent to giving others long-term access to PanHub
> under your account. **Never** paste them into issues, chats, public repos,
> or anywhere that gets logged.

### Recommended: paste one cookie line (simplest)

`panhub init` defaults to this path — you only need **one line** of
`document.cookie`, no need to split fields yourself:

1. Open https://panhub.shenzjd.com and **finish login** (first time: scan the
   public-account QR on the page and follow it).
2. Press `F12` → **Console** tab
3. Type `document.cookie` and press Enter
4. Copy the **entire output line** (looks like
   `wxauth-token=...; cf_clearance=...; other=...`)
5. Run `panhub init` and paste it when prompted (input is hidden)

The CLI parses out the `wxauth-token` + `cf_clearance` it needs and
**silently ignores every other cookie**.

```bash
panhub init
# → prompt "paste cookie string:"
# → paste → Enter → writes ~/.panhub/credentials.json (mode 600)
# → panhub auth-check to verify
```

### Scripted / agent usage (non-interactive)

```bash
# Option 1: cookie file
echo "wxauth-token=...; cf_clearance=..." > /tmp/panhub.cookie
panhub init --cookie-file /tmp/panhub.cookie --no-prompt
rm /tmp/panhub.cookie

# Option 2: environment variable (cron-friendly)
export PANHUB_COOKIE='wxauth-token=...; cf_clearance=...'
panhub init --no-prompt
```

### Advanced: enter fields separately (only if the default UA doesn't fit you)

If your `cf_clearance` came from a browser whose UA differs from the default
Chrome 152 / macOS one:

```bash
panhub init --advanced
# enter wxauth-token / cf_clearance / user-agent one by one
```

Or create `~/.panhub/credentials.json` manually:

```json
{
  "wxauth_token": "oXXXXX...XXX.1787932820.XXXXX...",
  "cf_clearance": "W_ys_6vlizG0Kgn8...XXX",
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
}
```

Then `chmod 600 ~/.panhub/credentials.json`.

> **Why is the UA fixed by default?** Cloudflare binds `cf_clearance` to the
> browser fingerprint it was issued for (UA + IP + TLS). **Rotating random
> UAs only triggers the bot defense** — the UA must match the browser that
> obtained that `cf_clearance`. The default covers the common Chrome/macOS
> case; override only when it doesn't match yours.

### Credential lifetime

| Credential | Lifetime | When it breaks |
|---|---|---|
| `cf_clearance` | Cloudflare default 30 days | Reopen the page to redo Turnstile |
| `wxauth-token` | Valid while you keep following the public account; HMAC part is server-side session-key signed | Unfollow the account, or server rotates its key |

Run `panhub auth-check` to detect expired credentials.

## Quickstart (30 seconds)

```bash
# 1. install
pip install panhub-cli

# 2. one-time credential setup (paste `document.cookie` from DevTools Console)
panhub init

# 3. search
panhub search "三体" --limit 5
```

## Usage

```bash
# Search (JSON to stdout by default)
panhub search "三体"                          # basic
panhub search "三体" --source baidu,quark     # filter by source
panhub search "三体" --limit 20               # cap results

# Public health check (no credentials needed)
panhub health

# Probe whether stored credentials are still valid
panhub auth-check

# Credential setup (one-time, or to refresh expired cookies)
panhub init                                  # paste one cookie line (default)
panhub init --advanced                       # enter each field separately
panhub init --cookie-file /tmp/cookie.txt    # scripted, non-interactive
PANHUB_COOKIE='...' panhub init --no-prompt  # from env var

# Hot search / trending (if upstream provides them)
panhub hot
panhub trending
```

### JSON shape

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
      "note": "三体 (2023) full trilogy",
      "datetime": "2025-09-16T11:15:52+08:00"
    }
  ]
}
```

## Architecture

```
┌────────────────┐    HTTPS + SSE     ┌──────────────────────────┐
│   panhub CLI   │ ─────────────────► │ panhub.shenzjd.com       │
│   (local)      │  wxauth-token      │  /api/search.stream      │
│                │  cf_clearance      │  ↑ Cloudflare edge       │
│                │  browser headers   │  ↑ Turnstile validation  │
└────────────────┘                    └──────────────────────────┘
```

**Key insight**: PanHub itself does almost no auth (it doesn't validate any
token). The real "anti-agent gate" is **Cloudflare**. The trio of
`cf_clearance` + `wxauth-token` + complete browser headers is enough for
anonymous server-to-server calls.

## When to use / not to use

| Scenario | OK? |
|---|---|
| Searching netdisks from terminal / script | ✅ |
| Letting an AI agent call PanHub search | ✅ |
| High-frequency / high-concurrency scraping | ❌ Cloudflare will rate-limit |
| Commercial use | ❌ PanHub's repo forbids it |

## Credits

- [PanHub](https://github.com/wu529778790/panhub.shenzjd.com) — original project, MIT
- This CLI is a community wrapper, not affiliated with PanHub

## License

MIT
