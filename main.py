import os, yfinance as yf, requests, json

def clean_env(name):
    return os.environ.get(name, "").strip().lstrip("﻿")


class StockAlarm:
    def __init__(self):
        self.config = self.load_config()
        self.config_updated = False

    def load_config(self):
        test_path = os.environ.get('TEST_CONFIG_PATH')
        if test_path:
            with open(test_path, encoding='utf-8') as f:
                return json.load(f)
        token, gist_id = clean_env('MY_GITHUB_TOKEN'), clean_env('MY_GIST_ID')
        res = requests.get(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {token}"}
        )
        return json.loads(res.json()['files']['stock_data.json']['content'])

    def save_config(self):
        if os.environ.get('TEST_SKIP_GIST_SAVE', '').lower() in ('1', 'true', 'yes'):
            return
        token, gist_id = clean_env('MY_GITHUB_TOKEN'), clean_env('MY_GIST_ID')
        payload = {"files": {"stock_data.json": {"content": json.dumps(self.config, indent=2)}}}
        requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {token}"},
            json=payload
        )

    def get_price(self, ticker):
        forced_price = os.environ.get(f'TEST_{ticker}_PRICE')
        forced_ath = os.environ.get(f'TEST_{ticker}_ATH')
        if forced_price:
            close = float(forced_price)
            ath = float(forced_ath) if forced_ath else close
            return ath, close, "test"
        stock = yf.Ticker(ticker)
        df = stock.history(period="max")
        if df.empty:
            return 0, 0, None
        return float(df['Close'].max()), float(df['Close'].iloc[-1]), df.index[-1].date().isoformat()

    def run(self):
        messages = []
        for ticker, etf in [("QQQ", "TQQQ"), ("SOXX", "SOXL")]:
            msg = self.process(ticker, etf)
            if msg:
                messages.append(msg)
        if self.config_updated:
            self.save_config()
        if messages:
            self.send_telegram("\n\n".join(messages))

    def process(self, ticker, etf):
        ath, cur_p, close_date = self.get_price(ticker)
        if ath <= 0:
            return None

        drop_pct = (cur_p / ath - 1) * 100
        t = self.config.setdefault(ticker, {})
        cycle_low = t.get("cycle_low")

        # 무매 HAE 자동 갱신
        infi_hae = t.get("infi_hae", 0)
        if cur_p > infi_hae:
            t["infi_hae"] = cur_p
            infi_hae = cur_p
            self.config_updated = True

        lines = [f"*{ticker}* (${cur_p:.2f} | ATH ${ath:.2f} | {drop_pct:+.1f}%)"]

        if infi_hae > 0:
            infi_drop = (cur_p / infi_hae - 1) * 100
            lines.append(f"  무매 ${infi_hae:.2f} ({infi_drop:+.1f}%)")

        if cycle_low:
            if cur_p < cycle_low:
                t["cycle_low"] = cur_p
                cycle_low = cur_p
                self.config_updated = True
            gain_pct = (cur_p / cycle_low - 1) * 100
            lines.append(f"  저점 ${cycle_low:.2f} → {gain_pct:+.1f}%")
        else:
            gain_pct = None

        alerts = []
        self.infi_alerts(ticker, cur_p, infi_hae, alerts)
        if ticker == "QQQ":
            self.qqq_buy_alerts(drop_pct, alerts)
            if gain_pct is not None:
                self.qqq_sell_alerts(ath, cur_p, drop_pct, gain_pct, t, alerts, close_date)
        else:
            self.soxx_buy_alerts(drop_pct, alerts)
            if gain_pct is not None:
                self.soxx_sell_alerts(ath, cur_p, drop_pct, gain_pct, t, alerts, close_date)

        return "\n".join(lines + alerts)

    # ── 무한매수 ───────────────────────────────────────────────────────────────

    def infi_alerts(self, ticker, cur_p, infi_hae, alerts):
        if infi_hae <= 0:
            return
        infi_drop = (cur_p / infi_hae - 1) * 100
        limit = -3.0 if ticker == "QQQ" else -4.0
        alert_limit = limit + 1.0
        if infi_drop <= limit:
            alerts.append(f"🔴 [{ticker}] 무매 즉시매수! (현재 {infi_drop:.1f}% / 기준 {limit:.0f}%)")
        elif infi_drop <= alert_limit:
            alerts.append(f"🟡 [{ticker}] 무매 근접! (현재 {infi_drop:.1f}% / 기준 {limit:.0f}%)")

    # ── QQQ 매수 ───────────────────────────────────────────────────────────────

    def qqq_buy_alerts(self, drop_pct, alerts):
        buy_levels = [(-19, "1차 30%"), (-20, "2차 40%"), (-21, "3차 30%")]
        reached = [(thr, lbl) for thr, lbl in buy_levels if drop_pct <= thr]
        if reached:
            labels = " + ".join(lbl for _, lbl in reached)
            alerts.append(f"🚨 [QQQ→TQQQ] 매수 타점 도달: {labels} (현재 {drop_pct:+.1f}%)")
        elif drop_pct <= -14:
            alerts.append(f"⚠️ [QQQ] 매수 타점 근접 (현재 {drop_pct:+.1f}% / 1차 기준 -19%)")

        if drop_pct <= -30:
            alerts.append(f"💀 [QQQ] 하드 사이클 진입 조건 도달 (현재 {drop_pct:+.1f}%)")
        elif drop_pct <= -25:
            alerts.append(f"⚠️ [QQQ] 하드 사이클 근접 (현재 {drop_pct:+.1f}% / 기준 -30%)")

    # ── SOXX 매수 ──────────────────────────────────────────────────────────────

    def soxx_buy_alerts(self, drop_pct, alerts):
        buy_levels = [(-20, "1차 10%"), (-22, "2차 10%"), (-25, "3차 80%")]
        reached = [(thr, lbl) for thr, lbl in buy_levels if drop_pct <= thr]
        if reached:
            labels = " + ".join(lbl for _, lbl in reached)
            alerts.append(f"🚨 [SOXX→SOXL] 매수 타점 도달: {labels} (현재 {drop_pct:+.1f}%)")
        elif drop_pct <= -15:
            alerts.append(f"⚠️ [SOXX] 매수 타점 근접 (현재 {drop_pct:+.1f}% / 1차 기준 -20%)")

        if drop_pct <= -40:
            alerts.append(f"💀 [SOXX] 하드 2단계 진입 조건 도달 (현재 {drop_pct:+.1f}%)")
        elif drop_pct <= -35:
            alerts.append(f"💀 [SOXX] 하드 1단계 진입 / 하드 2단계 근접 (현재 {drop_pct:+.1f}%)")
        elif drop_pct <= -30:
            alerts.append(f"⚠️ [SOXX] 하드 1단계 근접 (현재 {drop_pct:+.1f}% / 기준 -35%)")

    # ── QQQ 매도 ───────────────────────────────────────────────────────────────

    def qqq_sell_alerts(self, ath, cur_p, drop_pct, gain_pct, t, alerts, close_date):
        UNLOCK = 120
        unlocked = t.get("sell_unlocked", False)

        if not unlocked:
            if gain_pct >= UNLOCK:
                t["sell_unlocked"] = True
                self.config_updated = True
                alerts.append(f"✅ [QQQ] 매도 감시 시작 (저점 대비 {gain_pct:+.1f}%)")
                unlocked = True
            elif gain_pct >= UNLOCK - 5:
                alerts.append(f"🔔 [QQQ] 매도 조건 근접 (저점 대비 {gain_pct:+.1f}% / 기준 +{UNLOCK}%)")

        if not unlocked:
            return

        done_1st = t.get("sell_1st_done", False)
        if not done_1st:
            if drop_pct <= -5:
                t["sell_1st_done"] = True
                t["sell_2nd_ath"] = ath
                t["sell_2nd_count"] = 0
                t["sell_2nd_last_date"] = None
                self.config_updated = True
                alerts.append(f"💰 [QQQ→TQQQ] 1차 매도! ATH -5% (현재 {drop_pct:+.1f}%) → 50% 매도")
            return

        # 2차 매도: 동일 ATH 상태에서 -10% 2회
        ref_ath = t.get("sell_2nd_ath", ath)
        count = t.get("sell_2nd_count", 0)
        last_date = t.get("sell_2nd_last_date")

        if count >= 2:
            alerts.append(f"💰 [QQQ→TQQQ] 2차 매도 조건 달성 → 잔여 전량 매도")
            return

        if ath > ref_ath:
            ref_ath = ath
            count = 0
            last_date = None
            t["sell_2nd_ath"] = ref_ath
            t["sell_2nd_count"] = 0
            t["sell_2nd_last_date"] = None
            self.config_updated = True

        drop_from_ref = (cur_p / ref_ath - 1) * 100
        if drop_from_ref <= -10 and close_date != last_date:
            count += 1
            t["sell_2nd_count"] = count
            t["sell_2nd_last_date"] = close_date
            self.config_updated = True

        if count >= 2:
            alerts.append(f"💰 [QQQ→TQQQ] 2차 매도! 동일 ATH -10% 2회 → 잔여 전량 매도")
        elif drop_from_ref <= -10:
            alerts.append(f"⚠️ [QQQ] 2차 매도 카운트 {count}/2 (ATH ${ref_ath:.2f} 대비 {drop_from_ref:+.1f}%)")

    # ── SOXX 매도 ──────────────────────────────────────────────────────────────

    def soxx_sell_alerts(self, ath, cur_p, drop_pct, gain_pct, t, alerts, close_date):
        UNLOCK = 80
        unlocked = t.get("sell_unlocked", False)

        if not unlocked:
            if gain_pct >= UNLOCK:
                t["sell_unlocked"] = True
                self.config_updated = True
                alerts.append(f"✅ [SOXX] 매도 감시 시작 (저점 대비 {gain_pct:+.1f}%)")
                unlocked = True
            elif gain_pct >= UNLOCK - 5:
                alerts.append(f"🔔 [SOXX] 매도 조건 근접 (저점 대비 {gain_pct:+.1f}% / 기준 +{UNLOCK}%)")

        if not unlocked:
            return

        consec = t.get("soxx_consecutive", 0)
        last_date = t.get("soxx_last_date")

        if consec >= 5:
            alerts.append(f"💰 [SOXX→SOXL] 매도 조건 달성 → 전량 매도")
            return

        if close_date != last_date:
            consec = consec + 1 if drop_pct <= -10 else 0
            t["soxx_consecutive"] = consec
            t["soxx_last_date"] = close_date
            self.config_updated = True

        if consec >= 5:
            alerts.append(f"💰 [SOXX→SOXL] 매도! ATH -10% 5거래일 연속 → 전량 매도")
        elif consec >= 3:
            alerts.append(f"⚠️ [SOXX] 매도 카운트 {consec}/5 ({5 - consec}거래일 남음, ATH 대비 {drop_pct:+.1f}%)")
        elif consec > 0:
            alerts.append(f"[SOXX] ATH -10% {consec}거래일 연속 (ATH 대비 {drop_pct:+.1f}%)")

    # ── Telegram ───────────────────────────────────────────────────────────────

    def send_telegram(self, text):
        token, chat_id = clean_env('MY_TELEGRAM_TOKEN'), clean_env('MY_CHAT_ID')
        if os.environ.get('TEST_MODE', '').lower() in ('1', 'true', 'yes'):
            text = "[TEST MODE]\n" + text
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
        if os.environ.get('TEST_MODE', '').lower() in ('1', 'true', 'yes'):
            print(f"Telegram status: {res.status_code}")
            try:
                print(f"Telegram body: {res.json()}")
            except Exception:
                print(f"Telegram body: {res.text}")
        res.raise_for_status()


if __name__ == "__main__":
    StockAlarm().run()
