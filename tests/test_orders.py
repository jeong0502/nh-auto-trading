"""STEP 6: 주문 로직 검증 (실제 NHPLUG 호출 없음)."""

from unittest.mock import patch

import pytest

from app.config import account_env_key
from app.orders import (
    WebhookValidationError,
    build_input_0,
    prepare_order,
    process_webhook,
    resolve_path,
)


def _run_webhook(endpoint: str, account_label: str, payload: dict):
    return process_webhook(
        endpoint=endpoint,
        account_label=account_label,
        account_env_key=account_env_key(account_label),
        payload=payload,
    )


class TestValidOrders:
    def test_kr_buy_api1(self, kr_buy_payload):
        with patch("app.orders.call") as mock_call:
            result = _run_webhook("API1", "API1", kr_buy_payload)

        path, input_0 = prepare_order(
            market="KR",
            side="BUY",
            ticker="005930",
            qty=10,
            account_env_key="NH_ACCOUNT_1",
        )

        assert result["ok"] is True
        assert result["mode"] == "dry_run"
        assert result["account"] == "API1"
        assert result["market"] == "KR"
        assert result["side"] == "BUY"
        assert path == "/krstock/order/v1/cashBuy"
        assert input_0 == {
            "act_no": "1111111111",
            "iem_cd": "005930",
            "orr_qty": 10,
            "nmn_pr_tp_cd": "05",
            "orr_cnd_dit_cd": "00",
            "ssl_nmn_pr_dit_cd": "00",
            "rmt_mkt_cd": "KRX",
            "sor_mkt_sli_yn": "N",
        }
        assert "orr_pr" not in input_0
        assert mock_call.call_count == 0

    def test_kr_sell_api2(self, kr_sell_payload):
        with patch("app.orders.call") as mock_call:
            result = _run_webhook("API2", "API2", kr_sell_payload)

        path, input_0 = prepare_order(
            market="KR",
            side="SELL",
            ticker="005930",
            qty=10,
            account_env_key="NH_ACCOUNT_2",
        )

        assert result["ok"] is True
        assert result["account"] == "API2"
        assert result["side"] == "SELL"
        assert path == "/krstock/order/v1/cashSell"
        assert input_0["act_no"] == "2222222222"
        assert input_0["iem_cd"] == "005930"
        assert input_0["nmn_pr_tp_cd"] == "05"
        assert mock_call.call_count == 0

    def test_us_buy_api1(self, us_buy_payload):
        with patch("app.orders.call") as mock_call:
            result = _run_webhook("API1", "API1", us_buy_payload)

        path, input_0 = prepare_order(
            market="US",
            side="BUY",
            ticker="SOXL",
            qty=10,
            account_env_key="NH_ACCOUNT_1",
            country_code="200",
        )

        assert result["ok"] is True
        assert result["market"] == "US"
        assert result["side"] == "BUY"
        assert path == "/gbstock/order/v1/buy"
        assert input_0 == {
            "act_no": "1111111111",
            "fc_sec_trd_nat_cd": "200",
            "iem_cd": "SOXL",
            "orr_qty": 10,
            "ahi_nmn_pr_tp_cd": "03",
            "wtm_cur_knd_cd": "1",
        }
        assert "fc_orr_uit_pr" not in input_0
        assert mock_call.call_count == 0

    def test_us_sell_api2(self, us_sell_payload):
        with patch("app.orders.call") as mock_call:
            result = _run_webhook("API2", "API2", us_sell_payload)

        path, input_0 = prepare_order(
            market="US",
            side="SELL",
            ticker="SOXL",
            qty=10,
            account_env_key="NH_ACCOUNT_2",
            country_code="200",
        )

        assert result["ok"] is True
        assert result["side"] == "SELL"
        assert path == "/gbstock/order/v1/sell"
        assert input_0["act_no"] == "2222222222"
        assert input_0["fc_sec_trd_nat_cd"] == "200"
        assert input_0["ahi_nmn_pr_tp_cd"] == "03"
        assert "wtm_cur_knd_cd" not in input_0
        assert mock_call.call_count == 0


class TestRouting:
    def test_api1_uses_account_1(self, kr_buy_payload):
        with patch("app.orders.call"):
            _run_webhook("API1", "API1", kr_buy_payload)

        _, input_0 = prepare_order(
            market="KR",
            side="BUY",
            ticker="005930",
            qty=10,
            account_env_key="NH_ACCOUNT_1",
        )
        assert input_0["act_no"] == "1111111111"
        assert input_0["act_no"] != "2222222222"

    def test_api2_uses_account_2(self, kr_sell_payload):
        with patch("app.orders.call"):
            _run_webhook("API2", "API2", kr_sell_payload)

        _, input_0 = prepare_order(
            market="KR",
            side="SELL",
            ticker="005930",
            qty=10,
            account_env_key="NH_ACCOUNT_2",
        )
        assert input_0["act_no"] == "2222222222"
        assert input_0["act_no"] != "1111111111"


class TestPaths:
    @pytest.mark.parametrize(
        ("market", "side", "expected"),
        [
            ("KR", "BUY", "/krstock/order/v1/cashBuy"),
            ("KR", "SELL", "/krstock/order/v1/cashSell"),
            ("US", "BUY", "/gbstock/order/v1/buy"),
            ("US", "SELL", "/gbstock/order/v1/sell"),
        ],
    )
    def test_resolve_path(self, market, side, expected):
        assert resolve_path(market, side) == expected


