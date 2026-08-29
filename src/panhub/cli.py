"""CLI entry point for PanHub CLI.

Subcommands:
  search        — run a search query, emit JSON to stdout
  health        — call the public /api/health endpoint
  auth-check    — probe whether stored credentials are still valid
  init          — interactive setup of ~/.panhub/credentials.json

Run `panhub <subcommand> --help` for per-subcommand options.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import NoReturn

from . import __version__
from .client import (
    AuthError,
    NetworkError,
    PanHubError,
    health,
    search,
)
from .config import DEFAULT_BASE_URL, DEFAULT_USER_AGENT
from .credentials import (
    CREDENTIALS_FILE,
    Credentials,
    CredentialsError,
    load,
    parse_cookie_string,
    save,
)

# Exit codes
_OK = 0
_USAGE_ERROR = 2
_AUTH_ERROR = 3
_NETWORK_ERROR = 4
_SERVER_ERROR = 5


def _emit_json(obj: object) -> None:
    """Emit JSON to stdout, compact, UTF-8, with trailing newline.

    Errors go to stderr, not stdout, so this output stays clean for piping
    into `jq` or other agents.
    """
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _err(msg: str) -> None:
    """Write an error message to stderr (newline-terminated)."""
    sys.stderr.write(f"panhub: {msg}\n")
    sys.stderr.flush()


def cmd_search(args: argparse.Namespace) -> int:
    try:
        creds = load()
    except CredentialsError as e:
        _err(str(e))
        return _AUTH_ERROR

    try:
        result = search(
            args.query,
            creds,
            base_url=args.base_url,
            sources=args.source,
        )
    except AuthError as e:
        _err(str(e))
        return _AUTH_ERROR
    except NetworkError as e:
        _err(str(e))
        return _NETWORK_ERROR
    except PanHubError as e:
        _err(str(e))
        return _SERVER_ERROR

    if args.limit is not None and args.limit >= 0:
        result.results = result.results[: args.limit]

    _emit_json(result.to_dict())
    return _OK


def cmd_health(args: argparse.Namespace) -> int:
    try:
        info = health(base_url=args.base_url)
    except NetworkError as e:
        _err(str(e))
        return _NETWORK_ERROR
    _emit_json(info)
    return _OK


def cmd_auth_check(args: argparse.Namespace) -> int:
    """Probe whether the stored credentials are still valid.

    Strategy: do a low-cost search (kw="a") and check for AuthError.
    If we get AuthError → expired, user must re-init.
    If we get NetworkError → connectivity issue, not an auth problem.
    If we get results (even empty) → credentials are working.
    """
    try:
        creds = load()
    except CredentialsError as e:
        _err(str(e))
        return _AUTH_ERROR

    # Print masked credential summary first so users can verify the file
    # they're using is the one they think they're using.
    _emit_json(
        {
            "credentials_file": str(CREDENTIALS_FILE),
            "credentials": creds.safe_summary(),
            "status": "checking",
        }
    )
    try:
        result = search("a", creds, base_url=args.base_url, timeout_s=15.0)
    except AuthError as e:
        _emit_json(
            {
                "credentials_file": str(CREDENTIALS_FILE),
                "credentials": creds.safe_summary(),
                "status": "expired",
                "detail": str(e),
            }
        )
        return _AUTH_ERROR
    except NetworkError as e:
        _emit_json(
            {
                "credentials_file": str(CREDENTIALS_FILE),
                "credentials": creds.safe_summary(),
                "status": "network_error",
                "detail": str(e),
            }
        )
        return _NETWORK_ERROR
    _emit_json(
        {
            "credentials_file": str(CREDENTIALS_FILE),
            "credentials": creds.safe_summary(),
            "status": "ok",
            "probe_results": len(result.results),
        }
    )
    return _OK


def _prompt_advanced() -> Credentials:
    """Advanced (per-field) prompt. Used by `panhub init --advanced`."""
    import getpass  # noqa: PLC0415

    _err("Advanced setup: enter each value separately.")
    _err("  - wxauth-token : cookie value")
    _err("  - cf_clearance : cookie value")
    _err("  - user-agent   : your browser's User-Agent (optional)")
    _err("")

    try:
        wxauth = getpass.getpass("wxauth-token: ").strip()
        cf = getpass.getpass("cf_clearance: ").strip()
        ua = input(
            "user-agent (press Enter for default Chrome 152 macOS): "
        ).strip()
    except (EOFError, KeyboardInterrupt) as e:
        _err("aborted")
        raise CredentialsError("aborted") from e

    if not wxauth or not cf:
        raise CredentialsError(
            "both wxauth-token and cf_clearance are required"
        )
    return Credentials(
        wxauth_token=wxauth,
        cf_clearance=cf,
        user_agent=ua or DEFAULT_USER_AGENT,
    )


def _prompt_from_cookie() -> Credentials:
    """Default (paste-the-whole-cookie-string) prompt.

    Tells the user to copy `document.cookie` from DevTools Console and paste
    it on one line. Parses out wxauth-token + cf_clearance; ignores the rest.
    """
    _err("Setting up PanHub credentials.")
    _err("")
    _err("How to get your cookies (5 steps):")
    _err("  1. Open https://panhub.shenzjd.com and log in")
    _err("  2. Press F12 → Console tab")
    _err("  3. Type: document.cookie")
    _err("  4. Press Enter — copy the ENTIRE output line")
    _err("  5. Paste it below (input is hidden)")
    _err("")
    _err(
        "  (We only need wxauth-token + cf_clearance; "
        "everything else is ignored.)"
    )
    _err("")

    import getpass  # noqa: PLC0415

    try:
        cookie_str = getpass.getpass("paste cookie string: ")
    except (EOFError, KeyboardInterrupt) as e:
        _err("aborted")
        raise CredentialsError("aborted") from e

    parsed = parse_cookie_string(cookie_str)
    return Credentials(
        wxauth_token=parsed["wxauth-token"],
        cf_clearance=parsed["cf_clearance"],
        user_agent=DEFAULT_USER_AGENT,
    )


def cmd_init(args: argparse.Namespace) -> int:
    """Credential setup.

    Default flow (`panhub init`): paste a single cookie string from
    `document.cookie`. Easier than separating wxauth-token / cf_clearance.

    Advanced flow (`panhub init --advanced`): enter each value separately.

    Scripted flow (`panhub init --cookie-file <path>` or `--no-prompt`):
    read from a file or stdin, no interactive prompts. For cron / agents.
    """
    creds: Credentials

    try:
        if args.advanced:
            creds = _prompt_advanced()
        elif args.cookie_file is not None or args.no_prompt or not sys.stdin.isatty():
            # Non-interactive: read cookie string from file, stdin, or env.
            creds = _load_cookie_non_interactive(
                cookie_file=args.cookie_file, no_prompt=args.no_prompt
            )
        else:
            creds = _prompt_from_cookie()
    except CredentialsError as e:
        _err(str(e))
        return _AUTH_ERROR if "aborted" not in str(e) else _USAGE_ERROR

    try:
        save(creds)
    except CredentialsError as e:
        _err(str(e))
        return _AUTH_ERROR

    summary = creds.safe_summary()
    _err(f"wrote {CREDENTIALS_FILE} (mode 0600)")
    _err(
        f"  wxauth_token = {summary['wxauth_token']}\n"
        f"  cf_clearance = {summary['cf_clearance']}\n"
        f"  user_agent   = {creds.user_agent}"
    )
    _err("Run `panhub auth-check` to verify.")
    return _OK


def _load_cookie_non_interactive(
    *, cookie_file: str | None, no_prompt: bool
) -> Credentials:
    """Resolve a cookie string from --cookie-file, $PANHUB_COOKIE, or stdin.

    Precedence:
      1. `--cookie-file <path>` argument
      2. $PANHUB_COOKIE environment variable
      3. stdin (read all, strip whitespace)

    `--no-prompt` is accepted for clarity; it has no extra effect since
    non-TTY stdin is auto-detected.
    """
    cookie_str: str | None = None
    source: str = ""

    if cookie_file:
        p = Path(cookie_file)
        if not p.exists():
            raise CredentialsError(f"--cookie-file not found: {p}")
        cookie_str = p.read_text(encoding="utf-8")
        source = f"file:{p}"

    if cookie_str is None:
        env_val = os.environ.get("PANHUB_COOKIE", "").strip()
        if env_val:
            cookie_str = env_val
            source = "env:PANHUB_COOKIE"

    if cookie_str is None and no_prompt:
        raise CredentialsError(
            "--no-prompt needs --cookie-file or $PANHUB_COOKIE"
        )

    if cookie_str is None:
        # Read from stdin
        cookie_str = sys.stdin.read()

    cookie_str = cookie_str.strip()
    if not cookie_str:
        raise CredentialsError("no cookie string provided (empty input)")

    parsed = parse_cookie_string(cookie_str)
    if source:
        _err(f"loaded cookie from {source}")
    return Credentials(
        wxauth_token=parsed["wxauth-token"],
        cf_clearance=parsed["cf_clearance"],
        user_agent=DEFAULT_USER_AGENT,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="panhub",
        description=(
            "Command-line interface for PanHub netdisk aggregator. "
            "All commands emit JSON to stdout. See README.md for setup."
        ),
    )
    p.add_argument(
        "--version", action="version", version=f"panhub {__version__}"
    )
    p.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"PanHub base URL (default: {DEFAULT_BASE_URL})",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # search
    sp_search = sub.add_parser(
        "search", help="Search netdisks. JSON to stdout."
    )
    sp_search.add_argument("query", help="Search keyword")
    sp_search.add_argument(
        "--source",
        action="append",
        default=None,
        help=(
            "Filter by netdisk source (repeatable, e.g. "
            "`--source baidu --source quark`)"
        ),
    )
    sp_search.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of results in the output",
    )
    sp_search.set_defaults(func=cmd_search)

    # health
    sp_health = sub.add_parser("health", help="Public health check (no creds).")
    sp_health.set_defaults(func=cmd_health)

    # auth-check
    sp_auth = sub.add_parser(
        "auth-check", help="Probe whether stored credentials are still valid."
    )
    sp_auth.set_defaults(func=cmd_auth_check)

    # init
    sp_init = sub.add_parser(
        "init",
        help=(
            "Set up ~/.panhub/credentials.json. Default: paste a single "
            "cookie string from browser DevTools."
        ),
    )
    sp_init.add_argument(
        "--advanced",
        action="store_true",
        help=(
            "Enter wxauth-token / cf_clearance / user-agent separately "
            "instead of pasting the whole cookie string."
        ),
    )
    sp_init.add_argument(
        "--cookie-file",
        metavar="PATH",
        default=None,
        help=(
            "Read cookie string from this file (for scripts / agents). "
            "Takes precedence over $PANHUB_COOKIE and stdin."
        ),
    )
    sp_init.add_argument(
        "--no-prompt",
        action="store_true",
        help=(
            "Refuse to prompt interactively. Use with --cookie-file or "
            "$PANHUB_COOKIE."
        ),
    )
    sp_init.set_defaults(func=cmd_init)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _entrypoint() -> NoReturn:
    """Shell-script entry point (bin/panhub)."""
    sys.exit(main())
