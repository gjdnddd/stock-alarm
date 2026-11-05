import os, yfinance as yf, requests, json
from datetime import date, timedelta

def clean_env(name):
    return os.environ.get(name, "").strip().lstrip("﻿")

# ── 분할(스플릿) 감지 ─────────────────────────────────────────────────────────
SPLIT_JUMP_LOW, SPLIT_JUMP_HIGH = 0.6, 1.7   # 일간 종가 비율이 이 범위 밖이면 가격 불연속(분할 의심)
SPLIT_WINDOW = 40                            # 최근 N거래일 안에서 불연속을 찾는다
SPLIT_FIRST_LOOKBACK_DAYS = 10               # split_checked 가 없으면 이 기간 안의 분할만 '새 분할'로 본다


def round_split_ratio(r):
    """가격 비율(직전/현재)을 0.5 단위 분할 비율로 반올림. 정분할은 N(>=1), 역분할은 1/N(<1)."""
    if r >= 1:
        return max(round(r * 2) / 2, 1.0)
    inv = round((1 / r) * 2) / 2
    return 1 / inv if inv > 0 else r


def fmt_split_ratio(r):
    return f"{r:g}:1" if r >= 1 else f"1:{1 / r:g}"


def find_price_jump(closes, window=SPLIT_WINDOW):
    """최근 window 거래일 종가에서 분할로 보이는 불연속(가장 최근 1건)을 찾는다.
    Yahoo가 과거 종가를 아직 분할 조정하지 않았을 때 나타난다. 없으면 None."""
    s = closes.dropna().tail(window + 1)
    if len(s) < 2:
        return None
    ratio = s / s.shift(1)
    bad = ratio[(ratio <= SPLIT_JUMP_LOW) | (ratio >= SPLIT_JUMP_HIGH)].dropna()
    if bad.empty:
        return None
    idx = bad.index[-1]
    prev = float(s.shift(1).loc[idx])
    return {"date": idx.date().isoformat(), "ratio": round_split_ratio(prev / float(s.loc[idx]))}

# ── 매수/하드 기준 상수 (ATH 대비 하락률 %) ───────────────────────────────────
QQQ_BUY_ENTER = -15
QQQ_BUY_NEAR = -10

# 하드 2단계: near1(1단계 근접, 없으면 None) / enter1 / near2 / enter2
HARD_LEVELS = {
    "QQQ":  {"near1": -20,  "enter1": -25, "near2": -30, "enter2": -35},
    "SOXX": {"near1": None, "enter1": -30, "near2": -35, "enter2": -40},
}
HARD_RATIO_1 = "평가금 1/4"
HARD_RATIO_2 = "평가금 100%"


def hard_level_list(cfg):
    return [(cfg["enter1"], "1단계"), (cfg["enter2"], "2단계")]


def hard_status(cfg, drop):
    """(아이콘, 문구) 반환. 아이콘 ✅ 이면 대기."""
    if drop <= cfg["enter2"]:
        return "💀", f"하드 2단계 진입 ({HARD_RATIO_2})"
    if drop <= cfg["near2"]:
        return "💀", f"하드 1단계 진입 ({HARD_RATIO_1}) / 2단계 근접 (다음 {HARD_RATIO_2})"
    if drop <= cfg["enter1"]:
        return "💀", f"하드 1단계 진입 ({HARD_RATIO_1})"
    if cfg["near1"] is not None and drop <= cfg["near1"]:
        return "⚠️", f"하드 1단계 근접 (다음 {HARD_RATIO_1})"
    return "✅", "하드 대기"


