"""Webhook 검증 · 시장 구분 · NHPLUG 주문 실행 (기본 DRY RUN)."""

import logging
import re
import time
from typing import Any

from nhplug import NhplugError, call

from app.config import DEDUP_SECONDS, get_account_number, is_dry_run
from app.credentials import nhplug_credentials

logger = logging.getLogger(__name__)

DOMESTIC_EXCHANGES = {"KRX", "KOSPI", "KOSDAQ"}
US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "CBOE", "ARCA", "BATS", "NYSE ARCA"}

_RECENT_REQUESTS: dict[tuple[str, str, str, int], float] = {}


class WebhookValidationError(ValueError):
    """잘못된 Webhook 요청."""


class DuplicateRequestError(Exception):
    """짧은 시간 안에 동일 요청이 반복됨."""


def normalize_action(raw: str) -> str:
    action = (raw or "").strip().upper()
    if action not in ("BUY", "SELL"):
        raise WebhookValidationError(f"Unsupported action: {raw!r}")
    return action


def validate_ticker(raw: str) -> str:
    ticker = (raw or "").strip()
    if not ticker:
        raise WebhookValidationError("ticker is required")
    return ticker


def validate_qty(raw: Any) -> int:
    if isinstance(raw, bool) or raw is None:
        raise WebhookValidationError("qty must be a positive integer")

    if isinstance(raw, int):
        qty = raw
    elif isinstance(raw, float):
        if not raw.is_integer():
            raise WebhookValidationError("qty must be a positive integer")
        qty = int(raw)
    else:
        raise WebhookValidationError("qty must be a positive integer")

    if qty <= 0:
        raise WebhookValidationError("qty must be a positive integer")
    return qty


def validate_price(raw: Any) -> float:
    if raw is None:
        raise WebhookValidationError("price must be a number greater than 0")

    try:
        price = float(raw)
    except (TypeError, ValueError):
        raise WebhookValidationError("price must be a number greater than 0") from None

    if price <= 0:
        raise WebhookValidationError("price must be a number greater than 0")
    return price


