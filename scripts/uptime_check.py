"""Records one uptime check per target into data/uptime/<target>.json.

Run on a schedule (.github/workflows/uptime.yml), which commits the updated
files back to the repo. worker/site's /status page fetches these files
straight from GitHub's raw content CDN at runtime (not at build time), so a
check running here never needs the Astro site itself to rebuild/redeploy —
only an actual code change does that.

"Up" means "reachable and responding as expected", not "returned 200": the
tools and ynab-api targets are unauthenticated checks against endpoints that
require a token, so a 401/403 there proves the service is up just as much as
a 200 would. Only a timeout, connection failure, or 5xx counts as down for
those two. auth and worker are expected to return exactly 200 when healthy,
so anything else (including a 404 — the exact bug this page exists to catch
early) counts as down.

Usage:
    python scripts/uptime_check.py
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "uptime"
HISTORY_LIMIT = 288  # 48 hours of history at the workflow's 10-minute interval
TIMEOUT_SECONDS = 10


@dataclass
class Target:
    key: str
    url: str
    method: str = "GET"
    # Status codes that count as "up". Anything else (including a network
    # error/timeout) counts as down.
    up_codes: range = range(100, 500)


TARGETS = [
    Target("worker", "https://ynab.nyuchi.com/health", up_codes=range(200, 201)),
    Target("tools", "https://ynab.nyuchi.com/mcp"),
    Target("ynab-api", "https://api.ynab.com/v1/user"),
    Target("auth", "https://ynab.nyuchi.com/.well-known/oauth-authorization-server", up_codes=range(200, 201)),
]


def check(target: Target) -> dict:
    started = time.monotonic()
    request = urllib.request.Request(target.url, method=target.method, headers={"User-Agent": "mcp-ynab-uptime-check"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        # A raised HTTPError still means the server responded — 4xx/5xx are
        # legitimate outcomes to record, not a failure to reach it.
        status = exc.code
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        status = None
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return {
        "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "up": status is not None and status in target.up_codes,
        "status": status,
        "ms": elapsed_ms,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for target in TARGETS:
        path = DATA_DIR / f"{target.key}.json"
        history = json.loads(path.read_text()) if path.exists() else []
        history.append(check(target))
        history = history[-HISTORY_LIMIT:]
        path.write_text(json.dumps(history, indent=2) + "\n")
        print(f"{target.key}: {'up' if history[-1]['up'] else 'down'} ({history[-1]['status']}, {history[-1]['ms']}ms)")


if __name__ == "__main__":
    main()
