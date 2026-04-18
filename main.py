import os
import yfinance as yf
import requests
import json
import time
import logging
from datetime import datetime

# 1. 로깅 및 환경 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')

GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN")
GIST_ID = os.getenv("MY_GIST_ID")
TELEGRAM_TOKEN = os.getenv("MY_TELEGRAM_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

class StockAlarmSystem:
    def __init__(self):
        self.bot_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        self.gist_url = f"https://api.github.com/gists/{GIST_ID}"
        self.headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    # --- 유틸리티 기능 ---
    def send_tg(self, text):
        """텔레그램 메시지 발송"""
        url = f"{self.bot_url}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"텔레그램 발송 실패: {e}")

    def get_market_data(self, ticker):
        """최신 시세 및 ATH 취득 (3회 재시도)"""
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
        """Gist 저장소에서 현재 전략 상태 읽기"""
        try:
            res = requests.get(self.gist_url, headers=self.headers, timeout=10)
            files = res.json().get('files', {})
            content = files.get('stock_data.json', {}).get('content', '{}')
            return json.loads(content)
        except Exception as e:
            logging.error(f"Gist 읽기 실패: {e}")
            return {}

    def check_tax_season(self):
        """절세 및 주요 재무 일정 알람 (Step 9)"""
        today = datetime.now()
        month = today.month
        day = today.day
        tax_alarms = []
        
        # 세금 일정
        if month == 5 and 25 <= day <= 31:
            tax_alarms.append("📅 [절세] 5월 종합소득세 신고 기간입니다.")
        elif month == 7 and 25 <= day <= 31:
            tax_alarms.append("📅 [절세] 하반기 손익 중간 점검 시기입니다.")
        elif month == 12 and 20 <= day <= 31:
            tax_alarms.append("📅 [절세] 기본공제 250만원 활용 매도/재매수 검토!")
            
        return tax_alarms

    # --- 핵심 실행 로직 ---
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
            status = t_state.get("Status", "READY")

            if status == "PAUSED":
                report.append(f"⏸️ *{t}*: 감시 일시 중단 상태")
                continue

            # 기본 리포트 생성
            msg = f"*{t}* 현황\n- 현재가: `${cur_p:.2f}`\n- 하락률: `{drop_rate:.2f}%`"
            
            # 하락률 조건 알람 (사용자 전략 반영)
            if drop_rate <= -19:
                msg += "\n🚨 *[매수구간]* -19% 돌파! 진입 검토"
            elif drop_rate <= -10:
                msg += "\n⚠️ 하락률 -10% 돌파 중"
            
            report.append(msg)

        # 세금 및 일정 알람 추가
        tax_notes = self.check_tax_season()
        
        # 최종 메시지 조립
        full_msg = "📊 *미국주식 장 종료 리포트*\n\n" + "\n\n".join(report)
        
        if tax_notes:
            full_msg += "\n\n" + "--------------------\n" + "\n".join(tax_notes)

        # 발송
        self.send_tg(full_msg)

if __name__ == "__main__":
    # 필수 환경 변수 체크 후 실행
    if all([GITHUB_TOKEN, GIST_ID, TELEGRAM_TOKEN, CHAT_ID]):
        StockAlarmSystem().run()
    else:
        logging.error("환경 변수(Secrets) 설정이 누락되었습니다.")
