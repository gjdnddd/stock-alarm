import os, yfinance as yf, requests, json
from datetime import datetime

def clean_env(name):
    value = os.environ.get(name, "")
    return value.strip().lstrip("\ufeff")

class VisualAlarmEngine:
    def __init__(self):
        self.config = self.get_gist_state()
        self.report = []
        self.config_updated = False

    def get_gist_state(self):
        test_config_path = os.environ.get('TEST_CONFIG_PATH')
        if test_config_path:
            with open(test_config_path, encoding='utf-8') as f:
                return json.load(f)
        token = clean_env('MY_GITHUB_TOKEN')
        gist_id = clean_env('MY_GIST_ID')
        url = f"https://api.github.com/gists/{gist_id}"
        headers = {"Authorization": f"token {token}"}
        res = requests.get(url, headers=headers)
        return json.loads(res.json()['files']['stock_data.json']['content'])

    def save_gist_state(self):
        if os.environ.get('TEST_SKIP_GIST_SAVE', '').lower() in ('1', 'true', 'yes'):
            return
        token = clean_env('MY_GITHUB_TOKEN')
        gist_id = clean_env('MY_GIST_ID')
        url = f"https://api.github.com/gists/{gist_id}"
        headers = {"Authorization": f"token {token}"}
        payload = {"files": {"stock_data.json": {"content": json.dumps(self.config, indent=2)}}}
        requests.patch(url, headers=headers, json=payload)

    def get_market_data(self, ticker):
        forced_price = os.environ.get(f'TEST_{ticker}_PRICE')
        forced_ath = os.environ.get(f'TEST_{ticker}_ATH')
        if forced_price:
            close = float(forced_price)
            ath = float(forced_ath) if forced_ath else close
            return {"ath": ath, "close": close}
        stock = yf.Ticker(ticker)
        df = stock.history(period="max")
        if df.empty: return {"ath": 0, "close": 0}
        return {"ath": df['Close'].max(), "close": df['Close'].iloc[-1]}

    def run(self):
        self.execute_stock_analysis()
        if self.config_updated:
            self.save_gist_state()
        self.save_and_send()

    def execute_stock_analysis(self):
        tickers = ["QQQ", "SOXX"]
        for t in tickers:
            data = self.get_market_data(t)
            cur_p, ath_now = data['close'], data['ath']
            t_data = self.config.get(t, {})

            current_drop = (cur_p / ath_now - 1) * 100 if ath_now > 0 else 0
            msg = f"*{t}* (현재: `${cur_p:.2f}` / ATH대비: {current_drop:.1f}%)\n"

            # 무한매수: High_After_End 자동 업데이트 + 알람
            infi = t_data.get("Infi", {})
            if cur_p > infi.get("High_After_End", 0):
                infi["High_After_End"] = cur_p
                t_data["Infi"] = infi
                self.config[t] = t_data
                self.config_updated = True

            infi_ref = infi.get("High_After_End", 0)
            infi_drop = (cur_p / infi_ref - 1) * 100 if infi_ref > 0 else 0
            limit = -3 if t == "QQQ" else -4
            alert_limit = limit + 1.0
            if infi_drop <= limit:
                msg += f"🔴 [무매-즉시] 타겟 도달! (현재 {infi_drop:.1f}% / 목표 {limit:.1f}% / 알람 {alert_limit:.1f}%)\n"
            elif infi_drop <= alert_limit:
                msg += f"🟡 [무매-준비] 근접! (현재 {infi_drop:.1f}% / 목표 {limit:.1f}% / 알람 {alert_limit:.1f}%)\n"

            # 사이클 전략
            for c_key in ["New", "Old"]:
                cycle = t_data.get(c_key, {})
                status = cycle.get("Status", "READY")

                if status == "PAUSED":
                    continue

                if status == "ACTIVE":  # 매도 감시
                    frozen_ath = cycle.get("Target_ATH", 0)
                    if frozen_ath <= 0:
                        continue
                    r1 = 1.2 if t == "QQQ" else 1.3
                    target_gain = (r1 - 1) * 100
                    alert_gain = ((r1 * 0.95) - 1) * 100
                    current_gain = (cur_p / frozen_ath - 1) * 100
                    dist_r1 = (frozen_ath * r1 / cur_p - 1) * 100
                    if cur_p >= frozen_ath * r1 * 0.95:
                        msg += f"💰 [{c_key}-매도] 목표가까지 {dist_r1:+.1f}% 남음 (현재 {current_gain:+.1f}% / 목표 +{target_gain:.1f}% / 알람 +{alert_gain:.1f}%)\n"

                else:  # READY — 진입 감시
                    drop = (cur_p / ath_now - 1) * 100
                    targets = (
                        {-19: "T사이클", -20: "T퇴연", -21: "T사이클", -30: "T하드"}
                        if t == "QQQ" else
                        {-20: "S사이클", -22: "S퇴연", -25: "S사이클", -35: "S하드", -40: "S하드"}
                    )
                    for pct, name in targets.items():
                        alert_drop = pct + 5.0
                        if drop <= pct:
                            msg += f"🚨 [{c_key}-매수] {name} 도달! (현재 {drop:.1f}% / 목표 {pct:.1f}% / 알람 {alert_drop:.1f}%)\n"
                            break
                        elif drop <= alert_drop:
                            msg += f"⚠️ [{c_key}-준비] {name} 근접! (현재 {drop:.1f}% / 목표 {pct:.1f}% / 알람 {alert_drop:.1f}%)\n"
                            break

            self.report.append(msg)

    def save_and_send(self):
        if not self.report: return
        token = clean_env('MY_TELEGRAM_TOKEN')
        chat_id = clean_env('MY_CHAT_ID')
        message = '\n\n'.join(self.report)
        if os.environ.get('TEST_MODE', '').lower() in ('1', 'true', 'yes'):
            message = "[TEST MODE]\n" + message
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
        if os.environ.get('TEST_MODE', '').lower() in ('1', 'true', 'yes'):
            print(f"Telegram status: {res.status_code}")
            try:
                print(f"Telegram body: {res.json()}")
            except Exception:
                print(f"Telegram body: {res.text}")
        res.raise_for_status()

if __name__ == "__main__":
    VisualAlarmEngine().run()
