"""STEP 7: NHPLUG 인증·계좌 조회 구조 검증 (mock only)."""

import logging
from unittest.mock import patch

import pytest
from nhplug import NhplugError

from app.accounts import (
    AccountError,
    authenticate,
    fetch_account_list,
    mask_account_no,
    validate_acct_type,
    validate_all_configured_accounts,
    validate_configured_account,
)

ACCT_1 = "20101036881"
ACCT_2 = "50051036881"


@pytest.fixture
def mock_accounts():
    return [
        {"acct_no": ACCT_1, "acct_type": "03"},
        {"acct_no": ACCT_2, "acct_type": "03"},
    ]


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("NHPLUG_BASE_URL", "https://moapi.nhplug.com:8443")
    monkeypatch.setenv("NHPLUG_AUTH_URL", "https://api.nhplug.com:8443")
    monkeypatch.setenv("NHPLUG_APP_KEY", "test_app_key_secret_value")
    monkeypatch.setenv("NHPLUG_APP_SECRET", "test_app_secret_secret_value")
    monkeypatch.setenv("NH_ACCOUNT_1", ACCT_1)
    monkeypatch.setenv("NH_ACCOUNT_2", ACCT_2)
    monkeypatch.setenv("NH_DRY_RUN", "true")


class TestMaskAccount:
    def test_mask_account_no(self):
        assert mask_account_no("12345678901") == "12345678***"
        assert mask_account_no("123") == "***"


class TestMockAccountValidation:
    def test_mock_acct_type_03_valid(self, mock_env, mock_accounts):
        validate_acct_type("03")

    def test_api1_account_exists(self, mock_env, mock_accounts):
        with patch("app.accounts.get_token"), patch("app.accounts.call", return_value={"Output_0": mock_accounts}):
            result = validate_all_configured_accounts()
        assert result["skipped"] is False
        assert result["validated"] == 2

    def test_api2_account_exists(self, mock_env, mock_accounts):
        with patch("app.accounts.get_token"), patch("app.accounts.call", return_value={"Output_0": mock_accounts}):
            validate_configured_account(label="API2", env_key="NH_ACCOUNT_2", accounts=mock_accounts)

    def test_api1_account_missing(self, mock_env, mock_accounts, monkeypatch):
        monkeypatch.setenv("NH_ACCOUNT_1", "99999999999")
        with patch("app.accounts.get_token"), patch("app.accounts.call", return_value={"Output_0": mock_accounts}):
            with pytest.raises(AccountError, match="API1: configured account not found"):
                validate_all_configured_accounts()

    def test_api2_account_missing(self, mock_env, mock_accounts):
        with patch("app.accounts.get_token"), patch("app.accounts.call", return_value={"Output_0": mock_accounts}):
            with pytest.raises(AccountError, match="API2: configured account not found"):
                validate_configured_account(
                    label="API2",
                    env_key="NH_ACCOUNT_2",
                    accounts=[{"acct_no": ACCT_1, "acct_type": "03"}],
                )


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
    def test_authenticate_calls_get_token(self, mock_env):
        with patch("app.accounts.get_token") as mock_get_token:
            authenticate()
        mock_get_token.assert_called_once()

    def test_nhplug_error_propagates(self, mock_env):
        err = NhplugError("auth failed", category="auth")
        with patch("app.accounts.get_token", side_effect=err):
            with pytest.raises(NhplugError) as exc_info:
                authenticate()
        assert exc_info.value.category == "auth"
        assert exc_info.value.message == "auth failed"


class TestAcctinfoStructure:
    def test_fetch_account_list_calls_acctinfo(self, mock_env):
        with patch("app.accounts.call", return_value={"Output_0": [{"acct_no": ACCT_1, "acct_type": "03"}]}) as mock_call:
            accounts = fetch_account_list()
        mock_call.assert_called_once_with("/n2/acctinfo", {})
        assert accounts[0]["acct_no"] == ACCT_1
        assert accounts[0]["acct_type"] == "03"


class TestSensitiveLogging:
    def test_logs_do_not_expose_secrets(self, mock_env, mock_accounts, caplog):
        caplog.set_level(logging.INFO, logger="app.accounts")

        with patch("app.accounts.get_token"), patch("app.accounts.call", return_value={"Output_0": mock_accounts}):
            validate_all_configured_accounts()

        log_text = caplog.text
        assert "test_app_key_secret_value" not in log_text
        assert "test_app_secret_secret_value" not in log_text
        assert ACCT_1 not in log_text
        assert ACCT_2 not in log_text
        assert mask_account_no(ACCT_1) in log_text
        assert "token" not in log_text.lower()
