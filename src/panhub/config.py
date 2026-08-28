"""Constants for PanHub CLI.

Centralized so the base URL and default browser fingerprint are easy to find
and override in tests.
"""

from __future__ import annotations

# Public PanHub instance. Override via PANHUB_BASE_URL env var for tests
# or self-hosted deployments.
DEFAULT_BASE_URL = "https://panhub.shenzjd.com"

# Endpoint paths. /api/search.stream is the SSE endpoint that streams merged
# results as plugins complete; /api/search is the non-streaming variant.
SEARCH_STREAM_PATH = "/api/search.stream"
SEARCH_PATH = "/api/search"
HEALTH_PATH = "/api/health"

# Default User-Agent. PanHub's bot defense (Cloudflare) doesn't strictly
# validate this string, but matching a current desktop Chrome UA reduces
# oddities. Users can override via credentials.json.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)

# Connection timeout (seconds). SSE streams can take 5-10s as plugins
# complete; total budget should be larger.
DEFAULT_TIMEOUT_S = 30

# HTTP status that means Cloudflare blocked us as a bot.
CLOUDFLARE_BOT_STATUS = 403
CLOUDFLARE_BOT_MESSAGE = "bot forbidden"
