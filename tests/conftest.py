"""pytest 공통 설정."""

import os

import pytest

from app import orders


@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    """각 테스트마다 DRY RUN + 테스트용 계좌번호 + 중복 캐시 초기화."""
    monkeypatch.setenv("NH_DRY_RUN", "true")
    monkeypatch.setenv("NHPLUG_APP_KEY", "test_app_key_secret_value")
    monkeypatch.setenv("NHPLUG_APP_SECRET", "test_app_secret_secret_value")
    monkeypatch.setenv("NH_ACCOUNT_1", "1111111111")
    monkeypatch.setenv("NH_ACCOUNT_2", "2222222222")
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
