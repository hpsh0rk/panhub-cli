"""Tests for panhub.credentials — file load, save, mode enforcement, masking.

These tests do NOT touch the real ~/.panhub/credentials.json. They use
pytest's `tmp_path` fixture to write to a temporary directory, and monkey-
patch CREDENTIALS_DIR / CREDENTIALS_FILE.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from panhub import credentials as creds_mod
from panhub.config import DEFAULT_USER_AGENT
from panhub.credentials import (
    Credentials,
    CredentialsError,
    _mask,
    load,
    parse_cookie_string,
    save,
)


@pytest.fixture
def creds_path(tmp_path, monkeypatch) -> Path:
    """Redirect CREDENTIALS_FILE/CREDENTIALS_DIR to a temp location."""
    p = tmp_path / "credentials.json"
    monkeypatch.setattr(creds_mod, "CREDENTIALS_FILE", p)
    monkeypatch.setattr(creds_mod, "CREDENTIALS_DIR", tmp_path)
    # ensure_dir uses CREDENTIALS_DIR, which is already tmp_path — but
    # .mkdir(exist_ok=True) on the tmp_path itself is harmless.
    return p


def test_mask_short_value_fully_hidden() -> None:
    assert _mask("") == "***"
    assert _mask("abc") == "***"  # 3 chars < keep=6


def test_mask_long_value_keeps_prefix() -> None:
    masked = _mask("abcdefghij")
    assert masked == "abcdef***"
    assert "ghij" not in masked


def test_save_writes_file_with_0600(creds_path) -> None:
    save(Credentials(wxauth_token="wx.123.abc", cf_clearance="cf.456.def", user_agent="UA"))
    assert creds_path.exists()
    mode = stat.S_IMODE(creds_path.stat().st_mode)
    assert mode == 0o600


def test_save_writes_all_three_fields(creds_path) -> None:
    save(Credentials(wxauth_token="wx.123", cf_clearance="cf.456", user_agent="UA"))
    data = json.loads(creds_path.read_text())
    assert data["wxauth_token"] == "wx.123"
    assert data["cf_clearance"] == "cf.456"
    assert data["user_agent"] == "UA"


def test_load_round_trip(creds_path) -> None:
    original = Credentials(wxauth_token="wx.123.abc", cf_clearance="cf.456.def", user_agent="UA")
    save(original)
    loaded = load()
    assert loaded == original


def test_load_missing_file_raises(creds_path) -> None:
    with pytest.raises(CredentialsError, match="not found"):
        load()


def test_load_wrong_mode_raises(creds_path) -> None:
    save(Credentials(wxauth_token="wx", cf_clearance="cf", user_agent="UA"))
    creds_path.chmod(0o644)
    with pytest.raises(CredentialsError, match="mode"):
        load()


def test_load_invalid_json_raises(creds_path) -> None:
    creds_path.write_text("not json")
    creds_path.chmod(0o600)
    with pytest.raises(CredentialsError, match="not valid JSON"):
        load()


def test_load_missing_required_field_raises(creds_path) -> None:
    creds_path.write_text(json.dumps({"wxauth_token": "wx"}))  # missing cf_clearance
    creds_path.chmod(0o600)
    with pytest.raises(CredentialsError, match="cf_clearance"):
        load()


def test_load_uses_default_user_agent_when_missing(creds_path) -> None:
    creds_path.write_text(json.dumps({"wxauth_token": "wx", "cf_clearance": "cf"}))
    creds_path.chmod(0o600)
    loaded = load()
    assert loaded.user_agent == DEFAULT_USER_AGENT


def test_save_refuses_to_overwrite_loose_perms(creds_path) -> None:
    save(Credentials(wxauth_token="wx", cf_clearance="cf", user_agent="UA"))
    creds_path.chmod(0o644)
    with pytest.raises(CredentialsError, match="mode"):
        save(Credentials(wxauth_token="new", cf_clearance="new", user_agent="UA"))


def test_safe_summary_masks_secrets_but_keeps_ua(creds_path) -> None:
    c = Credentials(
        wxauth_token="abcdefghijklmnop", cf_clearance="qrstuvwxyz0123456", user_agent="UA"
    )
    s = c.safe_summary()
    assert s["wxauth_token"].startswith("abcdef")
    assert "ghij" not in s["wxauth_token"]
    assert s["cf_clearance"].startswith("qrstuv")
    assert s["user_agent"] == "UA"  # UA is not masked


def test_cookie_header_format() -> None:
    c = Credentials(wxauth_token="WX", cf_clearance="CF", user_agent="UA")
    assert c.cookie_header() == "wxauth-token=WX; cf_clearance=CF"


# ----- parse_cookie_string -----

def test_parse_cookie_string_full_panhub_payload() -> None:
    """The exact shape users will paste from document.cookie."""
    raw = (
        "wxauth-token=REDACTED"
        "REDACTED; "
        "cf_clearance=REDACTED"
        "-1787933859-1.2.1.1-gF4.J6EcV7W0j6pHidtA2_jpfD1mxh5LsTuiDz9i6P7YK"
    )
    parsed = parse_cookie_string(raw)
    assert parsed["wxauth-token"].startswith("o86ECwVFUX2nN0yv")
    assert parsed["cf_clearance"].startswith("W_ys_6vlizG0Kgn8")


def test_parse_cookie_string_ignores_other_cookies() -> None:
    raw = (
        "cf_clearance=CF_VALUE; "
        "_ga=GA1.2.1234567890.1234567890; "
        "theme=dark; "
        "wxauth-token=WX_VALUE"
    )
    parsed = parse_cookie_string(raw)
    # We only get the two we need, others dropped silently
    assert set(parsed.keys()) == {"wxauth-token", "cf_clearance"}
    assert parsed["wxauth-token"] == "WX_VALUE"
    assert parsed["cf_clearance"] == "CF_VALUE"


def test_parse_cookie_string_tolerates_trailing_semicolon() -> None:
    raw = "wxauth-token=WX; cf_clearance=CF; "
    parsed = parse_cookie_string(raw)
    assert parsed["wxauth-token"] == "WX"


def test_parse_cookie_string_tolerates_leading_whitespace() -> None:
    raw = "  wxauth-token=WX; cf_clearance=CF"
    parsed = parse_cookie_string(raw)
    assert parsed["wxauth-token"] == "WX"


def test_parse_cookie_string_missing_wxauth_raises() -> None:
    raw = "cf_clearance=CF; theme=dark"
    with pytest.raises(CredentialsError, match="wxauth-token"):
        parse_cookie_string(raw)


def test_parse_cookie_string_missing_cf_clearance_raises() -> None:
    raw = "wxauth-token=WX; theme=dark"
    with pytest.raises(CredentialsError, match="cf_clearance"):
        parse_cookie_string(raw)


def test_parse_cookie_string_empty_raises() -> None:
    with pytest.raises(CredentialsError, match="empty"):
        parse_cookie_string("")
    with pytest.raises(CredentialsError, match="empty"):
        parse_cookie_string("   ")


def test_parse_cookie_string_lists_what_was_found() -> None:
    """The error should help the user diagnose what went wrong."""
    raw = "theme=dark; lang=zh"
    with pytest.raises(CredentialsError) as excinfo:
        parse_cookie_string(raw)
    msg = str(excinfo.value)
    assert "wxauth-token" in msg
    assert "cf_clearance" in msg
    assert "theme" in msg  # Shows what WAS found


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
