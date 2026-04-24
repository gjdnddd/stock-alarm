import os, yfinance as yf, requests, json, time
from datetime import datetime

class VisualAlarmEngine:
    def __init__(self):
        self.config = self.get_gist_state()
        self.report = []

    def get_gist_state(self):
        token = os.environ.get('MY_GITHUB_TOKEN')
        gist_id = os.environ.get('MY_GIST_ID')
        url = f"https://api.github.com/gists/{gist_id}"
        headers = {"Authorization": f"token {token}"}
        res = requests.get(url, headers=headers)
        return json.loads(res.json()['files']['stock_data.json']['content'])

    def get_market_data(self, ticker):
        stock = yf.Ticker(ticker)
        df = stock.history(period="max")
        if df.empty: return {"ath": 0, "close": 0}
        return {"ath": df['Close'].max(), "close": df['Close'].iloc[-1]}

    def run(self):
        # 스트림릿 강제 기상 (Anti-Sleep)
        app_url = "https://stock-alarm-nwgxkui9krfqw6xddswa6n.streamlit.app/"
        try: requests.get(app_url, timeout=10)
        except: pass

        # 현재 시간 (KST 기준)
        now = datetime.now()
        now_hour = (now.hour + 9) % 24
        now_minute = now.minute

        # [최종 로직] 오전 7시 또는 오후 4시 50분 또는 수동 실행 시 리포트 생성
        # cron 설정과 맞물려 해당 시간에 실행될 때 분석을 수행합니다.
        self.execute_stock_analysis()
        self.save_and_send()

    def execute_stock_analysis(self):
        tickers = ["QQQ", "SOXX"]
        for t in tickers:
            data = self.get_market_data(t)
            cur_p, ath_now = data['close'], data['ath']
            t_data = self.config.get(t, {})
            
            current_drop = (cur_p / ath_now - 1) * 100 if ath_now > 0 else 0
            msg = f"*{t}* (현재: `${cur_p:.2f}` / ATH대비: {current_drop:.1f}%)\n"
            
            # 무한매수 로직
            infi = t_data.get("Infi", {})
            infi_ref = infi.get("High_After_End", 0)
            infi_drop = (cur_p / infi_ref - 1) * 100 if infi_ref > 0 else 0
            limit = -3 if t == "QQQ" else -4
            
            if infi_drop <= limit:
                msg += f"🔴 [무매-즉시] 타겟 도달! ({infi_drop:.1f}%)\n"
            elif infi_drop <= limit + 1.0:
                msg += f"🟡 [무매-준비] 근접! (현재 {infi_drop:.1f}%)\n"

            # 사이클 전략 (매도 감시)
            for c_key in ["New", "Old"]:
                cycle = t_data.get(c_key, {})
                if cycle.get("Status") == "ACTIVE":
                    frozen_ath = cycle.get("Target_ATH", 0)
                    r1 = 1.2 if t == "QQQ" else 1.3
                    dist_r1 = (frozen_ath * r1 / cur_p - 1) * 100
                    if cur_p >= frozen_ath * r1 * 0.95:
                        msg += f"💰 [{c_key}-매도] 목표가까지 {dist_r1:+.1f}% 남음\n"

            self.report.append(msg)

    def save_and_send(self):
        if not self.report: return
        
        token = os.environ.get('MY_TELEGRAM_TOKEN')
        chat_id = os.environ.get('MY_CHAT_ID')
        message = '\n\n'.join(self.report)
        
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)

if __name__ == "__main__":
    VisualAlarmEngine().run()
