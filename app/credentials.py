"""API1/API2별 NHPLUG 자격증명을 SDK 환경변수에 안전하게 매핑."""

import os
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import TypeVar

from app.config import get_credentials

_SDK_APP_KEY = "NHPLUG_APP_KEY"
_SDK_APP_SECRET = "NHPLUG_APP_SECRET"
_lock = threading.RLock()

T = TypeVar("T")


class CredentialsError(ValueError):
    """자격증명 설정 오류."""


def _snapshot_sdk_env() -> dict[str, str | None]:
    return {
        _SDK_APP_KEY: os.environ.get(_SDK_APP_KEY),
        _SDK_APP_SECRET: os.environ.get(_SDK_APP_SECRET),
    }


def _restore_sdk_env(saved: dict[str, str | None]) -> None:
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@contextmanager
def nhplug_credentials(label: str) -> Generator[None, None, None]:
    """Lock + SDK가 읽는 NHPLUG_APP_KEY/SECRET을 해당 사용자 credentials로 일시 설정."""
    creds = get_credentials(label)
    if creds is None:
        raise CredentialsError(f"{label}: NHPLUG credentials are not configured")

    app_key, app_secret = creds
    with _lock:
        saved = _snapshot_sdk_env()
        try:
            os.environ[_SDK_APP_KEY] = app_key
            os.environ[_SDK_APP_SECRET] = app_secret
            yield
        finally:
            _restore_sdk_env(saved)


def run_with_credentials(label: str, fn: Callable[[], T]) -> T:
    """credentials context 안에서 fn 실행."""
    with nhplug_credentials(label):
        return fn()
