import os
import yfinance as yf
import requests
import json
import time
import logging
from datetime import datetime

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')

# 환경 변수 로드
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN")
GIST_ID = os.getenv("MY_GIST_ID")
TELEGRAM_TOKEN = os.getenv("MY_TELEGRAM_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

class StockAlarmSystem:
    def __init__(self):
        self.bot_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        self.gist_url = f"https://api.github.com/gists/{GIST_ID}"
        self.headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    def send_tg(self, text):
        """텔레그램 메시지 전송 (마크다운 지원)"""
        url = f"{self.bot_url}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"TG 전송 실패: {e}")

    def get_market_data(self, ticker):
        """yfinance 데이터 취득 (재시도 로직 포함)"""
        for i in range(3):
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(period="max")
                if df.empty: raise ValueError
                return {"ath": df['Close'].max(), "close": df['Close'].iloc[-1]}
            except:
                logging.warning(f"{ticker} 데이터 재시도 중... ({i+1}/3)")
                time.sleep(30)
        return None

    def get_gist_state(self):
        """Gist에서 상태 데이터 읽기"""
        try:
            res = requests.get(self.gist_url, headers=self.headers, timeout=10)
            files = res.json().get('files', {})
            content = files.get('stock_data.json', {}).get('content', '{}')
            return json.loads(content)
        except Exception as e:
            logging.error(f"Gist 읽기 실패: {e}")
            return {}

    def run(self):
        state = self.get_gist_state()
        tickers = ["QQQ", "SOXX"]
        report = []

        for t in tickers:
            data = self.get_market_data(t)
            if not data:
                report.append(f"❌ {t}: 데이터 취득 실패")
                continue

            cur_p = data["close"]
            ath = data["ath"]
            drop_rate = (cur_p / ath - 1) * 100
            t_state = state.get(t, {})
            
            # [알람 로직]
            status = t_state.get("Status", "READY")
            if status == "PAUSED":
                report.append(f"⏸️ {t}: 감시 중단 상태")
                continue

            # 기본 알람 텍스트 구성
            msg = f"*{t}* 현황\n- 현재가: ${cur_p:.2f}\n- 하락률: {drop_rate:.2f}%\n"
            
            # 조건 판단 (Step 3 로직 적용)
            # 여기서는 예시로 하락률이 -19% 이하일 때 경고 추가
            if drop_rate <= -19:
                msg += "🚨 [매수구간 진입!] 전고점 대비 하락"
            
            report.append(msg)

        # 최종 보고서 발송
        full_msg = "📊 *미국주식 장 종료 리포트*\n\n" + "\n\n".join(report)
        self.send_tg(full_msg)

if __name__ == "__main__":
    if all([GITHUB_TOKEN, GIST_ID, TELEGRAM_TOKEN, CHAT_ID]):
        StockAlarmSystem().run()
    else:
        print("환경 변수 설정이 누락되었습니다.")
