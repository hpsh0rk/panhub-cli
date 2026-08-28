"""Tests for the SSE parser in panhub.client._parse_sse.

These tests do NOT make network calls — they feed the parser pre-captured
SSE byte streams (tests/fixtures/sample_sse*.txt) and check the parsed
events. This is the most failure-prone code path (raw byte stream → JSON
dicts), so unit testing it without network is the right move.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from panhub.client import _parse_sse

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> list[dict]:
    """Load a fixture, parse it through the SSE parser, return the events.

    The fixture file is a text SSE stream; we split it on newlines and feed
    each line as a separate byte chunk. This mirrors what urllib does
    line-by-line over the underlying socket.
    """
    text = (FIXTURES / name).read_text()
    return list(_parse_sse(line.encode("utf-8") for line in text.splitlines()))


def test_basic_sse_parsing_yields_three_events_plus_end() -> None:
    """A minimal SSE stream yields 4 events: 3 chunks + 1 end."""
    events = _load_fixture("sample_sse.txt")
    event_names = [e["__event__"] for e in events]
    assert event_names == ["chunk", "chunk", "chunk", "end"]


def test_first_chunk_has_empty_merged() -> None:
    events = _load_fixture("sample_sse.txt")
    assert events[0]["__event__"] == "chunk"
    assert events[0]["data"]["done"] == 1
    assert events[0]["data"]["total"] == 18
    assert events[0]["data"]["merged"] == {}


def test_second_chunk_contains_aliyun_result() -> None:
    events = _load_fixture("sample_sse.txt")
    payload = events[1]["data"]
    assert "aliyun" in payload["merged"]
    item = payload["merged"]["aliyun"][0]
    assert item["url"] == "https://www.aliyundrive.com/s/9c4FBnb65Cs"
    assert item["password"] == ""
    assert item["note"] == "test"


def test_third_chunk_contains_baidu_result() -> None:
    events = _load_fixture("sample_sse.txt")
    payload = events[2]["data"]
    assert "baidu" in payload["merged"]
    item = payload["merged"]["baidu"][0]
    assert item["password"] == "xhzs"


def test_end_event_is_last_and_distinct() -> None:
    events = _load_fixture("sample_sse.txt")
    assert events[-1]["__event__"] == "end"


def test_heartbeat_comment_lines_are_skipped() -> None:
    """A `: heartbeat` line between events must not become a parsed event."""
    events = _load_fixture("sample_sse_with_heartbeat.txt")
    # Expected: 2 chunks + 1 end, no spurious events from the comment.
    event_names = [e["__event__"] for e in events]
    assert event_names == ["chunk", "chunk", "end"]
    # And the second chunk should still have the quark result.
    assert "quark" in events[1]["data"]["merged"]


def test_empty_stream_yields_no_events() -> None:
    """Defensive: parsing an empty byte stream should produce nothing, not crash."""
    events = list(_parse_sse(iter([b""])))
    assert events == []


def test_sse_parser_handles_crlf_line_endings() -> None:
    """Real HTTP responses often use \\r\\n; the parser must strip both.

    Note: Python's `splitlines()` already handles \\r\\n, so the main risk
    is that .decode + .rstrip("\r\n") leaves a stray \\r on lines split
    with raw \r. We test that path explicitly here.
    """
    # Feed two lines, one with trailing \r, one blank — should produce 1 event
    events = list(
        _parse_sse(
            iter([b"event: chunk\r", b"data: {\"done\":1,\"merged\":{}}\r\n", b"\r\n"])
        )
    )
    assert len(events) == 1
    assert events[0]["__event__"] == "chunk"
    assert events[0]["data"]["done"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
