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
        # 1. 스트림릿 강제 기상 (Anti-Sleep)
        app_url = "https://stock-alarm-nwgxkui9krfqw6xddswa6n.streamlit.app/"
        try: requests.get(app_url, timeout=10)
        except: pass

        # 2. 시간 계산 (KST 기준)
        now_hour = (datetime.now().hour + 9) % 24
        
        # [테스트 모드] 수동 실행 시 즉시 결과를 보기 위해 True 설정
        # 3시, 5시, 15시가 아니더라도 'Run workflow' 클릭 시 메시지 발송
        is_test_run = True 

        # A. 기상 보고 (03시 또는 15시)
        if now_hour in [3, 15] or (is_test_run and now_hour not in [5]):
            status_msg = "🌅 새벽 기상 보고 완료" if 0 <= now_hour < 12 else "☀️ 오후 시스템 점검 완료"
            self.report.append(status_msg)
        
        # B. 주식 분석 리포트 (05시 또는 테스트 실행)
        if now_hour == 5 or is_test_run:
            self.execute_stock_analysis() 

        # 3. 통합 메시지 발송 (중복 방지: 단 1회 실행)
        if self.report:
            self.send_telegram('\n\n'.join(self.report))

    def execute_stock_analysis(self):
        tickers = ["QQQ", "SOXX"]
        for t in tickers:
            data = self.get_market_data(t)
            cur_p, ath_now = data['close'], data['ath']
            t_data = self.config.get(t, {})
            
            current_drop = (cur_p / ath_now - 1) * 100 if ath_now > 0 else 0
            msg = f"*{t}* (현재: `${cur_p:.2f}` / ATH대비: {current_drop:.1f}%)\n"
            
            # 무한매수 (Gist 수치 기반 알람)
            infi = t_data.get("Infi", {})
            infi_ref = infi.get("High_After_End", 0)
            infi_drop = (cur_p / infi_ref - 1) * 100 if infi_ref > 0 else 0
            limit = -3 if t == "QQQ" else -4
            
            if infi_drop <= limit:
                msg += f"🔴 [무매-즉시] 타겟 도달! ({infi_drop:.1f}%)\n"

            # 사이클 (매도 감시)
            for c_key in ["New", "Old"]:
                cycle = t_data.get(c_key, {})
                if cycle.get("Status") == "ACTIVE":
                    frozen_ath = cycle.get("Target_ATH", 0)
                    r1 = 1.2 if t == "QQQ" else 1.3
                    dist_r1 = (frozen_ath * r1 / cur_p - 1) * 100
                    if cur_p >= frozen_ath * r1 * 0.95:
                        msg += f"💰 [{c_key}-매도] 익절 구간 진입 ({dist_r1:+.1f}%)\n"

            self.report.append(msg)

    def send_telegram(self, message):
        token = os.environ.get('MY_TELEGRAM_TOKEN')
        chat_id = os.environ.get('MY_CHAT_ID')
        url = f"https://api.github.com/repos/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}"
        run_url_msg = f"\n\n🔗 [로그 확인]({url})"
        
        payload = {
            "chat_id": chat_id,
            "text": message + run_url_msg,
            "parse_mode": "Markdown"
        }
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)

if __name__ == "__main__":
    VisualAlarmEngine().run()
