import os, yfinance as yf, requests, json, time
from datetime import datetime

class VisualAlarmEngine:
    def __init__(self):
        self.config = self.get_gist_state()
        self.report = []
        # TEST_MODE: True일 경우 매 실행 시 현황 브리핑을 무조건 발송합니다.
        self.TEST_MODE = True 

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
            
            # 기본 헤더 생성
            current_drop = (cur_p / ath_now - 1) * 100
            msg = f"*{t}* (현재: `${cur_p:.2f}` / ATH대비: {current_drop:.1f}%)\n"
            has_event = False

            # 1. 무한매수 로직
            infi = t_data.get("Infi", {})
            if cur_p > infi.get("High_After_End", 0):
                infi["High_After_End"] = cur_p
            
            infi_ref = infi.get("High_After_End", 0)
            infi_drop = (cur_p / infi_ref - 1) * 100 if infi_ref > 0 else 0
            limit = -3 if t == "QQQ" else -4
            
            if infi_drop <= limit:
                msg += f"🔴 [무매-즉시] 타겟 도달! ({infi_drop:.1f}%)\n"
                has_event = True
            elif infi_drop <= limit + 1.0:
                msg += f"🟡 [무매-준비] 타겟 근접! (현재 {infi_drop:.1f}%)\n"
                has_event = True

            # 2. 사이클 전략 로직
            for c_key in ["New", "Old"]:
                cycle = t_data.get(c_key, {})
                status = cycle.get("Status", "READY")
                
                if status == "ACTIVE":
                    frozen_ath = cycle.get("Target_ATH", 0)
                    r1, r2 = (1.2, 1.24) if t == "QQQ" else (1.3, 1.34)
                    dist_r1 = (frozen_ath * r1 / cur_p - 1) * 100
                    
                    if cur_p >= frozen_ath * r2: 
                        msg += f"🔥 [{c_key}-매도] 2차 익절 도달!\n"
                        has_event = True
                    elif cur_p >= frozen_ath * r1: 
                        msg += f"💰 [{c_key}-매도] 1차 익절 도달!\n"
                        has_event = True
                    elif cur_p >= frozen_ath * r1 * 0.95: 
                        msg += f"🟢 [{c_key}-대기] 목표가까지 {dist_r1:+.1f}% 남음\n"
                        has_event = True
                
                else:
                    drop = (cur_p / ath_now - 1) * 100
                    targets = {-19:"T사이클", -20:"T퇴연", -21:"T사이클", -30:"T하드"} if t=="QQQ" else {-20:"S사이클", -22:"S퇴연", -25:"S사이클", -35:"S하드", -40:"S하드"}
                    for pct, name in targets.items():
                        if drop <= pct:
                            msg += f"🔴 [{c_key}-매수] {name} 도달! ({drop:.1f}%)\n"
                            has_event = True
                            break
                        elif drop <= pct + 5.0:
                            msg += f"🟡 [{c_key}-준비] {name} 근접! (남은거리: {drop-pct:.1f}%)\n"
                            has_event = True
                            break

            # 3. 안티-슬립 브리핑 (이벤트가 없어도 TEST_MODE면 무조건 추가)
            if self.TEST_MODE:
                if not has_event:
                    msg += "✅ 시스템 정상 (특이사항 없음)\n"
                self.report.append(msg)
            elif has_event:
                self.report.append(msg)
        
        self.save_and_send()
