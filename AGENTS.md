# AGENT_GUIDE.md — for AI agents helping users run panhub-cli

> This file is for AI assistants (Claude, Cursor, Cody, Aider, etc.) helping
> a user install, configure, and use `panhub-cli`. It is NOT developer
> documentation — for that, see the source code, tests, and `pyproject.toml`.
> Don't repeat what `README.md` already says; assume the agent has read it.

## What this tool is, in one sentence

`panhub-cli` is a Python CLI that calls [PanHub](https://panhub.shenzjd.com)'s
private search API on behalf of a logged-in user, returning JSON of netdisk
links. It exists because the public PanHub site is hard for agents to call
directly (Cloudflare bot challenge, no public auth API).

## How to recognize a user who should use it

Trigger this workflow if the user asks any of:

- "Search netdisks / 网盘 / 夸克 / 阿里云盘 / 百度网盘 for X"
- "Find a download link for 资源 / 纪录片 / 电视剧 ..."
- "I want to script / automate netdisk searches"
- "Help me set up panhub / panhub-cli"

**Do NOT** trigger if the user is asking about the upstream PanHub website
itself, the PanHub source code on GitHub, or commercial use (forbidden by
PanHub's license).

## Three-minute user onboarding (recommended script)

When a user wants to use `panhub-cli`, walk them through this in order. Do
**not** skip steps — the credential setup is the part users get stuck on.

### Step 1 — Install

```bash
pip install panhub-cli
panhub --version   # should print: panhub 0.1.0 (or later)
```

If `pip install` fails on SSL (common behind CN corporate mirrors):
```bash
pip install -i https://pypi.org/simple/ panhub-cli
```

Or skip pip entirely with a source symlink:
```bash
git clone https://github.com/hpsh0rk/panhub-cli.git
ln -sf "$(pwd)/panhub-cli/bin/panhub" ~/.local/bin/panhub
panhub --version
```

### Step 2 — One-time credential setup

**Always** default to the "paste one cookie line" flow. It is dramatically
easier than asking the user to split cookies themselves.

Walk them through, with exact instructions they can follow:

1. Open https://panhub.shenzjd.com in their browser
2. Log in if they haven't (first-time: scan the QR code to follow the WeChat
   public account — this is required, there's no way around it)
3. Press `F12` to open DevTools
4. Click the **Console** tab
5. Type `document.cookie` and press Enter
6. **Copy the entire output line** — it looks like
   `wxauth-token=oXXXX...; cf_clearance=YYYY...; other_cookie=...`
7. Run `panhub init` and paste when prompted (input is hidden, that's
   normal — they will not see what they type)

If they prefer a non-interactive flow (scripting, cron), suggest:
```bash
echo "wxauth-token=...; cf_clearance=..." > /tmp/panhub.cookie
panhub init --cookie-file /tmp/panhub.cookie
rm /tmp/panhub.cookie
```

### Step 3 — Verify

```bash
panhub health          # should return status: ok, ~6 plugins
panhub auth-check      # should return status: ok
panhub search "测试" --limit 3   # should return JSON
```

If any of these fail, jump to "Troubleshooting" below.

## How to call it from a script / agent

`panhub` outputs clean JSON to stdout and errors to stderr. Exit codes:
- `0` = success
- `2` = usage error (bad arguments)
- `3` = auth error (credentials missing / expired)
- `4` = network error
- `5` = server error

So agents can safely do:
```bash
panhub search "$QUERY" --limit 10 | jq -r '.results[] | "\(.source)\t\(.url)\t\(.password)"'
```

A full result has this shape:
```json
{
  "query": "三体",
  "total": 18,
  "sources": ["quark", "xunlei"],
  "results": [
    {
      "source": "quark",
      "url": "https://pan.quark.cn/s/...",
      "password": "abc1",   // empty string "" means no password
      "note": "三体 全30集 4K",
      "datetime": "2025-09-16T11:15:52+08:00"
    }
  ]
}
```

## Common user requests and how to handle them

### "只搜夸克网盘" / "only Quark results"

```bash
panhub search "三体" --source quark --limit 20
```

`--source` is repeatable for multiple sources:
```bash
panhub search "三体" --source quark --source baidu
```

**IMPORTANT caveat to mention to the user**: `--source` is **client-side**
filtering. The PanHub server still queries all 18+ sources; the CLI just
filters the results before printing. This is faster for them but still
costs the same server-side work. If they need real server-side filtering,
that capability doesn't exist in PanHub's API as of 2026-08.

### "My cookies expired"

```bash
panhub auth-check
# If status: "expired":
panhub init   # re-paste a fresh cookie line
```

`cf_clearance` expires after ~30 days. `wxauth-token` expires if the user
unfollows the public account, or if PanHub rotates its server-side signing
key.

### "I want to script this in a cron / 定时任务"

```bash
PANHUB_COOKIE='wxauth-token=...; cf_clearance=...' panhub init --no-prompt
# Cron entry:
0 9 * * * PANHUB_COOKIE='...' /usr/local/bin/panhub search "最新资源" --limit 20 > /tmp/results.json
```

**Caveat**: Cloudflare may rate-limit high-frequency users. Don't poll
more than once per hour.

### "Can I get an API key instead of copying cookies?"

**No.** PanHub does not have a public API key system. Cookie-based auth is
the only option as of 2026-08. Don't waste the user's time looking for
something that doesn't exist.

### "How do I install on Windows?"

The pip install works on Windows. If they hit "command not found" after
install, `panhub` is in `%LOCALAPPDATA%\Programs\Python\Python3X\Scripts\`
— they need to add that to PATH, or use:
```cmd
py -m panhub search "三体"
```

## Troubleshooting — diagnose and fix

Always work through these in order. The first failing step tells you where
the problem is.

### `panhub: command not found`

The `panhub` executable isn't on PATH. Fix:
```bash
# Check if pip installed it
python3 -m pip show -f panhub-cli | grep -E "Location|panhub"
# If found, add the bin/ directory to PATH, e.g.:
export PATH="$(python3 -m site --user-base)/bin:$PATH"
```

### `panhub: /Users/.../credentials.json not found`

They never ran `panhub init`. Run it.

### `status: "expired"` from `auth-check`

Cookies are stale. Walk them through `panhub init` again. If it keeps
expiring within hours (not 30 days), PanHub may have rate-limited or
banned their IP / OpenID.

### `panhub: Cloudflare rejected the request as a bot`

This means `cf_clearance` is invalid OR the User-Agent doesn't match the
browser that got `cf_clearance`. Fix:
1. Re-run `panhub init` with a fresh cookie
2. Make sure they copied the cookie from the **same browser session**
   that the search will use (in practice: any modern Chrome works)

### `panhub: connection failed` / `network_error`

Network-level problem, not credentials. Check:
```bash
curl -I https://panhub.shenzjd.com/api/health
```
If that fails too, it's a DNS / firewall / proxy issue on the user's end.
Common cause: corporate proxies block Cloudflare-fronted sites.

### Empty results (`total: 0`)

The query has no matches, OR all sources are temporarily down. Try:
- A different, common query ("三体" usually has hits)
- `--limit 100` to see if any source returned anything
- Wait a few minutes and retry

## Hard rules when using this tool

These are not optional. Get them wrong and you'll either fail to help
the user or compromise their account.

1. **NEVER ask the user to paste their `wxauth-token` or `cf_clearance`
   into chat, an issue, a wiki, or anywhere that gets logged.** If they
   paste it, tell them to go refresh the cookie (reopen the page) before
   continuing, so the leaked value becomes useless.

2. **NEVER log the value of `wxauth_token` or `cf_clearance` in your
   own output.** If you must reference them, use only the first 6
   characters: `oXXXXX***`.

3. **NEVER modify `~/.panhub/credentials.json` outside of `panhub init`.**
   The file must stay mode 0600; the CLI enforces this.

4. **NEVER suggest using `--source` as a way to "be polite" to the
   server.** It doesn't reduce server load (see caveat above).

5. **NEVER offer to write a wrapper that stores credentials in a
   less-secure location** (env var committed to a repo, plaintext
   config, etc.). The CLI's design is intentional.

## Quick reference card

```
panhub search QUERY [--source NAME]... [--limit N]
panhub health
panhub auth-check
panhub init [--advanced] [--cookie-file PATH] [--no-prompt]
panhub --help
panhub --version
panhub --base-url URL <subcommand>     # for self-hosted PanHub
```

## Links

- PyPI: https://pypi.org/project/panhub-cli/
- GitHub: https://github.com/hpsh0rk/panhub-cli
- Upstream PanHub (the service this CLI calls): https://github.com/wu529778790/panhub.shenzjd.com
- Upstream PanHub (the website): https://panhub.shenzjd.com
