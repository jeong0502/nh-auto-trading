"""STEP 10: API1/API2 credentials 분리 검증 (mock only)."""

import os
import threading
from unittest.mock import patch

import pytest

from app.config import get_credentials
from app.credentials import CredentialsError, nhplug_credentials, run_with_credentials
from tests.conftest import KEY_1, KEY_2, SECRET_1, SECRET_2


class TestCredentialMapping:
    def test_api1_uses_key_1_and_secret_1(self):
        creds = get_credentials("API1")
        assert creds == (KEY_1, SECRET_1)

    def test_api2_uses_key_2_and_secret_2(self):
        creds = get_credentials("API2")
        assert creds == (KEY_2, SECRET_2)


class TestCredentialsContext:
    def test_api1_sets_sdk_env_vars(self):
        original = {
            "NHPLUG_APP_KEY": os.environ.get("NHPLUG_APP_KEY"),
            "NHPLUG_APP_SECRET": os.environ.get("NHPLUG_APP_SECRET"),
        }
        with nhplug_credentials("API1"):
            assert os.environ["NHPLUG_APP_KEY"] == KEY_1
            assert os.environ["NHPLUG_APP_SECRET"] == SECRET_1
        assert os.environ.get("NHPLUG_APP_KEY") == original["NHPLUG_APP_KEY"]
        assert os.environ.get("NHPLUG_APP_SECRET") == original["NHPLUG_APP_SECRET"]

    def test_api2_sets_sdk_env_vars(self):
        with nhplug_credentials("API2"):
            assert os.environ["NHPLUG_APP_KEY"] == KEY_2
            assert os.environ["NHPLUG_APP_SECRET"] == SECRET_2

    def test_env_restored_on_exception(self):
        marker = "restore_marker_key"
        os.environ["NHPLUG_APP_KEY"] = marker

        with pytest.raises(RuntimeError):
            with nhplug_credentials("API1"):
                raise RuntimeError("boom")

        assert os.environ.get("NHPLUG_APP_KEY") == marker

    def test_missing_credentials_raises(self, monkeypatch):
        monkeypatch.delenv("NHPLUG_APP_KEY_1", raising=False)
        with pytest.raises(CredentialsError):
            with nhplug_credentials("API1"):
                pass


class TestTokenIsolation:
    def test_api1_and_api2_use_different_sdk_keys_during_acctinfo(self):
        seen: list[str] = []

        def side_effect(path, input_0):
            seen.append(os.environ["NHPLUG_APP_KEY"])
            if os.environ["NHPLUG_APP_KEY"] == KEY_1:
                return {"Output_0": [{"acct_no": "20101036881", "acct_type": "03"}]}
            return {"Output_0": [{"acct_no": "50051036881", "acct_type": "03"}]}

        from app.accounts import fetch_account_list_for

        with patch("app.accounts.get_token"), patch("app.accounts.call", side_effect=side_effect):
            fetch_account_list_for("API1")
            fetch_account_list_for("API2")

        assert seen == [KEY_1, KEY_2]


class TestLockPreventsCrossContamination:
    def test_lock_serializes_credential_contexts(self):
        import time

        order: list[str] = []
        gate = threading.Event()

        def hold_api1():
            with nhplug_credentials("API1"):
                order.append("api1-enter")
                gate.wait(timeout=5)

        def try_api2():
            time.sleep(0.05)
            with nhplug_credentials("API2"):
                order.append("api2-enter")

        t1 = threading.Thread(target=hold_api1)
        t2 = threading.Thread(target=try_api2)
        t1.start()
        t2.start()
        time.sleep(0.1)
        assert order == ["api1-enter"]
        gate.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        assert order == ["api1-enter", "api2-enter"]


class TestRunWithCredentials:
    def test_run_with_credentials_helper(self):
        value = run_with_credentials("API1", lambda: os.environ["NHPLUG_APP_KEY"])
        assert value == KEY_1


class TestOrdersUseCredentialsContext:
    def test_live_order_uses_api1_credentials(self, monkeypatch):
        from app.config import account_env_key
        from app.orders import execute_order

        monkeypatch.setenv("NH_DRY_RUN", "false")
        seen_keys: list[str] = []

        def mock_call(path, input_0):
            seen_keys.append(os.environ["NHPLUG_APP_KEY"])
            return {"Output_0": {"mkt_orr_no": "1"}}

        with patch("app.orders.call", side_effect=mock_call):
            execute_order(
                market="KR",
                side="BUY",
                ticker="005930",
                qty=10,
                account_label="API1",
                account_env_key=account_env_key("API1"),
            )

        assert seen_keys == [KEY_1]

    def test_dry_run_does_not_call_nhplug(self):
        from app.config import account_env_key
        from app.orders import execute_order

        with patch("app.orders.call") as mock_call:
            execute_order(
                market="KR",
                side="BUY",
                ticker="005930",
                qty=10,
                account_label="API1",
                account_env_key=account_env_key("API1"),
            )
        assert mock_call.call_count == 0
