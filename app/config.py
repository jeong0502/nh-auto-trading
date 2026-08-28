"""환경 설정."""

import os

# Webhook endpoint → 계좌 환경변수 키
ENDPOINT_ACCOUNTS = {
    "API1": "NH_ACCOUNT_1",
    "API2": "NH_ACCOUNT_2",
}

# Webhook endpoint → (APP_KEY env, APP_SECRET env)
ENDPOINT_CREDENTIALS = {
    "API1": ("NHPLUG_APP_KEY_1", "NHPLUG_APP_SECRET_1"),
    "API2": ("NHPLUG_APP_KEY_2", "NHPLUG_APP_SECRET_2"),
}

# 중복 요청 방지: 동일 키가 이 시간(초) 안에 다시 오면 무시
DEDUP_SECONDS = 30


def account_env_key(endpoint: str) -> str:
    """API1 → NH_ACCOUNT_1, API2 → NH_ACCOUNT_2"""
    return ENDPOINT_ACCOUNTS[endpoint]


def credential_env_keys(label: str) -> tuple[str, str]:
    """API1 → (NHPLUG_APP_KEY_1, NHPLUG_APP_SECRET_1)"""
    return ENDPOINT_CREDENTIALS[label]


def get_account_number(env_key: str) -> str | None:
    """환경변수에서 계좌번호(act_no)를 읽습니다. 없으면 None."""
    value = os.environ.get(env_key, "").strip()
    return value or None


def get_credentials(label: str) -> tuple[str, str] | None:
    """API label에 해당하는 APP_KEY/APP_SECRET. 없으면 None."""
    key_env, secret_env = credential_env_keys(label)
    app_key = os.environ.get(key_env, "").strip()
    app_secret = os.environ.get(secret_env, "").strip()
    if app_key and app_secret:
        return app_key, app_secret
    return None


def has_api_credentials(label: str) -> bool:
    """API label의 APP_KEY/APP_SECRET 설정 여부."""
    return get_credentials(label) is not None


def is_dry_run() -> bool:
    """기본값 true — 실제 nhplug.call()을 실행하지 않음."""
    value = os.environ.get("NH_DRY_RUN", "true").strip().lower()
    return value not in ("0", "false", "no")


def current_env() -> str:
    """moapi 호스트면 mock, api 호스트면 live. nhplug 미설정 시 unknown."""
    base = os.environ.get("NHPLUG_BASE_URL", "").strip().lower()
    if base:
        if "moapi." in base:
            return "mock"
        if "api." in base and "moapi." not in base:
            return "live"

    try:
        from nhplug import get_base_url

        host = get_base_url().split("//")[-1].split("/")[0].lower()
        if host.startswith("moapi."):
            return "mock"
        if host.startswith("api."):
            return "live"
    except Exception:
        pass
    return "unknown"


def expected_acct_types() -> frozenset[str]:
    """현재 NHPLUG_BASE_URL 환경에 맞는 acct_type 집합."""
    env = current_env()
    if env == "mock":
        return frozenset({"03"})
    if env == "live":
        return frozenset({"01", "02"})
    return frozenset()
