"""STEP 11: 주문 시스템 안전성 검증 (mock only, 실제 NHPLUG 호출 없음)."""

import json
import logging
import os
import threading
import time
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
    prepare_order,
    process_webhook,
)
from tests.conftest import KEY_1, KEY_2, SECRET_1, SECRET_2

client = TestClient(app)

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


class TestEightOrderCombinations:
    """API1/API2 × 국내/미국 × BUY/SELL 8조합."""

    @pytest.mark.parametrize(
        ("label", "payload", "market", "side", "account_env", "act_no", "path_part"),
        [
            (
                "API1",
                {"action": "buy", "ticker": "005930", "exchange": "KRX", "price": 70000, "qty": 1},
                "KR",
                "BUY",
                "NH_ACCOUNT_1",
                ACCOUNT_1,
                "cashBuy",
            ),
            (
                "API1",
                {"action": "sell", "ticker": "005930", "exchange": "KRX", "price": 70000, "qty": 2},
                "KR",
                "SELL",
                "NH_ACCOUNT_1",
                ACCOUNT_1,
                "cashSell",
            ),
            (
                "API1",
                {"action": "buy", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 3},
                "US",
                "BUY",
                "NH_ACCOUNT_1",
                ACCOUNT_1,
                "/buy",
            ),
            (
                "API1",
                {"action": "sell", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 4},
                "US",
                "SELL",
                "NH_ACCOUNT_1",
                ACCOUNT_1,
                "/sell",
            ),
            (
                "API2",
                {"action": "buy", "ticker": "005930", "exchange": "KRX", "price": 70000, "qty": 5},
                "KR",
                "BUY",
                "NH_ACCOUNT_2",
                ACCOUNT_2,
                "cashBuy",
            ),
            (
                "API2",
                {"action": "sell", "ticker": "005930", "exchange": "KRX", "price": 70000, "qty": 6},
                "KR",
                "SELL",
                "NH_ACCOUNT_2",
                ACCOUNT_2,
                "cashSell",
            ),
            (
                "API2",
                {"action": "buy", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 7},
                "US",
                "BUY",
                "NH_ACCOUNT_2",
                ACCOUNT_2,
                "/buy",
            ),
            (
                "API2",
                {"action": "sell", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 8},
                "US",
                "SELL",
                "NH_ACCOUNT_2",
                ACCOUNT_2,
                "/sell",
            ),
        ],
    )
    def test_order_combination(self, label, payload, market, side, account_env, act_no, path_part):
        with patch("app.orders.call") as mock_call:
            result = _run(label, payload)

        assert result["ok"] is True
        assert result["mode"] == "dry_run"
        assert result["account"] == label
        assert result["market"] == market
        assert result["side"] == side
        assert result["order_type"] == "MARKET"
        assert mock_call.call_count == 0

        path, input_0 = prepare_order(
            market=market,
            side=side,
            ticker=payload["ticker"],
            qty=payload["qty"],
            account_env_key=account_env,
            country_code="200" if market == "US" else None,
        )
        assert path_part in path
        assert input_0["act_no"] == act_no
        assert account_env == account_env_key(label)


class TestMarketRouting:
    def test_kr_market_from_krx(self):
        result = _run(
            "API1",
            {"action": "buy", "ticker": "005930", "exchange": "KRX", "price": 70000, "qty": 11},
        )
        assert result["market"] == "KR"

    def test_us_market_from_bats(self):
        result = _run(
            "API1",
            {"action": "buy", "ticker": "SOXL", "exchange": "BATS", "price": 30, "qty": 12},
        )
        assert result["market"] == "US"


class TestBuySellNormalization:
    @pytest.mark.parametrize("action", ["buy", "sell", "BUY", "SELL"])
    def test_action_normalized_to_upper(self, action):
        side = action.strip().upper()
        result = _run(
            "API1",
            {
                "action": action,
                "ticker": "SOXL",
                "exchange": "NASDAQ",
                "price": 30,
                "qty": 20 if side == "BUY" else 21,
            },
        )
        assert result["side"] == side


class TestCredentialCrossContamination:
    def test_api1_live_uses_only_key1_not_key2(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        seen: list[str] = []

        def mock_call(path, input_0):
            seen.append(os.environ.get("NHPLUG_APP_KEY"))
            assert input_0["act_no"] == ACCOUNT_1
            assert input_0["act_no"] != ACCOUNT_2
            return {"Output_0": {"mkt_orr_no": "1"}}

        with patch("app.orders.call", side_effect=mock_call):
            _run(
                "API1",
                {"action": "buy", "ticker": "005930", "exchange": "KRX", "price": 70000, "qty": 31},
            )

        assert seen == [KEY_1]
        assert KEY_2 not in seen

    def test_api2_live_uses_only_key2_not_key1(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        seen: list[str] = []

        def mock_call(path, input_0):
            seen.append(os.environ.get("NHPLUG_APP_KEY"))
            assert input_0["act_no"] == ACCOUNT_2
            assert input_0["act_no"] != ACCOUNT_1
            return {"Output_0": {"orr_no": "2"}}

        with patch("app.orders.call", side_effect=mock_call):
            _run(
                "API2",
                {"action": "sell", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 32},
            )

        assert seen == [KEY_2]
        assert KEY_1 not in seen


class TestConcurrentCredentialsLock:
    def test_concurrent_api1_api2_live_calls_use_correct_keys(self, monkeypatch):
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
                    "exchange": "NASDAQ",
                    "price": 30,
                    "qty": qty,
                },
            )

        with patch("app.orders.call", side_effect=mock_call):
            t1 = threading.Thread(target=worker, args=("API1", 41))
            t2 = threading.Thread(target=worker, args=("API2", 42))
            t1.start()
            t2.start()
            time.sleep(0.05)
            gate.set()
            t1.join(timeout=5)
            t2.join(timeout=5)

        assert len(results) == 2
        by_label = {label: (key, act_no) for label, key, act_no in results}
        assert by_label["API1"] == (KEY_1, ACCOUNT_1)
        assert by_label["API2"] == (KEY_2, ACCOUNT_2)


