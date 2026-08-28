"""STEP 12: 운영 전 최종 안전성 점검 (mock only, 실제 NHPLUG 호출 없음)."""

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from nhplug import NhplugError

from app.config import account_env_key
from app.credentials import nhplug_credentials
from app.main import app
from app.orders import (
    DuplicateRequestError,
    WebhookValidationError,
    _RECENT_REQUESTS,
    check_duplicate,
    process_webhook,
)
from tests.conftest import KEY_1, KEY_2, SECRET_1, SECRET_2

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parents[1]

ACCOUNT_1 = "1111111111"
ACCOUNT_2 = "2222222222"


def _run(label: str, payload: dict) -> dict:
    return process_webhook(
        endpoint=label,
        account_label=label,
        account_env_key=account_env_key(label),
        payload=payload,
    )


@pytest.fixture(autouse=True)
def clear_dedup():
    _RECENT_REQUESTS.clear()
    yield
    _RECENT_REQUESTS.clear()


class TestApiCredentialSeparation:
    def test_api1_uses_key1_secret1_account1(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        captured: dict[str, str] = {}

        def mock_call(path, input_0):
            captured["key"] = os.environ["NHPLUG_APP_KEY"]
            captured["secret"] = os.environ["NHPLUG_APP_SECRET"]
            captured["act_no"] = input_0["act_no"]
            return {"Output_0": {"mkt_orr_no": "1"}}

        with patch("app.orders.call", side_effect=mock_call):
            _run(
                "API1",
                {
                    "action": "buy",
                    "ticker": "005930",
                    "exchange": "KRX",
                    "price": 70000,
                    "qty": 201,
                },
            )

        assert captured["key"] == KEY_1
        assert captured["secret"] == SECRET_1
        assert captured["act_no"] == ACCOUNT_1
        assert captured["key"] != KEY_2
        assert captured["act_no"] != ACCOUNT_2

    def test_api2_uses_key2_secret2_account2(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        captured: dict[str, str] = {}

        def mock_call(path, input_0):
            captured["key"] = os.environ["NHPLUG_APP_KEY"]
            captured["secret"] = os.environ["NHPLUG_APP_SECRET"]
            captured["act_no"] = input_0["act_no"]
            return {"Output_0": {"orr_no": "2"}}

        with patch("app.orders.call", side_effect=mock_call):
            _run(
                "API2",
                {
                    "action": "sell",
                    "ticker": "SOXL",
                    "exchange": "NASDAQ",
                    "price": 30,
                    "qty": 202,
                },
            )

        assert captured["key"] == KEY_2
        assert captured["secret"] == SECRET_2
        assert captured["act_no"] == ACCOUNT_2
        assert captured["key"] != KEY_1
        assert captured["act_no"] != ACCOUNT_1


class TestConcurrentApiRequests:
    def test_api1_api2_concurrent_no_credential_mix(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        results: list[tuple[str, str, str]] = []
        gate = threading.Event()

        def mock_call(path, input_0):
            gate.wait(timeout=5)
            key = os.environ["NHPLUG_APP_KEY"]
            label = "API1" if key == KEY_1 else "API2"
            results.append((label, key, input_0["act_no"]))
            return {"Output_0": {}}

        def worker(label: str, qty: int):
            _run(
                label,
                {
                    "action": "buy",
                    "ticker": "SOXL",
                    "exchange": "BATS",
                    "price": 30,
                    "qty": qty,
                },
            )

        with patch("app.orders.call", side_effect=mock_call):
            t1 = threading.Thread(target=worker, args=("API1", 211))
            t2 = threading.Thread(target=worker, args=("API2", 212))
            t1.start()
            t2.start()
            time.sleep(0.05)
            gate.set()
            t1.join(timeout=5)
            t2.join(timeout=5)

        by_label = {label: (key, act_no) for label, key, act_no in results}
        assert by_label["API1"] == (KEY_1, ACCOUNT_1)
        assert by_label["API2"] == (KEY_2, ACCOUNT_2)


class TestCredentialRestore:
    def test_sdk_env_restored_after_exception(self):
        marker = "step12_restore_marker"
        os.environ["NHPLUG_APP_KEY"] = marker

        with pytest.raises(RuntimeError):
            with nhplug_credentials("API1"):
                raise RuntimeError("simulated failure")

        assert os.environ.get("NHPLUG_APP_KEY") == marker

    def test_sdk_env_restored_after_nhplug_error(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        marker = "step12_nhplug_restore"
        os.environ["NHPLUG_APP_KEY"] = marker

        with patch(
            "app.orders.call",
            side_effect=NhplugError("fail", category="business"),
        ):
            response = client.post(
                "/webhook/api1",
                json={
                    "action": "buy",
                    "ticker": "005930",
                    "exchange": "KRX",
                    "price": 70000,
                    "qty": 221,
                },
            )

        assert response.status_code == 502
        assert os.environ.get("NHPLUG_APP_KEY") == marker


class TestDedupBehavior:
    def test_duplicate_blocked_within_30_seconds(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr("app.orders.time.time", lambda: clock[0])

        check_duplicate("API1", "BUY", "SOXL", 1)
        with pytest.raises(DuplicateRequestError):
            check_duplicate("API1", "BUY", "SOXL", 1)

        clock[0] = 1029.0
        with pytest.raises(DuplicateRequestError):
            check_duplicate("API1", "BUY", "SOXL", 1)

        clock[0] = 1030.0
        check_duplicate("API1", "BUY", "SOXL", 1)

    def test_buy_and_sell_are_not_duplicates(self):
        base = {
            "ticker": "SOXL",
            "exchange": "NASDAQ",
            "price": 30,
            "qty": 231,
        }
        buy = _run("API1", {**base, "action": "buy"})
        sell = _run("API1", {**base, "action": "sell"})
        assert buy["ok"] is True
        assert sell["ok"] is True
        assert buy["side"] == "BUY"
        assert sell["side"] == "SELL"

    def test_api1_and_api2_dedup_are_independent(self):
        payload = {
            "action": "buy",
            "ticker": "SOXL",
            "exchange": "NASDAQ",
            "price": 30,
            "qty": 241,
        }
        r1 = client.post("/webhook/api1", json=payload).json()
        r2 = client.post("/webhook/api2", json=payload).json()
        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r1["account"] == "API1"
        assert r2["account"] == "API2"


class TestInvalidInputBlocked:
    @pytest.mark.parametrize(
        "payload",
        [
            {"action": "hold", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 1},
            {"action": "buy", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 0},
            {"action": "buy", "ticker": "", "exchange": "NASDAQ", "price": 30, "qty": 1},
        ],
    )
    def test_validation_error_never_reaches_execute_order(self, payload):
        with patch("app.orders.execute_order") as mock_execute:
            with pytest.raises(WebhookValidationError):
                _run("API1", payload)
        mock_execute.assert_not_called()

    def test_invalid_json_never_reaches_process_webhook(self):
        with patch("app.orders.process_webhook") as mock_process:
            with pytest.raises(json.JSONDecodeError):
                client.post(
                    "/webhook/api1",
                    content=b"{bad",
                    headers={"Content-Type": "application/json"},
                )
        mock_process.assert_not_called()


class TestNhplugErrorHandling:
    @pytest.mark.parametrize(
        ("category", "message"),
        [
            ("rate_limit", "rate limit exceeded"),
            ("network", "connection timeout"),
            ("http", "gateway error"),
            ("business", "order rejected"),
        ],
    )
    def test_nhplug_errors_return_502_single_call(self, monkeypatch, category, message):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        call_count = 0

        def mock_call(path, input_0):
            nonlocal call_count
            call_count += 1
            raise NhplugError(message, category=category)

        with patch("app.orders.call", side_effect=mock_call):
            response = client.post(
                "/webhook/api1",
                json={
                    "action": "buy",
                    "ticker": "005930",
                    "exchange": "KRX",
                    "price": 70000,
                    "qty": 300 + call_count,
                },
            )

        assert response.status_code == 502
        assert response.json()["detail"]["category"] == category
        assert call_count == 1

    def test_server_recovers_after_nhplug_error(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        attempts = 0

        def mock_call(path, input_0):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise NhplugError("temporary", category="network")
            return {"Output_0": {"mkt_orr_no": "ok"}}

        with patch("app.orders.call", side_effect=mock_call):
            fail = client.post(
                "/webhook/api1",
                json={
                    "action": "buy",
                    "ticker": "005930",
                    "exchange": "KRX",
                    "price": 70000,
                    "qty": 251,
                },
            )
            ok = client.post(
                "/webhook/api1",
                json={
                    "action": "buy",
                    "ticker": "005930",
                    "exchange": "KRX",
                    "price": 70000,
                    "qty": 252,
                },
            )

        assert fail.status_code == 502
        assert ok.status_code == 200
        assert ok.json()["ok"] is True
        assert attempts == 2


class TestSensitiveLogging:
    def test_success_and_error_logs_hide_secrets(self, monkeypatch, caplog):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        caplog.set_level(logging.INFO)
        caplog.set_level(logging.ERROR, logger="app.orders")

        with patch(
            "app.orders.call",
            side_effect=NhplugError("failed", category="business"),
        ):
            client.post(
                "/webhook/api1",
                json={
                    "action": "buy",
                    "ticker": "005930",
                    "exchange": "KRX",
                    "price": 70000,
                    "qty": 261,
                },
            )

        log_text = caplog.text
        for secret in (KEY_1, SECRET_1, KEY_2, SECRET_2, ACCOUNT_1, ACCOUNT_2):
            assert secret not in log_text
        assert "Bearer" not in log_text


class TestHealthIsolation:
    def test_get_health_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_head_health_200(self):
        response = client.head("/health")
        assert response.status_code == 200

    def test_health_does_not_touch_nhplug(self):
        with (
            patch("app.orders.call") as mock_call,
            patch("nhplug.get_token") as mock_token,
            patch("app.credentials.nhplug_credentials") as mock_creds,
        ):
            client.get("/health")
            client.head("/health")

        mock_call.assert_not_called()
        mock_token.assert_not_called()
        mock_creds.assert_not_called()


class TestGitSecurity:
    def test_env_not_tracked_by_git(self):
        if not (REPO_ROOT / ".git").is_dir():
            pytest.skip("not a git repository")

        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        tracked = result.stdout.splitlines()
        assert ".env" not in tracked
        assert not any(p.endswith("/.env") or p == ".env" for p in tracked)

    def test_gitignore_excludes_env(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in gitignore
