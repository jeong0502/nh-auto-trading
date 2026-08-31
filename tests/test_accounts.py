"""STEP 7/10: NHPLUG 인증·계좌 조회 — 사용자별 분리 (mock only)."""

import logging
import os
from unittest.mock import patch

import pytest
from nhplug import NhplugError

from app.accounts import (
    AccountError,
    authenticate_for,
    fetch_account_list_for,
    mask_account_no,
    validate_acct_type,
    validate_account_for,
    validate_all_configured_accounts,
    validate_configured_account,
)
from tests.conftest import KEY_1, KEY_2, SECRET_1, SECRET_2

ACCT_1 = "20101036881"
ACCT_2 = "50051036881"


def _acctinfo_for_current_key(path, input_0):
    key = os.environ.get("NHPLUG_APP_KEY")
    if key == KEY_1:
        return {"Output_0": [{"acct_no": ACCT_1, "acct_type": "03"}]}
    if key == KEY_2:
        return {"Output_0": [{"acct_no": ACCT_2, "acct_type": "03"}]}
    return {"Output_0": []}


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("NHPLUG_BASE_URL", "https://moapi.nhplug.com:8443")
    monkeypatch.setenv("NHPLUG_AUTH_URL", "https://api.nhplug.com:8443")
    monkeypatch.setenv("NHPLUG_APP_KEY_1", KEY_1)
    monkeypatch.setenv("NHPLUG_APP_SECRET_1", SECRET_1)
    monkeypatch.setenv("NHPLUG_APP_KEY_2", KEY_2)
    monkeypatch.setenv("NHPLUG_APP_SECRET_2", SECRET_2)
    monkeypatch.setenv("NH_ACCOUNT_1", ACCT_1)
    monkeypatch.setenv("NH_ACCOUNT_2", ACCT_2)
    monkeypatch.setenv("NH_DRY_RUN", "true")


class TestMaskAccount:
    def test_mask_account_no(self):
        assert mask_account_no("12345678901") == "12345678***"
        assert mask_account_no("123") == "***"

    def test_mask_account_tail(self):
        from app.accounts import mask_account_tail

        assert mask_account_tail("20101036881") == "*******6881"
        assert mask_account_tail("1234") == "***"
        assert mask_account_tail("12345") == "*2345"


class TestMockAccountValidation:
    def test_mock_acct_type_03_valid(self, mock_env):
        validate_acct_type("03")

    def test_api1_account_exists(self, mock_env):
        with patch("app.accounts.get_token"), patch(
            "app.accounts.call", side_effect=_acctinfo_for_current_key
        ):
            result = validate_all_configured_accounts()
        assert result["skipped"] is False
        assert result["validated"] == 2

    def test_api2_account_exists(self, mock_env):
        with patch("app.accounts.get_token"), patch(
            "app.accounts.call", side_effect=_acctinfo_for_current_key
        ):
            validate_account_for("API2")

    def test_api1_account_missing(self, mock_env, monkeypatch):
        monkeypatch.setenv("NH_ACCOUNT_1", "99999999999")
        with patch("app.accounts.get_token"), patch(
            "app.accounts.call", side_effect=_acctinfo_for_current_key
        ):
            with pytest.raises(AccountError, match="API1: configured account not found"):
                validate_all_configured_accounts()

    def test_api2_account_missing(self, mock_env):
        with patch("app.accounts.get_token"), patch(
            "app.accounts.call",
            return_value={"Output_0": [{"acct_no": ACCT_1, "acct_type": "03"}]},
        ):
            with pytest.raises(AccountError, match="API2: configured account not found"):
                validate_configured_account(
                    label="API2",
                    env_key="NH_ACCOUNT_2",
                    accounts=[{"acct_no": ACCT_1, "acct_type": "03"}],
                )

    def test_api1_acctinfo_does_not_validate_api2_account(self, mock_env, monkeypatch):
        monkeypatch.setenv("NH_ACCOUNT_1", ACCT_2)
        with patch("app.accounts.get_token"), patch(
            "app.accounts.call",
            return_value={"Output_0": [{"acct_no": ACCT_1, "acct_type": "03"}]},
        ):
            with pytest.raises(AccountError, match="API1: configured account not found"):
                validate_account_for("API1")


class TestAcctTypeEnvironment:
    def test_moapi_rejects_acct_type_01(self, mock_env):
        with pytest.raises(AccountError, match="does not match environment"):
            validate_acct_type("01", label="API1")

    def test_moapi_rejects_acct_type_02(self, mock_env):
        with pytest.raises(AccountError, match="does not match environment"):
            validate_acct_type("02", label="API2")

    def test_api_accepts_acct_type_01(self, monkeypatch):
        monkeypatch.setenv("NHPLUG_BASE_URL", "https://api.nhplug.com:8443")
        validate_acct_type("01")

    def test_api_accepts_acct_type_02(self, monkeypatch):
        monkeypatch.setenv("NHPLUG_BASE_URL", "https://api.nhplug.com:8443")
        validate_acct_type("02")


class TestGetToken:
    def test_authenticate_for_api1_calls_get_token(self, mock_env):
        with patch("app.accounts.get_token") as mock_get_token:
            authenticate_for("API1")
        mock_get_token.assert_called_once()

    def test_nhplug_error_propagates(self, mock_env):
        err = NhplugError("auth failed", category="auth")
        with patch("app.accounts.get_token", side_effect=err):
            with pytest.raises(NhplugError) as exc_info:
                authenticate_for("API1")
        assert exc_info.value.category == "auth"
        assert exc_info.value.message == "auth failed"


class TestAcctinfoStructure:
    def test_fetch_account_list_for_api1(self, mock_env):
        with patch("app.accounts.get_token"), patch(
            "app.accounts.call", side_effect=_acctinfo_for_current_key
        ) as mock_call:
            accounts = fetch_account_list_for("API1")
        mock_call.assert_called_once_with("/n2/acctinfo", {})
        assert accounts[0]["acct_no"] == ACCT_1


class TestSensitiveLogging:
    def test_logs_do_not_expose_secrets(self, mock_env, caplog):
        caplog.set_level(logging.INFO, logger="app.accounts")

        with patch("app.accounts.get_token"), patch(
            "app.accounts.call", side_effect=_acctinfo_for_current_key
        ):
            validate_all_configured_accounts()

        log_text = caplog.text
        assert KEY_1 not in log_text
        assert SECRET_1 not in log_text
        assert KEY_2 not in log_text
        assert SECRET_2 not in log_text
        assert ACCT_1 not in log_text
        assert ACCT_2 not in log_text
        assert mask_account_no(ACCT_1) in log_text
        assert "token" not in log_text.lower()