class TestInvalidRequests:
    @pytest.mark.parametrize("qty", [0, -1, 10.5, "10"])
    def test_invalid_qty(self, kr_buy_payload, qty):
        payload = {**kr_buy_payload, "qty": qty}
        with patch("app.orders.call") as mock_call:
            with pytest.raises(WebhookValidationError):
                _run_webhook("API1", "API1", payload)
        assert mock_call.call_count == 0

    @pytest.mark.parametrize("action", ["hold", "test", "abc", ""])
    def test_invalid_action(self, kr_buy_payload, action):
        payload = {**kr_buy_payload, "action": action}
        with patch("app.orders.call") as mock_call:
            with pytest.raises(WebhookValidationError):
                _run_webhook("API1", "API1", payload)
        assert mock_call.call_count == 0

    def test_domestic_exchange_with_us_ticker(self, kr_buy_payload):
        payload = {**kr_buy_payload, "ticker": "SOXL", "exchange": "KRX"}
        with patch("app.orders.call") as mock_call:
            with pytest.raises(WebhookValidationError):
                _run_webhook("API1", "API1", payload)
        assert mock_call.call_count == 0

    def test_unknown_exchange(self, us_buy_payload):
        payload = {**us_buy_payload, "exchange": "UNKNOWN"}
        with patch("app.orders.call") as mock_call:
            with pytest.raises(WebhookValidationError):
                _run_webhook("API1", "API1", payload)
        assert mock_call.call_count == 0

    def test_missing_ticker(self, kr_buy_payload):
        payload = {**kr_buy_payload}
        del payload["ticker"]
        with pytest.raises(WebhookValidationError):
            _run_webhook("API1", "API1", payload)

    def test_missing_exchange_non_domestic_ticker(self, us_buy_payload):
        payload = {**us_buy_payload}
        del payload["exchange"]
        with pytest.raises(WebhookValidationError):
            _run_webhook("API1", "API1", payload)

    def test_missing_exchange_domestic_ticker_allowed(self, kr_buy_payload):
        payload = {**kr_buy_payload}
        del payload["exchange"]
        with patch("app.orders.call") as mock_call:
            result = _run_webhook("API1", "API1", payload)
        assert result["ok"] is True
        assert result["market"] == "KR"
        assert result["exchange"] == "KRX"
        assert mock_call.call_count == 0

    def test_missing_action(self, kr_buy_payload):
        payload = {**kr_buy_payload}
        del payload["action"]
        with pytest.raises(WebhookValidationError):
            _run_webhook("API1", "API1", payload)

    def test_missing_qty(self, kr_buy_payload):
        payload = {**kr_buy_payload}
        del payload["qty"]
        with pytest.raises(WebhookValidationError):
            _run_webhook("API1", "API1", payload)

    def test_missing_price(self, kr_buy_payload):
        payload = {**kr_buy_payload}
        del payload["price"]
        with pytest.raises(WebhookValidationError):
            _run_webhook("API1", "API1", payload)


class TestDryRunSafety:
    def test_dry_run_never_calls_nhplug(self, kr_buy_payload, us_buy_payload):
        payloads = [kr_buy_payload, us_buy_payload]
        with patch("app.orders.call") as mock_call:
            for i, payload in enumerate(payloads):
                endpoint = f"API{i + 1}"
                _run_webhook(endpoint, endpoint, {**payload, "qty": payload["qty"] + i})
        assert mock_call.call_count == 0


class TestCallFormat:
    def test_call_receives_path_and_input_0_not_wrapped(self, monkeypatch, kr_buy_payload):
        monkeypatch.setenv("NH_DRY_RUN", "false")

        with patch("app.orders.call", return_value={"Output_0": {"mkt_orr_no": "123"}}) as mock_call:
            _run_webhook("API1", "API1", kr_buy_payload)

        assert mock_call.call_count == 1
        path, input_0 = mock_call.call_args.args
        assert path == "/krstock/order/v1/cashBuy"
        assert isinstance(input_0, dict)
        assert "Input_0" not in input_0
        assert input_0["act_no"] == "1111111111"
        assert input_0["iem_cd"] == "005930"


class TestSensitiveLogging:
    def test_logs_do_not_expose_secrets(self, caplog, kr_buy_payload, us_sell_payload):
        from tests.conftest import KEY_1, KEY_2, SECRET_1, SECRET_2

        import logging

        caplog.set_level(logging.INFO, logger="app.orders")

        with patch("app.orders.call"):
            _run_webhook("API1", "API1", kr_buy_payload)
            _run_webhook("API2", "API2", {**us_sell_payload, "qty": 11})

        log_text = caplog.text.lower()
        assert KEY_1.lower() not in log_text
        assert SECRET_1.lower() not in log_text
        assert KEY_2.lower() not in log_text
        assert SECRET_2.lower() not in log_text
        assert "1111111111" not in log_text
        assert "2222222222" not in log_text
        assert "nh_account_1" not in log_text
        assert "nh_account_2" not in log_text
        assert "token" not in log_text


class TestUsSellNoWtmCur:
    def test_us_sell_input_has_no_wtm_cur_knd_cd(self):
        input_0 = build_input_0(market="US", side="SELL", ticker="SOXL", qty=10, country_code="200")
        assert "wtm_cur_knd_cd" not in input_0

    def test_us_buy_input_has_wtm_cur_knd_cd(self):
        input_0 = build_input_0(market="US", side="BUY", ticker="SOXL", qty=10, country_code="200")
        assert input_0["wtm_cur_knd_cd"] == "1"
