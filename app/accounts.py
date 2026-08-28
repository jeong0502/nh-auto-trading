"""NHPLUG 인증 및 계좌 조회 (/n2/acctinfo)."""

import logging
from typing import Any

from nhplug import NhplugError, call, get_token

from app.config import (
    ENDPOINT_ACCOUNTS,
    expected_acct_types,
    get_account_number,
    has_api_credentials,
)

logger = logging.getLogger(__name__)

ACCTINFO_PATH = "/n2/acctinfo"


class AccountError(Exception):
    """계좌 설정·조회·검증 오류."""


def mask_account_no(acct_no: str) -> str:
    """계좌번호 마스킹 (예: 12345678***)."""
    if len(acct_no) <= 3:
        return "***"
    return acct_no[:-3] + "***"


def authenticate() -> None:
    """공식 SDK get_token()으로 인증 (토큰 값은 반환·로그하지 않음)."""
    get_token()


def fetch_account_list() -> list[dict[str, Any]]:
    """POST /n2/acctinfo — 계좌 목록 조회."""
    data = call(ACCTINFO_PATH, {})
    output_0 = data.get("Output_0", [])

    if isinstance(output_0, dict):
        return [output_0]
    if isinstance(output_0, list):
        return output_0
    return []


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


def validate_all_configured_accounts() -> dict[str, Any]:
    """설정된 NH_ACCOUNT_1/2를 acctinfo와 대조 검증."""
    targets: list[tuple[str, str]] = []
    for label, env_key in ENDPOINT_ACCOUNTS.items():
        if get_account_number(env_key):
            targets.append((label, env_key))

    if not targets:
        return {"skipped": True, "validated": 0, "count": 0}

    if not has_api_credentials():
        raise AccountError("NHPLUG API credentials are not configured")

    authenticate()
    accounts = fetch_account_list()

    for label, env_key in targets:
        validate_configured_account(label=label, env_key=env_key, accounts=accounts)

    return {
        "skipped": False,
        "validated": len(targets),
        "count": len(accounts),
    }


__all__ = [
    "ACCTINFO_PATH",
    "AccountError",
    "authenticate",
    "fetch_account_list",
    "mask_account_no",
    "validate_acct_type",
    "validate_all_configured_accounts",
    "validate_configured_account",
]
