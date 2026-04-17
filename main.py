import yfinance as yf
import requests
import json
import time
import logging

# [설정] 본인의 정보로 채우세요
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN")
GIST_ID = os.getenv("MY_GIST_ID")
TELEGRAM_TOKEN = os.getenv("MY_TELEGRAM_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')

class StockAlarmSystem:
    def __init__(self):
        self.gist_url = f"https://api.github.com/gists/{GIST_ID}"
        self.headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        self.bot_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    # --- Step 1 & 2: 데이터 핸들링 ---
    def get_market_data(self, ticker_symbol):
        for i in range(3):
            try:
                t = yf.Ticker(ticker_symbol)
                df = t.history(period="max")
                if df.empty: raise ValueError
                return {"ath": df['Close'].max(), "close": df['Close'].iloc[-1]}
            except:
                time.sleep(300)
        return None

    def get_gist_state(self):
        res = requests.get(self.gist_url, headers=self.headers)
        files = res.json().get('files', {})
        content = files.get('stock_data.json', {}).get('content')
        return json.loads(content) if content else {}

    # --- Step 3 & 4: 로직 및 알람 ---
    def send_tg(self, text):
        requests.post(f"{self.bot_url}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

    def run(self):
        state = self.get_gist_state()
        tickers = ["QQQ", "SOXX"]
        final_report = "📊 *장 종료 알람 분석*\n\n"
        
        for t in tickers:
            data = self.get_market_data(t)
            if not data:
                self.send_tg(f"❌ {t} 데이터 취득 실패! 수동 확인 필요.")
                continue
            
            cur_price = data["close"]
            ath_now = data["ath"]
            t_state = state.get(t, {})
            
            # 여기서 앞서 만든 check_alarm_conditions 로직을 실행
            # (지면 관계상 핵심 로직만 요약 호출)
            # ... 알람 리스트 생성 ...
            
            final_report += f"*{t}*: ${cur_price:.2f} (ATH: ${ath_now:.2f})\n"
            # 조건 일치 시 리포트에 추가
        
        self.send_tg(final_report)

if __name__ == "__main__":
    app = StockAlarmSystem()
    app.run()