"""NHPLUG 인증 및 계좌 조회 (/n2/acctinfo) — 사용자별 분리."""

import logging
from typing import Any

from nhplug import NhplugError, call, get_token

from app.config import (
    ENDPOINT_ACCOUNTS,
    expected_acct_types,
    get_account_number,
    has_api_credentials,
)
from app.credentials import nhplug_credentials

logger = logging.getLogger(__name__)

ACCTINFO_PATH = "/n2/acctinfo"


class AccountError(Exception):
    """계좌 설정·조회·검증 오류."""


def mask_account_no(acct_no: str) -> str:
    """계좌번호 마스킹 (예: 12345678***)."""
    if len(acct_no) <= 3:
        return "***"
    return acct_no[:-3] + "***"


def mask_account_tail(acct_no: str, visible: int = 4) -> str:
    """계좌번호 마스킹 — 마지막 visible 자리만 표시 (예: *******6881)."""
    s = (acct_no or "").strip()
    if len(s) <= visible:
        return "***"
    return "*" * (len(s) - visible) + s[-visible:]


def authenticate_for(label: str) -> None:
    """사용자별 get_token() (토큰 값은 반환·로그하지 않음)."""
    with nhplug_credentials(label):
        get_token()


def _fetch_account_list_unlocked() -> list[dict[str, Any]]:
    """nhplug_credentials context 안에서 호출."""
    data = call(ACCTINFO_PATH, {})
    output_0 = data.get("Output_0", [])

    if isinstance(output_0, dict):
        return [output_0]
    if isinstance(output_0, list):
        return output_0
    return []


def fetch_account_list_for(label: str) -> list[dict[str, Any]]:
    """사용자별 POST /n2/acctinfo."""
    with nhplug_credentials(label):
        get_token()
        return _fetch_account_list_unlocked()


def validate_acct_type(acct_type: str, *, label: str = "") -> None:
    """acct_type이 현재 NHPLUG_BASE_URL 환경과 일치하는지 확인."""
    allowed = expected_acct_types()
    if not allowed:
        raise AccountError("Cannot determine environment from NHPLUG_BASE_URL")

    if acct_type not in allowed:
        prefix = f"{label}: " if label else ""
        raise AccountError(
            f"{prefix}acct_type {acct_type!r} does not match environment "
            f"(expected {sorted(allowed)})"
        )


def _find_account(acct_no: str, accounts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in accounts:
        if str(item.get("acct_no", "")).strip() == acct_no:
            return item
    return None


def validate_configured_account(
    *,
    label: str,
    env_key: str,
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """환경변수 계좌가 acctinfo 목록에 있고 acct_type이 환경과 일치하는지 확인."""
    acct_no = get_account_number(env_key)
    if not acct_no:
        raise AccountError(f"{label}: {env_key} is not configured")

    found = _find_account(acct_no, accounts)
    if not found:
        raise AccountError(f"{label}: configured account not found in acctinfo list")

    acct_type = str(found.get("acct_type", "")).strip()
    validate_acct_type(acct_type, label=label)

    logger.info(
        "[ACCOUNT] %s validated acct=%s acct_type=%s",
        label,
        mask_account_no(acct_no),
        acct_type,
    )
    return found


def validate_account_for(label: str) -> dict[str, Any]:
    """단일 API label: credentials → acctinfo → 해당 NH_ACCOUNT_n 검증."""
    env_key = ENDPOINT_ACCOUNTS[label]
    if not get_account_number(env_key):
        raise AccountError(f"{label}: {env_key} is not configured")
    if not has_api_credentials(label):
        raise AccountError(f"{label}: NHPLUG credentials are not configured")

    accounts = fetch_account_list_for(label)
    return validate_configured_account(label=label, env_key=env_key, accounts=accounts)


def validate_all_configured_accounts() -> dict[str, Any]:
    """API1/API2 각각 별도 credentials·acctinfo로 검증."""
    validated: list[str] = []

    for label, env_key in ENDPOINT_ACCOUNTS.items():
        if not get_account_number(env_key):
            continue
        if not has_api_credentials(label):
            raise AccountError(f"{label}: NHPLUG credentials are not configured")

        accounts = fetch_account_list_for(label)
        validate_configured_account(label=label, env_key=env_key, accounts=accounts)
        validated.append(label)

    if not validated:
        return {"skipped": True, "validated": 0, "labels": []}

    return {
        "skipped": False,
        "validated": len(validated),
        "labels": validated,
    }


__all__ = [
    "ACCTINFO_PATH",
    "AccountError",
    "authenticate_for",
    "fetch_account_list_for",
    "mask_account_no",
    "mask_account_tail",
    "validate_acct_type",
    "validate_account_for",
    "validate_all_configured_accounts",
    "validate_configured_account",
]
