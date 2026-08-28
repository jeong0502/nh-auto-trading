"""STEP 2: NHPLUG 인증 테스트.

공식 SDK 샘플(snippets/auth/issue_token)과 동일하게 get_token() 으로
토큰 발급·캐시를 확인합니다. 토큰 값은 출력하지 않습니다.
"""

import os
import sys

from nhplug import NhplugError, __version__, cache_path, get_base_url, get_token, loaded_files

from app.accounts import AccountError, validate_all_configured_accounts
from app.config import current_env, has_api_credentials


def main() -> int:
    print(f"NHPLUG SDK version: {__version__}")
    print(f"Environment: {current_env()}")
    print(f"Base URL: {get_base_url()}")

    env_files = loaded_files()
    if env_files:
        print(f"Env files: {', '.join(env_files)}")
    else:
        print("Env files: (none)")

    try:
        # 1차: 토큰 발급 (또는 캐시에서 로드)
        get_token()
        cache_file = cache_path()
        cache_exists = cache_file.exists()

        # 2차: 캐시 재사용 확인 (토큰 값은 출력하지 않음)
        get_token()

        print(f"Token cache file: {'found' if cache_exists else 'not found'}")
        print("Authentication: SUCCESS")

        if has_api_credentials() and (
            os.environ.get("NH_ACCOUNT_1", "").strip()
            or os.environ.get("NH_ACCOUNT_2", "").strip()
        ):
            try:
                result = validate_all_configured_accounts()
                if result.get("skipped"):
                    print("Account validation: SKIPPED (accounts not configured)")
                else:
                    print(
                        f"Account validation: SUCCESS "
                        f"({result['validated']} configured, {result['count']} in acctinfo)"
                    )
            except AccountError as e:
                print("Account validation: FAILED")
                print(f"message: {e}")
                return 1

        return 0

    except NhplugError as e:
        print("Authentication: FAILED")
        print(f"category: {e.category}")
        print(f"message: {e.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