class TestDryRunGuarantee:
    def test_api1_dry_run_no_call_no_get_token(self):
        with patch("app.orders.call") as mock_call, patch("nhplug.get_token") as mock_token:
            _run(
                "API1",
                {"action": "buy", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 51},
            )
        assert mock_call.call_count == 0
        assert mock_token.call_count == 0

    def test_api2_dry_run_no_call_no_get_token(self):
        with patch("app.orders.call") as mock_call, patch("nhplug.get_token") as mock_token:
            _run(
                "API2",
                {"action": "sell", "ticker": "005930", "exchange": "KRX", "price": 70000, "qty": 52},
            )
        assert mock_call.call_count == 0
        assert mock_token.call_count == 0

    def test_dry_run_skips_credentials_context(self):
        with patch("app.orders.nhplug_credentials") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda s: None
            mock_ctx.return_value.__exit__ = lambda s, *a: None
            _run(
                "API1",
                {"action": "buy", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 53},
            )
        mock_ctx.assert_not_called()


class TestInvalidInputs:
    @pytest.mark.parametrize("action", ["hold", "abc"])
    def test_invalid_action_rejected(self, action):
        with pytest.raises(WebhookValidationError):
            _run(
                "API1",
                {"action": action, "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": 1},
            )

    @pytest.mark.parametrize("qty", [0, -1, None, "1"])
    def test_invalid_qty_rejected(self, qty):
        with pytest.raises(WebhookValidationError):
            _run(
                "API1",
                {"action": "buy", "ticker": "SOXL", "exchange": "NASDAQ", "price": 30, "qty": qty},
            )

    def test_empty_ticker_rejected(self):
        with pytest.raises(WebhookValidationError):
            _run(
                "API1",
                {"action": "buy", "ticker": "", "exchange": "NASDAQ", "price": 30, "qty": 1},
            )

    def test_unsupported_exchange_rejected(self):
        with pytest.raises(WebhookValidationError):
            _run(
                "API1",
                {"action": "buy", "ticker": "SOXL", "exchange": "UNKNOWN", "price": 30, "qty": 1},
            )

    def test_invalid_json_is_rejected(self):
        """현재 FastAPI는 잘못된 JSON 시 JSONDecodeError를 발생시킨다."""
        with pytest.raises(json.JSONDecodeError):
            client.post(
                "/webhook/api1",
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            )


class TestDuplicateWebhook:
    def test_duplicate_request_returns_duplicate_flag(self):
        payload = {
            "action": "buy",
            "ticker": "SOXL",
            "exchange": "NASDAQ",
            "price": 30,
            "qty": 99,
        }
        first = client.post("/webhook/api1", json=payload).json()
        assert first["ok"] is True

        with patch("app.orders.call") as mock_call:
            second = client.post("/webhook/api1", json=payload).json()

        assert second["ok"] is False
        assert second["duplicate"] is True
        assert mock_call.call_count == 0

    def test_check_duplicate_raises(self):
        check_duplicate("API1", "BUY", "SOXL", 100)
        with pytest.raises(DuplicateRequestError):
            check_duplicate("API1", "BUY", "SOXL", 100)


class TestRateLimitHandling:
    def test_429_returns_502_without_retry(self, monkeypatch):
        monkeypatch.setenv("NH_DRY_RUN", "false")
        err = NhplugError("rate limit", category="rate_limit", retryable=True)
        call_count = 0

        def mock_call(path, input_0):
            nonlocal call_count
            call_count += 1
            raise err

        with patch("app.orders.call", side_effect=mock_call):
            response = client.post(
                "/webhook/api1",
                json={
                    "action": "buy",
                    "ticker": "005930",
                    "exchange": "KRX",
                    "price": 70000,
                    "qty": 61,
                },
            )

        assert response.status_code == 502
        assert response.json()["detail"]["category"] == "rate_limit"
        assert call_count == 1


class TestSensitiveLoggingOnError:
    def test_nhplug_error_log_masks_credentials(self, monkeypatch, caplog):
        monkeypatch.setenv("NH_DRY_RUN", "false")
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
                    "qty": 71,
                },
            )

        log_text = caplog.text
        assert KEY_1 not in log_text
        assert SECRET_1 not in log_text
        assert ACCOUNT_1 not in log_text
        assert "Bearer" not in log_text


class TestHealthEndpoints:
    def test_get_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_head_health(self):
        response = client.head("/health")
        assert response.status_code == 200
        assert response.content == b""
