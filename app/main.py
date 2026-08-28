import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from nhplug import NhplugError

from app.config import account_env_key
from app.orders import (
    DuplicateRequestError,
    WebhookValidationError,
    process_webhook,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

app = FastAPI(title="NH Auto Trading", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


def _handle_webhook(endpoint: str, account_label: str, payload: dict[str, Any]):
    try:
        return process_webhook(
            endpoint=endpoint,
            account_label=account_label,
            account_env_key=account_env_key(account_label),
            payload=payload,
        )
    except DuplicateRequestError as e:
        return {
            "ok": False,
            "mode": "dry_run",
            "duplicate": True,
            "account": account_label,
            "message": str(e),
        }
    except WebhookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NhplugError as e:
        raise HTTPException(
            status_code=502,
            detail={"category": e.category, "message": e.message},
        ) from e


@app.post("/webhook/api1")
async def webhook_api1(request: Request):
    payload = await request.json()
    return _handle_webhook("API1", "API1", payload)


@app.post("/webhook/api2")
async def webhook_api2(request: Request):
    payload = await request.json()
    return _handle_webhook("API2", "API2", payload)
