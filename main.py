import os, yfinance as yf, requests, json, time
from datetime import datetime

class VisualAlarmEngine:
    def __init__(self):
        self.config = self.get_gist_state()
        self.report = []

    def get_market_data(self, ticker):
        stock = yf.Ticker(ticker)
        df = stock.history(period="max")
        return {"ath": df['Close'].max(), "close": df['Close'].iloc[-1]}

    def run(self):
        tickers = ["QQQ", "SOXX"]
        for t in tickers:
            data = self.get_market_data(t)
            cur_p, ath_now = data['close'], data['ath']
            t_data = self.config.get(t, {})
            msg = f"*{t}* (현재: `${cur_p:.2f}`)\n"

            # 1. 무한매수 (종료 후 최고가 대비)
            infi = t_data.get("Infi", {})
            if cur_p > infi.get("High_After_End", 0):
                infi["High_After_End"] = cur_p
            
            infi_ref = infi.get("High_After_End", 0)
            infi_drop = (cur_p / infi_ref - 1) * 100 if infi_ref > 0 else 0
            limit = -3 if t == "QQQ" else -4
            
            if infi_drop <= limit:
                msg += f"🚨 [무매-즉시] 타겟 도달! ({infi_drop:.1f}%)\n"
            elif infi_drop <= limit + 1.5: # 1.5% 근접 시 예보
                msg += f"⚠️ [무매-준비] 타겟 근접! (현재 {infi_drop:.1f}%)\n"

            # 2. 사이클 전략 (신/구)
            for c_key in ["New", "Old"]:
                cycle = t_data.get(c_key, {})
                status = cycle.get("Status", "READY")
                
                if status == "ACTIVE": # 매도 감시 (박제 ATH 기준)
                    frozen_ath = cycle.get("Target_ATH", 0)
                    r1, r2 = (1.2, 1.24) if t == "QQQ" else (1.3, 1.34)
                    if cur_p >= frozen_ath * r2: msg += f"💰 [{c_key}-매도] 2차 익절 도달!\n"
                    elif cur_p >= frozen_ath * r1: msg += f"💰 [{c_key}-매도] 1차 익절 도달!\n"
                    elif cur_p >= frozen_ath * r1 * 0.97: msg += f"📈 [{c_key}-대기] 익절가 3% 이내 근접!\n"
                
                else: # 진입 감시 (현재 ATH 기준)
                    drop = (cur_p / ath_now - 1) * 100
                    targets = {-19:"T사이클", -20:"T퇴연", -21:"T사이클", -30:"T하드"} if t=="QQQ" else {-20:"S사이클", -22:"S퇴연", -25:"S사이클", -35:"S하드", -40:"S하드"}
                    for pct, name in targets.items():
                        if drop <= pct:
                            msg += f"🚨 [{c_key}-매수] {name} 도달! ({drop:.1f}%)\n"
                            break
                        elif drop <= pct + 2.0: # 2% 이내 근접 시
                            msg += f"⚠️ [{c_key}-준비] {name} 근접! (남은거리: {drop-pct:.1f}%)\n"
                            break
            self.report.append(msg)
        
        self.save_and_send()