class StockAlarm:
    def __init__(self):
        self.config = self.load_config()
        self.config_updated = False
        self.price_jump = {}   # ticker -> {"date","ratio"} (가격 불연속, 없으면 None)

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
            forced_jump = os.environ.get(f'TEST_{ticker}_JUMP')   # "YYYY-MM-DD:비율"
            if forced_jump:
                d, r = forced_jump.split(':')
                self.price_jump[ticker] = {"date": d, "ratio": float(r)}
            else:
                self.price_jump[ticker] = None
            return ath, close, "test"
        stock = yf.Ticker(ticker)
        df = stock.history(period="max")
        if df.empty:
            self.price_jump[ticker] = None
            return 0, 0, None
        self.price_jump[ticker] = find_price_jump(df['Close'])
        return float(df['Close'].max()), float(df['Close'].iloc[-1]), df.index[-1].date().isoformat()

    def get_splits(self, ticker):
        """yfinance가 등록한 분할 이벤트 [(날짜 ISO, 비율)]. 정분할 3:1 이면 3.0."""
        forced = os.environ.get(f'TEST_{ticker}_SPLIT')           # "YYYY-MM-DD:비율"
        if forced:
            d, r = forced.split(':')
            return [(d, float(r))]
        try:
            return [(idx.date().isoformat(), float(v))
                    for idx, v in yf.Ticker(ticker).splits.items() if v and v > 0]
        except Exception:
            return []

    def split_hold(self, ticker, t):
        """분할 보정이 필요하거나 Yahoo 과거 데이터가 아직 미조정이면 알림을 보류하고 안내 메시지를 돌려준다.
        저장된 절대가(infi_hae/cycle_low/sell_ath)는 여기서 절대 자동 수정하지 않는다 —
        텔레그램 안내 후 대시보드에서 사용자가 '분할 보정 적용'을 눌러야 반영된다."""
        checked = t.get("split_checked") or (date.today() - timedelta(days=SPLIT_FIRST_LOOKBACK_DAYS)).isoformat()
        jump = self.price_jump.get(ticker)
        if jump and jump["date"] <= (t.get("split_dismissed") or ""):
            jump = None   # 사용자가 '분할 아님'으로 처리한 불연속
        events = [(d, r) for d, r in self.get_splits(ticker) if d > checked]

        candidate = None
        if jump and jump["date"] > checked:
            candidate = {"date": jump["date"], "ratio": jump["ratio"], "source": "price_jump"}
        elif events and not jump:   # 이벤트 등록 + 과거 종가 조정 완료 → 정확한 비율
            d, r = events[-1]
            candidate = {"date": d, "ratio": r, "source": "yfinance"}

        pending = t.get("pending_split")
        fresh = False
        if candidate and candidate != pending:
            t["pending_split"] = pending = candidate
            self.config_updated = True
            fresh = True
        if pending:
            return self.split_pending_message(ticker, pending, fresh)
        if jump:   # 보정은 확정됐지만 Yahoo 과거 데이터가 아직 분할 미반영 → ATH 신뢰 불가
            return f"⏳ *{ticker}* 분할 보정은 완료됐지만 Yahoo 과거 데이터가 아직 조정되지 않아 알림을 보류합니다 (조정되면 자동 재개)."
        return None

    def split_pending_message(self, ticker, pending, fresh):
        ratio = fmt_split_ratio(pending["ratio"])
        if pending.get("source") == "yfinance":
            why = f"분할 감지: {ratio} ({pending['date']})"
        else:
            why = f"가격 불연속 감지: {pending['date']} (약 {ratio} 분할 추정, Yahoo 과거 데이터 미조정 가능)"
        return (f"{'⚠️' if fresh else '⏳'} *{ticker}* {why}\n"
                f"  저장된 무매 HAE·사이클 저점·매도 ATH를 {pending['ratio']:g}로 나눠 보정해야 합니다.\n"
                f"  대시보드의 '분할 보정 적용' 버튼으로 확정해주세요. 확정 전까지 {ticker} 알림은 보류됩니다.")

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

        # 분할 의심/보정 대기 중이면 저장값(HAE·저점)을 건드리거나 알림을 내기 전에 보류
        hold = self.split_hold(ticker, t)
        if hold:
            return hold

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
            self.qqq_buy_alerts(ath, drop_pct, alerts)
            if gain_pct is not None:
                self.qqq_sell_alerts(ath, cur_p, drop_pct, gain_pct, t, alerts, close_date)
        else:
            _, soxl_price, _ = self.get_price("SOXL")
            self.soxx_buy_alerts(ath, cur_p, soxl_price, drop_pct, alerts)
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
            alerts.append(f"🔴 [{ticker}] 무매 즉시매수! (현재 {infi_drop:.1f}% / 기준 {limit:.0f}%(${infi_hae * (1 + limit / 100):.2f}))")
        elif infi_drop <= alert_limit:
            alerts.append(f"🟡 [{ticker}] 무매 근접! (현재 {infi_drop:.1f}% / 기준 {alert_limit:.0f}%(${infi_hae * (1 + alert_limit / 100):.2f}))")

    # ── QQQ 매수 ───────────────────────────────────────────────────────────────

    def qqq_buy_alerts(self, ath, drop_pct, alerts):
        buy_abs = ath * (1 + QQQ_BUY_ENTER / 100)
        if drop_pct <= QQQ_BUY_ENTER:
            alerts.append(f"🚨 [QQQ→TQQQ] 매수 타점 도달 (현재 {drop_pct:+.1f}% / 기준 {QQQ_BUY_ENTER}%(${buy_abs:.2f}))")
        elif drop_pct <= QQQ_BUY_NEAR:
            alerts.append(f"⚠️ [QQQ] 매수 타점 근접 (현재 {drop_pct:+.1f}% / 기준 {QQQ_BUY_ENTER}%(${buy_abs:.2f}))")

        cfg = HARD_LEVELS["QQQ"]
        icon, text = hard_status(cfg, drop_pct)
        if icon != "✅":
            detail = " / ".join(f"{lbl} {thr}%(${ath * (1 + thr / 100):.2f})" for thr, lbl in hard_level_list(cfg))
            alerts.append(f"{icon} [QQQ] {text} (현재 {drop_pct:+.1f}% / 기준 {detail})")

    # ── SOXX 매수 ──────────────────────────────────────────────────────────────

    def soxx_buy_alerts(self, ath, cur_p, soxl_price, drop_pct, alerts):
        def fmt_level(label, level):
            abs_price = ath * (1 + level / 100)
            soxl_part = ""
            if soxl_price > 0 and cur_p > 0:
                move = abs_price / cur_p - 1
                soxl_est = soxl_price * (1 + 2.9 * move)
                soxl_part = f"(SOXL ${soxl_est:.2f})" if soxl_est > 0 else ""
            return f"{label} {level:.0f}% ${abs_price:.2f}{soxl_part}"

        buy_levels = [(-20, "1차"), (-22, "2차"), (-25, "3차")]
        buy_detail = " / ".join(fmt_level(lbl, thr) for thr, lbl in buy_levels)
        reached = [lbl for thr, lbl in buy_levels if drop_pct <= thr]
        if reached:
            alerts.append(f"🚨 [SOXX→SOXL] 매수 타점 도달: {'+'.join(reached)} (현재 {drop_pct:+.1f}%) | {buy_detail}")
        elif drop_pct <= -15:
            alerts.append(f"⚠️ [SOXX] 매수 타점 근접 (현재 {drop_pct:+.1f}%) | {buy_detail}")
        else:
            alerts.append(f"✅ [SOXX] 매수 타점 대기 (현재 {drop_pct:+.1f}%) | {buy_detail}")

        cfg = HARD_LEVELS["SOXX"]
        hard_detail = " / ".join(fmt_level(lbl, thr) for thr, lbl in hard_level_list(cfg))
        icon, text = hard_status(cfg, drop_pct)
        alerts.append(f"{icon} [SOXX] {text} (현재 {drop_pct:+.1f}%) | {hard_detail}")

    # ── QQQ 매도 ───────────────────────────────────────────────────────────────

    def qqq_sell_alerts(self, ath, cur_p, drop_pct, gain_pct, t, alerts, close_date):
        UNLOCK = 90
        unlocked = t.get("sell_unlocked", False)
        cycle_low = cur_p / (1 + gain_pct / 100)

        if not unlocked:
            if gain_pct >= UNLOCK:
                t["sell_unlocked"] = True
                self.config_updated = True
                alerts.append(f"✅ [QQQ] 매도 감시 시작 (저점 대비 {gain_pct:+.1f}% / 기준 +{UNLOCK}%(${cycle_low * (1 + UNLOCK / 100):.2f}))")
                unlocked = True
            elif gain_pct >= UNLOCK - 5:
                alerts.append(f"🔔 [QQQ] 매도 조건 근접 (저점 대비 {gain_pct:+.1f}% / 기준 +{UNLOCK}%(${cycle_low * (1 + UNLOCK / 100):.2f}))")

        if not unlocked:
            return

        done_1st = t.get("sell_1st_done", False)
        if not done_1st:
            if drop_pct <= -5:
                t["sell_1st_done"] = True
                self.config_updated = True
                alerts.append(f"💰 [QQQ→TQQQ] 1차 매도! ATH -5%(${ath * 0.95:.2f}) (현재 {drop_pct:+.1f}%) → 50% 매도")
            return

        if t.get("sell_2nd_done", False):
            return

        if drop_pct <= -10:
            t["sell_2nd_done"] = True
            self.config_updated = True
            alerts.append(f"💰 [QQQ→TQQQ] 2차 매도! ATH -10%(${ath * 0.90:.2f}) (현재 {drop_pct:+.1f}%) → 잔여 전량 매도")

    # ── SOXX 매도 ──────────────────────────────────────────────────────────────

    def soxx_sell_alerts(self, ath, cur_p, drop_pct, gain_pct, t, alerts, close_date):
        UNLOCK = 80
        unlocked = t.get("sell_unlocked", False)
        cycle_low = cur_p / (1 + gain_pct / 100)

        if not unlocked:
            if gain_pct >= UNLOCK:
                t["sell_unlocked"] = True
                self.config_updated = True
                alerts.append(f"✅ [SOXX] 매도 감시 시작 (저점 대비 {gain_pct:+.1f}% / 기준 +{UNLOCK}%(${cycle_low * (1 + UNLOCK / 100):.2f}))")
                unlocked = True
            elif gain_pct >= UNLOCK - 5:
                alerts.append(f"🔔 [SOXX] 매도 조건 근접 (저점 대비 {gain_pct:+.1f}% / 기준 +{UNLOCK}%(${cycle_low * (1 + UNLOCK / 100):.2f}))")

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
            alerts.append(f"💰 [SOXX→SOXL] 매도! ATH -10%(${ath * 0.90:.2f}) 5거래일 연속 → 전량 매도")
        elif consec >= 3:
            alerts.append(f"⚠️ [SOXX] 매도 카운트 {consec}/5 ({5 - consec}거래일 남음, ATH 대비 {drop_pct:+.1f}% / 기준 -10%(${ath * 0.90:.2f}))")
        elif consec > 0:
            alerts.append(f"[SOXX] ATH -10%(${ath * 0.90:.2f}) {consec}거래일 연속 (ATH 대비 {drop_pct:+.1f}%)")

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
