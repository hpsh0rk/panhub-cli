"""Credentials management for PanHub CLI.

Credentials are two Cloudflare/PanHub session cookies + a matching User-Agent
string, copied from a browser where the user has already logged in to
https://panhub.shenzjd.com.

Storage location: ~/.panhub/credentials.json
File mode: 0600 (owner read/write only) — checked on every load.

The CLI never logs credential values. The `safe_summary()` helper returns a
masked view suitable for `panhub auth-check` output.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DEFAULT_USER_AGENT

CREDENTIALS_DIR = Path.home() / ".panhub"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
REQUIRED_MODE = 0o600


class CredentialsError(Exception):
    """Raised when credentials are missing, malformed, or have wrong permissions."""


@dataclass(frozen=True)
class Credentials:
    """The three values needed to call PanHub's protected endpoints.

    Attributes:
        wxauth_token: Value of the `wxauth-token` cookie. Format:
            `<openid>.<timestamp>.<hmac_sig>`. Tied to the user's public-account
            follow state.
        cf_clearance: Value of the `cf_clearance` cookie. Cloudflare's
            "passed bot challenge" proof. Valid for ~30 days.
        user_agent: Browser User-Agent string. PanHub/Cloudflare use it as
            part of the fingerprint; using a UA that matches a current
            desktop browser reduces oddities.
    """

    wxauth_token: str
    cf_clearance: str
    user_agent: str

    def cookie_header(self) -> str:
        """Build the `Cookie:` header value for outbound requests."""
        return f"wxauth-token={self.wxauth_token}; cf_clearance={self.cf_clearance}"

    def safe_summary(self) -> dict[str, str]:
        """Return a masked view safe for printing / logging.

        Shows the prefix of each value (so users can verify they loaded the
        right file) without leaking the full secret.
        """
        return {
            "wxauth_token": _mask(self.wxauth_token),
            "cf_clearance": _mask(self.cf_clearance),
            "user_agent": self.user_agent,  # UA is not secret
        }


def _mask(value: str, *, keep: int = 6) -> str:
    """Mask a secret string: keep the first `keep` chars, replace the rest.

    >>> _mask("abcdefghij")
    'abcdef***'
    >>> _mask("short")
    'shor***'
    """
    if len(value) <= keep:
        return "***"
    return value[:keep] + "***"


def ensure_dir() -> Path:
    """Create ~/.panhub/ if missing, return the path. Idempotent."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    return CREDENTIALS_DIR


def save(creds: Credentials, *, path: Path | None = None) -> None:
    """Persist credentials to disk with 0600 permissions.

    Refuses to write if the destination file already has loose permissions —
    the user must `chmod 600` first. This guards against a stale, world-
    readable file getting overwritten with new secrets.

    `path` defaults to the current value of `CREDENTIALS_FILE` (read at call
    time so monkeypatching in tests works).
    """
    if path is None:
        path = CREDENTIALS_FILE
    ensure_dir()
    if path.exists():
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != REQUIRED_MODE:
            raise CredentialsError(
                f"{path} has mode {oct(mode)}; must be {oct(REQUIRED_MODE)}. "
                f"Run: chmod 600 {path}"
            )
    payload: dict[str, Any] = {
        "wxauth_token": creds.wxauth_token,
        "cf_clearance": creds.cf_clearance,
        "user_agent": creds.user_agent,
    }
    # Write to a temp file in the same directory, then atomically rename.
    # This avoids leaving a half-written file with the wrong mode if the
    # process is killed mid-write. We use ".json.tmp" (NOT .with_suffix) so
    # that the original .json suffix is preserved if the rename is ever
    # changed; and the temp lives next to the target (same dir = same fs).
    tmp = path.parent / (path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, REQUIRED_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    # Defensive: if umask is weird, force the mode again.
    os.chmod(path, REQUIRED_MODE)


def load(*, path: Path | None = None) -> Credentials:
    """Load credentials from disk. Validates file mode is 0600.

    Raises CredentialsError if the file is missing, malformed, or has loose
    permissions. `path` defaults to the current value of `CREDENTIALS_FILE`
    (read at call time so monkeypatching in tests works).
    """
    if path is None:
        path = CREDENTIALS_FILE
    if not path.exists():
        raise CredentialsError(
            f"{path} not found. Run `panhub init` to set up credentials."
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != REQUIRED_MODE:
        raise CredentialsError(
            f"{path} has mode {oct(mode)}; must be {oct(REQUIRED_MODE)}. "
            f"Run: chmod 600 {path}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CredentialsError(f"{path} is not valid JSON: {e}") from e

    try:
        return Credentials(
            wxauth_token=str(data["wxauth_token"]),
            cf_clearance=str(data["cf_clearance"]),
            user_agent=str(data.get("user_agent") or DEFAULT_USER_AGENT),
        )
    except KeyError as e:
        raise CredentialsError(
            f"{path} is missing required field: {e.args[0]!r}. "
            f"Required: wxauth_token, cf_clearance. Optional: user_agent."
        ) from e
