"""STEP 2: NHPLUG 인증 테스트 — API1/API2 사용자별 분리."""

import sys
from typing import Any

from nhplug import NhplugError, __version__, cache_path, get_base_url, get_token, loaded_files

from app.accounts import (
    AccountError,
    fetch_account_list_for,
    mask_account_tail,
    validate_all_configured_accounts,
)
from app.config import ENDPOINT_ACCOUNTS, current_env, get_account_number, has_api_credentials
from app.credentials import nhplug_credentials

# acctinfo Output_0 항목에서 표시할 비민감 필드 (openapi 정본: acct_no, acct_type)
_ACCTINFO_DISPLAY_FIELDS = ("acct_type", "acct_name", "acct_nm", "prd_nm", "prd_name")


def _format_configured_account(env_key: str) -> str:
    configured = get_account_number(env_key)
    if not configured:
        return "(not set)"
    return mask_account_tail(configured)


def _format_acctinfo_item(item: dict[str, Any]) -> str:
    parts: list[str] = []
    acct_no = str(item.get("acct_no", "")).strip()
    if acct_no:
        parts.append(f"acct_no={mask_account_tail(acct_no)}")
    for field in _ACCTINFO_DISPLAY_FIELDS:
        if field == "acct_type":
            value = item.get("acct_type")
            if value is not None and str(value).strip():
                parts.append(f"acct_type={value!r}")
        else:
            value = item.get(field)
            if value is not None and str(value).strip():
                parts.append(f"{field}={value!r}")
    return ", ".join(parts) if parts else "(empty item)"


def _print_hyphen_hint(label: str, env_key: str) -> None:
    configured = get_account_number(env_key)
    if not configured or "-" not in configured:
        return
    normalized = configured.replace("-", "").strip()
    print(
        f"{label} hint: {env_key} contains hyphens; "
        f"code does NOT normalize — acctinfo expects digits only "
        f"(normalized masked: {mask_account_tail(normalized)})"
    )


def print_acctinfo_diagnostic(label: str) -> None:
    """/n2/acctinfo 결과를 마스킹해 출력 (인증·acctinfo만, 주문 없음)."""
    env_key = ENDPOINT_ACCOUNTS[label]
    print(f"{label} configured {env_key} (masked): {_format_configured_account(env_key)}")
    _print_hyphen_hint(label, env_key)

    try:
        accounts = fetch_account_list_for(label)
    except NhplugError as e:
        print(f"{label} acctinfo: FAILED")
        print(f"  category: {e.category}")
        print(f"  message: {e.message}")
        return

    print(f"{label} acctinfo: {len(accounts)} account(s)")
    if not accounts:
        print(f"  (no Output_0 items — check API credentials or account linkage)")
        return

    for index, item in enumerate(accounts, start=1):
        print(f"  [{index}] {_format_acctinfo_item(item)}")


def main() -> int:
    print(f"NHPLUG SDK version: {__version__}")
    print(f"Environment: {current_env()}")
    print(f"Base URL: {get_base_url()}")

    env_files = loaded_files()
    if env_files:
        print(f"Env files: {', '.join(env_files)}")
    else:
        print("Env files: (none)")

    any_auth = False
    auth_failed = False

    for label in ENDPOINT_ACCOUNTS:
        if not has_api_credentials(label):
            print(f"{label} authentication: SKIPPED (credentials not configured)")
            continue

        any_auth = True
        try:
            with nhplug_credentials(label):
                get_token()
                cache_file = cache_path()
                cache_exists = cache_file.exists()
                get_token()

            print(f"{label} authentication: SUCCESS")
            print(f"{label} token cache file: {'found' if cache_exists else 'not found'}")
        except NhplugError as e:
            auth_failed = True
            print(f"{label} authentication: FAILED")
            print(f"category: {e.category}")
            print(f"message: {e.message}")

    if not any_auth:
        print("Authentication: SKIPPED (no API credentials configured)")
        return 0

    if auth_failed:
        return 1

    configured_labels = [
        label
        for label, env_key in ENDPOINT_ACCOUNTS.items()
        if get_account_number(env_key) and has_api_credentials(label)
    ]

    if configured_labels:
        try:
            result = validate_all_configured_accounts()
            if result.get("skipped"):
                print("Account validation: SKIPPED (accounts not configured)")
            else:
                print(
                    f"Account validation: SUCCESS "
                    f"({result['validated']} configured: {', '.join(result['labels'])})"
                )
        except AccountError as e:
            print("Account validation: FAILED")
            print(f"message: {e}")
            print("--- acctinfo diagnostic (masked) ---")
            for label in configured_labels:
                print_acctinfo_diagnostic(label)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
