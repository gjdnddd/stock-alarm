# Stock Alarm GCP Secrets

## 목적

Cloud Run Job에서 `main.py`가 기존과 같은 환경변수명을 읽도록 Secret Manager 값을 준비한다.

## Secret 목록

| Cloud Secret ID | Cloud Run 환경변수 | 용도 |
|---|---|---|
| `stock-alarm-github-token` | `MY_GITHUB_TOKEN` | Gist 읽기/쓰기 토큰 |
| `stock-alarm-gist-id` | `MY_GIST_ID` | `stock_data.json` Gist ID |
| `stock-alarm-telegram-token` | `MY_TELEGRAM_TOKEN` | Telegram bot token |
| `stock-alarm-chat-id` | `MY_CHAT_ID` | Telegram 수신 chat id |

현재 `main.py`는 `yfinance`를 사용하므로 GCP 알람 실행에는 `FINNHUB_TOKEN`이 필요 없다.

## 실행 전 준비

Google Cloud CLI 로그인과 프로젝트 설정이 필요하다.

```powershell
gcloud auth login
gcloud config set project "PROJECT_ID"
```

## Secret 생성

```powershell
cd "C:\Users\gjdnd\OneDrive\4. AI\제미나이\미국주식알람"
.\gcp_secret_setup.ps1 -ProjectId "PROJECT_ID"
```

스크립트는 아래 값을 순서대로 입력받는다.

- `MY_GITHUB_TOKEN`
- `MY_GIST_ID`
- `MY_TELEGRAM_TOKEN`
- `MY_CHAT_ID`

값은 파일에 저장하지 않는다. Secret Manager로 전달하기 위해 임시 파일을 만들고, 처리 후 삭제한다.

## 다음 단계에서 사용할 매핑

Cloud Run Job 생성 시 아래처럼 환경변수와 Secret을 연결한다.

```text
MY_GITHUB_TOKEN = stock-alarm-github-token:latest
MY_GIST_ID = stock-alarm-gist-id:latest
MY_TELEGRAM_TOKEN = stock-alarm-telegram-token:latest
MY_CHAT_ID = stock-alarm-chat-id:latest
```

운영 안정화 후에는 `latest` 대신 특정 version pinning을 검토한다.
