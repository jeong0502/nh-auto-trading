"""pytest 공통 설정."""

import pytest

from app import orders

KEY_1 = "test_app_key_1_secret"
SECRET_1 = "test_app_secret_1_secret"
KEY_2 = "test_app_key_2_secret"
SECRET_2 = "test_app_secret_2_secret"


@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    """각 테스트마다 DRY RUN + API1/API2 credentials + 중복 캐시 초기화."""
    monkeypatch.setenv("NH_DRY_RUN", "true")
    monkeypatch.setenv("NHPLUG_APP_KEY_1", KEY_1)
    monkeypatch.setenv("NHPLUG_APP_SECRET_1", SECRET_1)
    monkeypatch.setenv("NHPLUG_APP_KEY_2", KEY_2)
    monkeypatch.setenv("NHPLUG_APP_SECRET_2", SECRET_2)
    monkeypatch.setenv("NH_ACCOUNT_1", "1111111111")
    monkeypatch.setenv("NH_ACCOUNT_2", "2222222222")
    monkeypatch.delenv("NHPLUG_APP_KEY", raising=False)
    monkeypatch.delenv("NHPLUG_APP_SECRET", raising=False)
    orders._RECENT_REQUESTS.clear()
    yield
    orders._RECENT_REQUESTS.clear()


@pytest.fixture
def kr_buy_payload():
    return {
        "action": "buy",
        "ticker": "005930",
        "exchange": "KRX",
        "price": 100000,
        "qty": 10,
    }


@pytest.fixture
def kr_sell_payload():
    return {
        "action": "sell",
        "ticker": "005930",
        "exchange": "KRX",
        "price": 100000,
        "qty": 10,
    }


@pytest.fixture
def us_buy_payload():
    return {
        "action": "buy",
        "ticker": "SOXL",
        "exchange": "NASDAQ",
        "price": 100,
        "qty": 10,
    }


@pytest.fixture
def us_sell_payload():
    return {
        "action": "sell",
        "ticker": "SOXL",
        "exchange": "NASDAQ",
        "price": 100,
        "qty": 10,
    }
