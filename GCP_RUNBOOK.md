# Stock Alarm GCP Runbook

## 배포 대상 최소 파일

- `main.py`
- `requirements.txt`
- `Dockerfile`

로컬 테스트 전용 파일은 배포 이미지에 포함하지 않는다.

- `manual_test_alarm.ps1`
- `stock_data.test.json`

## 컨테이너 빌드 개념

이 이미지는 `python main.py`를 1회 실행하고 종료하는 배치 작업용이다.

- 상시 서버 아님
- Cloud Run **Service**보다 Cloud Run **Job**에 적합

## 필요한 Secret

| Cloud Secret ID | Cloud Run 환경변수 |
|---|---|
| `stock-alarm-github-token` | `MY_GITHUB_TOKEN` |
| `stock-alarm-gist-id` | `MY_GIST_ID` |
| `stock-alarm-telegram-token` | `MY_TELEGRAM_TOKEN` |
| `stock-alarm-chat-id` | `MY_CHAT_ID` |

자세한 설정은 `GCP_SECRETS.md`와 `gcp_secret_setup.ps1`을 사용한다.

## GCP 반영 순서

1. Artifact Registry 저장소 준비
2. 컨테이너 이미지 빌드 및 푸시
3. Cloud Run Job 생성
4. Secret Manager 연결
5. 수동 실행 테스트
6. Cloud Scheduler 연결

## Cloud Run Job 실행 커맨드

컨테이너 기본 실행은 아래와 같다.

```text
python main.py
```

추가 인자나 웹 포트는 필요 없다.

## 생성된 리소스

| 항목 | 값 |
|---|---|
| Project | `infin-stock-bot` |
| Region | `asia-northeast3` |
| Artifact Registry | `stock-alarm` |
| Image | `asia-northeast3-docker.pkg.dev/infin-stock-bot/stock-alarm/stock-alarm:latest` |
| Service Account | `stock-alarm-runner@infin-stock-bot.iam.gserviceaccount.com` |
| Cloud Run Job | `stock-alarm-job` |
| Task Timeout | `10m` |
| Max Retries | `1` |
| Scheduler Service Account | `stock-alarm-scheduler@infin-stock-bot.iam.gserviceaccount.com` |

## 수동 실행 테스트

실제 Telegram 알림과 Gist 갱신이 발생할 수 있다.

```powershell
gcloud run jobs execute stock-alarm-job --region "asia-northeast3" --project "infin-stock-bot" --wait
```

검증 완료:

- `stock-alarm-job-tq6nq`
- `1 task completed successfully`
- container `exit(0)`

## Cloud Scheduler

| Scheduler Job | Schedule | Timezone | Target |
|---|---|---|---|
| `stock-alarm-0700-kst` | `0 7 * * 2-6` | `Asia/Seoul` | `stock-alarm-job` |
| `stock-alarm-1650-kst` | `50 16 * * 1-5` | `Asia/Seoul` | `stock-alarm-job` |

Scheduler는 Cloud Run Jobs v2 API endpoint를 HTTP POST로 호출한다.

```text
https://run.googleapis.com/v2/projects/infin-stock-bot/locations/asia-northeast3/jobs/stock-alarm-job:run
```

수동 Scheduler 트리거 테스트:

```powershell
gcloud scheduler jobs run stock-alarm-1650-kst --location "asia-northeast3" --project "infin-stock-bot"
```

이 명령은 실제 Telegram 알림과 Gist 갱신을 발생시킬 수 있다.

## 예약 실행 확인

예약 실행 후 최근 execution을 확인한다.

```powershell
gcloud run jobs executions list --job stock-alarm-job --region "asia-northeast3" --project "infin-stock-bot" --limit 5
```

최근 로그:

```powershell
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="stock-alarm-job"' --project "infin-stock-bot" --limit 20 --format "value(timestamp,severity,textPayload)"
```

성공 기준:

- 새 execution 생성
- execution 성공
- container `exit(0)`
- Telegram 메시지 수신

Scheduler 수동 트리거 검증 완료:

- Scheduler Job: `stock-alarm-1650-kst`
- Execution: `stock-alarm-job-pc9fj`
- Run by: `stock-alarm-scheduler@infin-stock-bot.iam.gserviceaccount.com`
- Result: `1 task completed successfully`
- container `exit(0)`

## GitHub Actions 백업

`run_alarm.yml`의 자동 schedule은 비활성화했다.

남은 트리거:

- `workflow_dispatch`

GitHub Actions는 정기 실행을 담당하지 않고, 필요 시 수동 백업 실행용으로만 사용한다.
