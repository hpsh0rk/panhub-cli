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
import sys
from typing import NoReturn

from . import __version__
from .client import (
    AuthError,
    NetworkError,
    PanHubError,
    health,
    search,
)
from .config import DEFAULT_BASE_URL
from .credentials import (
    CREDENTIALS_FILE,
    Credentials,
    CredentialsError,
    load,
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


def cmd_init(args: argparse.Namespace) -> int:
    """Interactive credential setup.

    Prompts the user to paste three values, with input hidden to discourage
    shoulder-surfing. Writes ~/.panhub/credentials.json with mode 0600.

    We deliberately do NOT log the typed values; once written, they live
    only in the credentials file.
    """
    import getpass  # noqa: PLC0415

    _err("Setting up PanHub credentials.")
    _err("Get these from your browser DevTools after logging in:")
    _err("  - wxauth-token  (cookie value)")
    _err("  - cf_clearance  (cookie value)")
    _err("  - User-Agent    (navigator.userAgent in console)")
    _err("")

    try:
        wxauth = getpass.getpass("wxauth-token: ").strip()
        cf = getpass.getpass("cf_clearance: ").strip()
        ua = input("user-agent (press Enter for default Chrome 152 macOS): ").strip()
    except (EOFError, KeyboardInterrupt):
        _err("aborted")
        return _USAGE_ERROR

    if not wxauth or not cf:
        _err("both wxauth-token and cf_clearance are required")
        return _USAGE_ERROR

    creds = Credentials(
        wxauth_token=wxauth,
        cf_clearance=cf,
        user_agent=ua or None,  # type: ignore[arg-type]
    )
    if creds.user_agent is None:
        from .config import DEFAULT_USER_AGENT  # noqa: PLC0415

        creds = Credentials(
            wxauth_token=creds.wxauth_token,
            cf_clearance=creds.cf_clearance,
            user_agent=DEFAULT_USER_AGENT,
        )

    try:
        save(creds)
    except CredentialsError as e:
        _err(str(e))
        return _AUTH_ERROR

    _err(f"wrote {CREDENTIALS_FILE} (mode 0600)")
    _err("Run `panhub auth-check` to verify.")
    return _OK


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
        "init", help="Interactively set up ~/.panhub/credentials.json."
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
