# NH Auto Trading

TradingView Webhook → FastAPI → NHPLUG → 나무증권 주문 브릿지

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

헬스체크: http://127.0.0.1:8000/health

## TradingView Webhook URL

계좌 구분은 **Webhook URL**로 합니다. TradingView Alert JSON에는 `account` 필드를 넣지 않습니다.

배포 후 Render 도메인을 `<render-domain>`에 넣어 사용합니다.

| 계좌 | URL |
|------|-----|
| API1 | `https://<render-domain>/webhook/api1` |
| API2 | `https://<render-domain>/webhook/api2` |

### TradingView Alert JSON (변경 없음)

```json
{
  "action": "{{strategy.order.action}}",
  "ticker": "{{ticker}}",
  "exchange": "{{exchange}}",
  "price": {{close}},
  "qty": {{strategy.order.contracts}}
}
```

### 라우팅

```text
POST /webhook/api1 → NH_ACCOUNT_1 → act_no
POST /webhook/api2 → NH_ACCOUNT_2 → act_no
```

## Render 배포

### 시작 명령

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

- Render에서는 `0.0.0.0`을 사용합니다 (`127.0.0.1` 사용 금지).
- Python 3.10+ (`runtime.txt` 참고).

### 환경변수 (Render Dashboard)

`.env` 파일은 Render에서 사용하지 않습니다. Dashboard에서 아래 변수를 설정합니다.

| 변수 | 설명 |
|------|------|
| `NHPLUG_APP_KEY` | NHPLUG 앱 키 (비밀) |
| `NHPLUG_APP_SECRET` | NHPLUG 앱 시크릿 (비밀) |
| `NHPLUG_BASE_URL` | `https://moapi.nhplug.com:8443` (모의투자) |
| `NHPLUG_AUTH_URL` | `https://api.nhplug.com:8443` |
| `NH_ACCOUNT_1` | API1 계좌번호 (비밀) |
| `NH_ACCOUNT_2` | API2 계좌번호 (비밀) |
| `NH_DRY_RUN` | `true` (기본값, 실제 주문 차단) |

`render.yaml` Blueprint를 사용할 수도 있습니다.

### GitHub 연결 (STEP 9)

```bash
git init -b main
git add -A
git commit -m "Initial commit: NH auto trading webhook server"
gh auth login
gh repo create nh-auto-trading --public --source=. --remote=origin --push
```

`.env`, `.venv/`, `__pycache__/`는 Git에 포함되지 않습니다.

### Render Web Service 생성

1. [Render Dashboard](https://dashboard.render.com) → **New Web Service**
2. GitHub repository `nh-auto-trading` 연결
3. 설정 확인:
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check**: `/health`
4. 환경변수 (API KEY 발급 전):
   - `NH_DRY_RUN=true`
   - `NHPLUG_BASE_URL=https://moapi.nhplug.com:8443`
   - `NHPLUG_AUTH_URL=https://api.nhplug.com:8443`
   - `NHPLUG_APP_KEY`, `NHPLUG_APP_SECRET`, `NH_ACCOUNT_1`, `NH_ACCOUNT_2`는 **비워둠**

또는 Blueprint:

```bash
# Render Dashboard → Blueprints → render.yaml 연결
```

### 배포 후 외부 테스트

`<render-domain>`을 Render에서 확인한 실제 URL로 교체합니다.

```bash
# Health
curl https://<render-domain>/health

# API1 — 미국 BUY
curl -X POST https://<render-domain>/webhook/api1 \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"buy\",\"ticker\":\"SOXL\",\"exchange\":\"NASDAQ\",\"price\":20,\"qty\":10}"

# API2 — 미국 SELL
curl -X POST https://<render-domain>/webhook/api2 \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"sell\",\"ticker\":\"SOXL\",\"exchange\":\"NASDAQ\",\"price\":20,\"qty\":10}"

# API1 — 국내 BUY
curl -X POST https://<render-domain>/webhook/api1 \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"buy\",\"ticker\":\"005930\",\"exchange\":\"KRX\",\"price\":100000,\"qty\":1}"

# API2 — 국내 SELL
curl -X POST https://<render-domain>/webhook/api2 \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"sell\",\"ticker\":\"005930\",\"exchange\":\"KRX\",\"price\":100000,\"qty\":1}"
```

모든 요청은 `NH_DRY_RUN=true`이면 `mode=dry_run`으로 응답하고 실제 주문은 발생하지 않습니다.

### 헬스체크

```text
GET /health → {"status": "ok"}
```

NHPLUG 서버 상태와 무관하게 FastAPI 서버 생존 여부만 확인합니다.

## 로컬 Webhook 테스트

`NH_DRY_RUN=true` 상태에서:

```bash
# API1 — 미국 BUY
curl -X POST http://127.0.0.1:8000/webhook/api1 \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"buy\",\"ticker\":\"SOXL\",\"exchange\":\"NASDAQ\",\"price\":20,\"qty\":10}"

# API2 — 국내 SELL
curl -X POST http://127.0.0.1:8000/webhook/api2 \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"sell\",\"ticker\":\"005930\",\"exchange\":\"KRX\",\"price\":100000,\"qty\":10}"
```

## 인증·계좌 테스트

프로젝트 루트에 `.env`를 만든 뒤 (API KEY 발급 후):

```bash
python chk_auth.py
```

## 테스트

```bash
python -m pytest tests/ -v
```

## HTTP 응답 코드

| 상황 | 코드 |
|------|------|
| 정상 Webhook | 200 |
| 잘못된 payload | 400 |
| NHPLUG 오류 | 502 |

## 환경변수 (로컬)

`.env.example`을 참고해 `.env`를 만듭니다. `.env`는 Git에 커밋하지 않습니다.
