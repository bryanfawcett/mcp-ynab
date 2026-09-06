"""Tests for scripts/uptime_check.py — the /status page's data source.

Zero coverage existed for this script before: it's invoked only by
.github/workflows/uptime.yml on a schedule, never imported by the app
itself, so nothing else in the suite would ever exercise its up/down
classification logic or its history-file read/append/cap round-trip.
A wrong classification here is exactly the kind of bug that wouldn't
surface until the /status page started lying about an outage.
"""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from scripts.uptime_check import HISTORY_LIMIT, Target, check, main


def _fake_response(status: int) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


@pytest.mark.parametrize(
    "status,up_codes,expected_up",
    [
        (200, range(200, 201), True),
        (404, range(200, 201), False),
        # tools/ynab-api-style targets: unauthenticated, so 401/403 still
        # proves the service is up, not down.
        (401, range(100, 500), True),
        (403, range(100, 500), True),
        (500, range(100, 500), False),
        (503, range(200, 201), False),
    ],
)
def test_check_classifies_status_against_target_up_codes(status, up_codes, expected_up):
    target = Target("t", "https://example.com", up_codes=up_codes)
    with patch("urllib.request.urlopen", return_value=_fake_response(status)):
        result = check(target)
    assert result["status"] == status
    assert result["up"] is expected_up


def test_check_treats_http_error_as_a_real_response_not_a_failure():
    # urlopen raises HTTPError (rather than returning normally) for any
    # non-2xx/3xx status — the server still responded, so this must be
    # recorded as that status code, not as unreachable.
    target = Target("t", "https://example.com")
    error = urllib.error.HTTPError(url="https://example.com", code=401, msg="Unauthorized", hdrs=None, fp=None)
    with patch("urllib.request.urlopen", side_effect=error):
        result = check(target)
    assert result["status"] == 401
    assert result["up"] is True


@pytest.mark.parametrize("exception", [urllib.error.URLError("no route"), TimeoutError(), ConnectionError()])
def test_check_records_network_failure_as_down_with_no_status(exception):
    target = Target("t", "https://example.com")
    with patch("urllib.request.urlopen", side_effect=exception):
        result = check(target)
    assert result["status"] is None
    assert result["up"] is False


def test_check_result_shape():
    target = Target("t", "https://example.com", up_codes=range(200, 201))
    with patch("urllib.request.urlopen", return_value=_fake_response(200)):
        result = check(target)
    assert set(result) == {"t", "up", "status", "ms"}
    assert result["t"].endswith("Z")  # ISO 8601 UTC, matching what the /status page parses
    assert isinstance(result["ms"], int)


def test_main_appends_to_existing_history_and_writes_one_file_per_target(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.uptime_check.DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "scripts.uptime_check.TARGETS",
        [Target("worker", "https://example.com/health", up_codes=range(200, 201))],
    )
    existing = [{"t": "2026-01-01T00:00:00Z", "up": True, "status": 200, "ms": 10}]
    (tmp_path / "worker.json").write_text(json.dumps(existing))

    with patch("urllib.request.urlopen", return_value=_fake_response(200)):
        main()

    history = json.loads((tmp_path / "worker.json").read_text())
    assert len(history) == 2
    assert history[0] == existing[0]
    assert history[1]["up"] is True


def test_main_caps_history_at_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.uptime_check.DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "scripts.uptime_check.TARGETS",
        [Target("worker", "https://example.com/health", up_codes=range(200, 201))],
    )
    padding = [{"t": "2026-01-01T00:00:00Z", "up": True, "status": 200, "ms": 1}] * HISTORY_LIMIT
    (tmp_path / "worker.json").write_text(json.dumps(padding))

    with patch("urllib.request.urlopen", return_value=_fake_response(200)):
        main()

    history = json.loads((tmp_path / "worker.json").read_text())
    assert len(history) == HISTORY_LIMIT
    # The oldest entry was dropped to make room for the new check.
    assert history[-1]["up"] is True


def test_main_creates_data_dir_and_file_on_first_run(tmp_path, monkeypatch):
    fresh_dir = tmp_path / "uptime"
    monkeypatch.setattr("scripts.uptime_check.DATA_DIR", fresh_dir)
    monkeypatch.setattr(
        "scripts.uptime_check.TARGETS",
        [Target("auth", "https://example.com/.well-known/oauth-authorization-server", up_codes=range(200, 201))],
    )

    with patch("urllib.request.urlopen", return_value=_fake_response(200)):
        main()

    history = json.loads((fresh_dir / "auth.json").read_text())
    assert len(history) == 1
    assert history[0]["up"] is True
