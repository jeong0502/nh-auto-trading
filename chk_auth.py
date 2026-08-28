"""STEP 2: NHPLUG 인증 테스트 — API1/API2 사용자별 분리."""

import os
import sys

from nhplug import NhplugError, __version__, cache_path, get_base_url, get_token, loaded_files

from app.accounts import AccountError, validate_all_configured_accounts
from app.config import ENDPOINT_ACCOUNTS, current_env, get_account_number, has_api_credentials
from app.credentials import nhplug_credentials


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

    if any(
        get_account_number(env_key)
        for env_key in ENDPOINT_ACCOUNTS.values()
    ):
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
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
