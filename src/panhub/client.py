"""HTTP client + SSE parser for PanHub's streaming search endpoint.

PanHub's /api/search.stream returns Server-Sent Events. Each event looks like:

    event: chunk
    data: {"done":1,"total":18,"merged":{...}}

The `merged` field is a map from source name (e.g. "baidu", "quark") to a
list of result objects. Each result object has:

    {
      "url": "https://...",
      "password": "xxxx" or "",
      "note": "human-readable title",
      "datetime": "ISO-8601 timestamp"
    }

The stream also sends a final `event: end` marker, which we use to know
when to stop reading.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .config import (
    CLOUDFLARE_BOT_MESSAGE,
    CLOUDFLARE_BOT_STATUS,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_S,
    HEALTH_PATH,
    SEARCH_STREAM_PATH,
)
from .credentials import Credentials

# SSE event field names
_EVENT_CHUNK = "chunk"
_EVENT_END = "end"
_EVENT_ERROR = "error"


class PanHubError(Exception):
    """Base error for PanHub CLI."""


class AuthError(PanHubError):
    """Credentials rejected (Cloudflare bot forbidden, expired token, etc.).

    The user needs to refresh cookies via `panhub init`.
    """


class NetworkError(PanHubError):
    """Connection / HTTP transport error."""


@dataclass
class SearchResult:
    """A single netdisk search hit, normalized across sources."""

    source: str
    url: str
    password: str
    note: str
    datetime: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "url": self.url,
            "password": self.password,
            "note": self.note,
            "datetime": self.datetime,
        }


@dataclass
class SearchResponse:
    """Full result of a search query."""

    query: str
    total: int
    results: list[SearchResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        sources = sorted({r.source for r in self.results})
        return {
            "query": self.query,
            "total": self.total,
            "sources": sources,
            "results": [r.to_dict() for r in self.results],
        }


def _build_request(
    creds: Credentials,
    query: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    sources: list[str] | None = None,
) -> urllib.request.Request:
    """Build the urllib request for the streaming search endpoint."""
    url = f"{base_url.rstrip('/')}{SEARCH_STREAM_PATH}"
    qs_parts = [f"kw={urllib.parse.quote(query)}", "res=merge"]
    if sources:
        # PanHub accepts ?channels=... but that field is for plugin source
        # selection; for the merged /api/search endpoint we pass cloud_types
        # which is the user-facing filter for netdisk types.
        qs_parts.append("cloud_types=" + ",".join(sources))
    url = f"{url}?{'&'.join(qs_parts)}"

    req = urllib.request.Request(url, method="GET")
    req.add_header("accept", "text/event-stream")
    req.add_header("accept-language", "zh,en-US;q=0.9,en;q=0.8")
    req.add_header("cache-control", "no-cache")
    req.add_header("cookie", creds.cookie_header())
    req.add_header("pragma", "no-cache")
    req.add_header("referer", f"{base_url.rstrip('/')}/")
    req.add_header(
        "sec-ch-ua", '"Not?A_Brand";v="24", "Chromium";v="152"'
    )
    req.add_header("sec-ch-ua-mobile", "?0")
    req.add_header("sec-ch-ua-platform", '"macOS"')
    req.add_header("sec-fetch-dest", "empty")
    req.add_header("sec-fetch-mode", "cors")
    req.add_header("sec-fetch-site", "same-origin")
    req.add_header("user-agent", creds.user_agent)
    return req


def _parse_sse(stream: Iterator[bytes]) -> Iterator[dict[str, Any]]:
    """Parse a byte stream of SSE events into `data` payloads.

    Handles:
      - `event:` field (we care about chunk / end / error)
      - `data:` field (one line = one payload, may be multi-line per spec but
        PanHub uses single-line JSON)
      - blank-line event separators
      - comment lines starting with `:`
      - retry / id fields are ignored

    Yields each `data:` payload as a parsed JSON object, wrapped with the
    event name under the `__event__` key.
    """
    current_event: str | None = None
    data_buf: list[str] = []
    for raw_line in stream:
        # SSE spec: lines are separated by \n, \r, or \r\n. Decode and strip.
        try:
            line = raw_line.decode("utf-8").rstrip("\r\n")
        except UnicodeDecodeError:
            # Skip lines that aren't valid UTF-8 (rare, but possible mid-stream).
            continue
        if not line:
            # Blank line = dispatch the current event
            if data_buf:
                payload_text = "\n".join(data_buf)
                data_buf = []
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    # Non-JSON data: wrap as opaque
                    payload = {"_raw": payload_text}
                yield {"__event__": current_event or "message", "data": payload}
            current_event = None
            continue
        if line.startswith(":"):
            # Comment / heartbeat
            continue
        if ":" in line:
            field_name, _, value = line.partition(":")
            # Per spec, strip a single leading space after the colon
            if value.startswith(" "):
                value = value[1:]
            if field_name == "event":
                current_event = value
            elif field_name == "data":
                data_buf.append(value)
            # `id:` and `retry:` are ignored
        else:
            # Field name with no value (treated as field name with empty value)
            if line == "event":
                current_event = ""
    # Trailing partial event (no terminating blank line) — flush
    if data_buf:
        payload_text = "\n".join(data_buf)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = {"_raw": payload_text}
        yield {"__event__": current_event or "message", "data": payload}


def search(
    query: str,
    creds: Credentials,
    *,
    base_url: str = DEFAULT_BASE_URL,
    sources: list[str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> SearchResponse:
    """Run a search and return the merged, deduplicated results.

    Args:
        query: Search keyword.
        creds: Loaded credentials.
        base_url: Override for self-hosted deployments (default: panhub.shenzjd.com).
        sources: Optional list of netdisk source names to filter by
            (e.g. ["baidu", "quark"]).
        timeout_s: Total request timeout in seconds. PanHub's stream can take
            5-10s as plugins complete; default 30s is generous.

    Returns:
        SearchResponse with the merged results.

    Raises:
        AuthError: If Cloudflare returns 403 "bot forbidden" — credentials
            need to be refreshed.
        NetworkError: On any other transport / HTTP error.
    """
    req = _build_request(creds, query, base_url=base_url, sources=sources)
    try:
        response = urllib.request.urlopen(req, timeout=timeout_s)  # noqa: S310
    except urllib.error.HTTPError as e:
        # Read the body to detect Cloudflare's specific message
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        if e.code == CLOUDFLARE_BOT_STATUS and CLOUDFLARE_BOT_MESSAGE in body:
            raise AuthError(
                "Cloudflare rejected the request as a bot. "
                "Run `panhub init` to refresh credentials."
            ) from e
        raise NetworkError(
            f"HTTP {e.code} {e.reason}: {body[:200]}"
        ) from e
    except urllib.error.URLError as e:
        raise NetworkError(f"connection failed: {e.reason}") from e

    try:
        response_obj = SearchResponse(query=query, total=0)
        seen_total: int | None = None
        for event in _parse_sse(response):
            event_name = event.get("__event__")
            payload = event.get("data", {})
            if event_name == _EVENT_END:
                break
            if event_name == _EVENT_ERROR:
                raise PanHubError(f"server error event: {payload}")
            if event_name != _EVENT_CHUNK:
                continue
            # Track the total across chunks (it's repeated on each chunk)
            if isinstance(payload, dict) and "total" in payload:
                seen_total = int(payload["total"])
            merged = payload.get("merged", {}) if isinstance(payload, dict) else {}
            for source_name, items in merged.items():
                for item in items or []:
                    response_obj.results.append(
                        SearchResult(
                            source=source_name,
                            url=str(item.get("url", "")),
                            password=str(item.get("password", "")),
                            note=str(item.get("note", "")),
                            datetime=str(item.get("datetime", "")),
                        )
                    )
        if seen_total is not None:
            response_obj.total = seen_total
        return response_obj
    finally:
        response.close()


def health(*, base_url: str = DEFAULT_BASE_URL, timeout_s: float = 10.0) -> dict[str, Any]:
    """Call the public /api/health endpoint. No credentials required.

    Returns the parsed JSON body as a dict.
    """
    url = f"{base_url.rstrip('/')}{HEALTH_PATH}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise NetworkError(f"health check failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise NetworkError(f"health check failed: {e.reason}") from e