def _is_domestic_ticker(ticker: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", ticker))


def classify_market(ticker: str, exchange: str) -> dict[str, str]:
    """국내(KR) / 미국(US) 구분. 충돌 시 예외."""
    ex = (exchange or "").strip().upper()

    if ex in DOMESTIC_EXCHANGES:
        if not _is_domestic_ticker(ticker):
            raise WebhookValidationError(
                f"Market conflict: domestic exchange {exchange!r} with non-domestic ticker {ticker!r}"
            )
        return {"market": "KR", "exchange": ex}

    if ex in US_EXCHANGES:
        return {"market": "US", "country_code": "200"}

    if not ex and _is_domestic_ticker(ticker):
        return {"market": "KR", "exchange": "KRX"}

    if not ex:
        raise WebhookValidationError("exchange is required")

    raise WebhookValidationError(f"Unsupported exchange: {exchange!r}")


def check_duplicate(endpoint: str, action: str, ticker: str, qty: int) -> None:
    key = (endpoint, action, ticker, qty)
    now = time.time()

    expired = [k for k, ts in _RECENT_REQUESTS.items() if now - ts >= DEDUP_SECONDS]
    for k in expired:
        del _RECENT_REQUESTS[k]

    if key in _RECENT_REQUESTS:
        raise DuplicateRequestError("Duplicate request ignored")

    _RECENT_REQUESTS[key] = now


def build_input_0(
    *,
    market: str,
    side: str,
    ticker: str,
    qty: int,
    country_code: str | None = None,
) -> dict[str, Any]:
    """nhplug.call(path, input_0)에 넣을 Input_0 dict (act_no 제외)."""
    if market == "KR":
        return {
            "iem_cd": ticker,
            "orr_qty": qty,
            "nmn_pr_tp_cd": "05",
            "orr_cnd_dit_cd": "00",
            "ssl_nmn_pr_dit_cd": "00",
            "rmt_mkt_cd": "KRX",
            "sor_mkt_sli_yn": "N",
        }

    if market == "US":
        input_0: dict[str, Any] = {
            "fc_sec_trd_nat_cd": country_code or "200",
            "iem_cd": ticker,
            "orr_qty": qty,
            "ahi_nmn_pr_tp_cd": "03",
        }
        if side == "BUY":
            # openapi.json 권장값이 아닌 1차 모의투자 테스트 선택값
            input_0["wtm_cur_knd_cd"] = "2"
        return input_0

    raise WebhookValidationError(f"Unsupported market: {market}")


def resolve_path(market: str, side: str) -> str:
    if market == "KR":
        return (
            "/krstock/order/v1/cashBuy"
            if side == "BUY"
            else "/krstock/order/v1/cashSell"
        )
    if market == "US":
        return (
            "/gbstock/order/v1/buy"
            if side == "BUY"
            else "/gbstock/order/v1/sell"
        )
    raise WebhookValidationError(f"Unsupported market: {market}")


def prepare_order(
    *,
    market: str,
    side: str,
    ticker: str,
    qty: int,
    account_env_key: str,
    country_code: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """NHPLUG path와 Input_0(act_no 포함)를 생성합니다."""
    path = resolve_path(market, side)
    input_0 = build_input_0(
        market=market,
        side=side,
        ticker=ticker,
        qty=qty,
        country_code=country_code,
    )

    act_no = get_account_number(account_env_key)
    if act_no:
        input_0["act_no"] = act_no
    elif not is_dry_run():
        raise WebhookValidationError(f"Account not configured: {account_env_key}")

    return path, input_0


def execute_order(
    *,
    market: str,
    side: str,
    ticker: str,
    qty: int,
    account_label: str,
    account_env_key: str,
    country_code: str | None = None,
) -> dict[str, Any]:
    """path·Input_0 생성 후 DRY RUN이면 call() 생략, 아니면 nhplug.call() 실행."""
    path, input_0 = prepare_order(
        market=market,
        side=side,
        ticker=ticker,
        qty=qty,
        account_env_key=account_env_key,
        country_code=country_code,
    )

    if is_dry_run():
        logger.info("[DRY_RUN] NHPLUG call skipped")
        return {
            "executed": False,
            "mode": "dry_run",
            "path": path,
        }

    logger.info("[NHPLUG] calling %s", path)
    try:
        with nhplug_credentials(account_label):
            data = call(path, input_0)
    except NhplugError as e:
        logger.error(
            "[NHPLUG] order failed category=%s message=%s",
            e.category,
            e.message,
        )
        raise

    logger.info("[NHPLUG] order request sent")

    result: dict[str, Any] = {
        "executed": True,
        "mode": "live",
        "path": path,
    }

    output_0 = data.get("Output_0") if isinstance(data, dict) else None
    if isinstance(output_0, dict):
        if "mkt_orr_no" in output_0:
            result["order_no"] = output_0.get("mkt_orr_no")
        if "orr_no" in output_0:
            result["order_no"] = output_0.get("orr_no")

    return result


def process_webhook(
    *,
    endpoint: str,
    account_label: str,
    account_env_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    action = normalize_action(str(payload.get("action", "")))
    ticker = validate_ticker(str(payload.get("ticker", "")))
    qty = validate_qty(payload.get("qty"))
    validate_price(payload.get("price"))
    exchange = str(payload.get("exchange", ""))

    market_info = classify_market(ticker, exchange)
    market = market_info["market"]

    check_duplicate(endpoint, action, ticker, qty)

    logger.info(
        "[WEBHOOK] endpoint=%s action=%s ticker=%s exchange=%s qty=%s",
        endpoint,
        action,
        ticker,
        exchange,
        qty,
    )
    logger.info("[ROUTING] account=%s", account_label)

    if market == "KR":
        logger.info("[MARKET] KR exchange=%s", market_info.get("exchange", ""))
    else:
        logger.info("[MARKET] US country_code=%s", market_info.get("country_code", ""))

    logger.info(
        "[ORDER] account=%s market=%s side=%s ticker=%s qty=%s order_type=MARKET",
        account_label,
        market,
        action,
        ticker,
        qty,
    )

    order_result = execute_order(
        market=market,
        side=action,
        ticker=ticker,
        qty=qty,
        account_label=account_label,
        account_env_key=account_env_key,
        country_code=market_info.get("country_code"),
    )

    response: dict[str, Any] = {
        "ok": True,
        "mode": order_result["mode"],
        "account": account_label,
        "market": market,
        "side": action,
        "ticker": ticker,
        "qty": qty,
        "order_type": "MARKET",
    }

    if market == "KR":
        response["exchange"] = market_info.get("exchange")
    else:
        response["country_code"] = market_info.get("country_code")

    if order_result.get("order_no") is not None:
        response["order_no"] = order_result["order_no"]

    return response
