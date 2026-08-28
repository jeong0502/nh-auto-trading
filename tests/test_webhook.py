"""STEP 8: FastAPI HTTP 엔드포인트 검증 (Render 배포 준비)."""

import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import orders

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_duplicate_cache():
    orders._RECENT_REQUESTS.clear()
    yield
    orders._RECENT_REQUESTS.clear()


class TestHealth:
    def test_health_get_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_head_returns_200(self):
        response = client.head("/health")
        assert response.status_code == 200
        assert response.content == b""


class TestWebhookApi1:
    def test_api1_us_buy_dry_run(self):
        payload = {
            "action": "buy",
            "ticker": "SOXL",
            "exchange": "NASDAQ",
            "price": 20,
            "qty": 10,
        }
        with patch("app.orders.call") as mock_call:
            response = client.post("/webhook/api1", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["mode"] == "dry_run"
        assert body["account"] == "API1"
        assert body["market"] == "US"
        assert body["side"] == "BUY"
        assert mock_call.call_count == 0


class TestWebhookApi2:
    def test_api2_kr_sell_dry_run(self):
        payload = {
            "action": "sell",
            "ticker": "005930",
            "exchange": "KRX",
            "price": 100000,
            "qty": 10,
        }
        with patch("app.orders.call") as mock_call:
            response = client.post("/webhook/api2", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["mode"] == "dry_run"
        assert body["account"] == "API2"
        assert body["market"] == "KR"
        assert body["side"] == "SELL"
        assert mock_call.call_count == 0


class TestWebhookErrors:
    def test_invalid_payload_returns_400(self):
        payload = {
            "action": "hold",
            "ticker": "SOXL",
            "exchange": "NASDAQ",
            "price": 20,
            "qty": 10,
        }
        with patch("app.orders.call") as mock_call:
            response = client.post("/webhook/api1", json=payload)

        assert response.status_code == 400
        assert mock_call.call_count == 0


class TestSensitiveLogging:
    def test_webhook_logs_do_not_expose_secrets(self, monkeypatch, caplog):
        monkeypatch.setenv("NHPLUG_APP_KEY", "test_app_key_secret_value")
        monkeypatch.setenv("NHPLUG_APP_SECRET", "test_app_secret_secret_value")
        monkeypatch.setenv("NH_ACCOUNT_1", "1111111111")
        monkeypatch.setenv("NH_ACCOUNT_2", "2222222222")

        caplog.set_level(logging.INFO)

        payload = {
            "action": "buy",
            "ticker": "SOXL",
            "exchange": "NASDAQ",
            "price": 20,
            "qty": 12,
        }
        with patch("app.orders.call"):
            client.post("/webhook/api1", json=payload)

        log_text = caplog.text
        assert "test_app_key_secret_value" not in log_text
        assert "test_app_secret_secret_value" not in log_text
        assert "1111111111" not in log_text
        assert "2222222222" not in log_text
        assert "nh_account_1" not in log_text.lower()
        assert "nh_account_2" not in log_text.lower()
