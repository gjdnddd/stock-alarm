import streamlit as st
import requests
import json
import yfinance as yf
import pandas as pd
import os
from dotenv import load_dotenv

# 0. .env 파일 로드
load_dotenv()
# 우선 순위: 1. Streamlit Secrets(Cloud), 2. Environment Variable(.env)
env_token = st.secrets.get("MY_GITHUB_TOKEN", os.getenv("MY_GITHUB_TOKEN", ""))
env_gist_id = st.secrets.get("MY_GIST_ID", os.getenv("MY_GIST_ID", ""))

# 1. 페이지 설정
st.set_page_config(page_title="미국주식 통합 전략 대시보드", layout="wide")
st.title("📈 미국주식 통합 전략 비주얼 현황판")

# --- 사이드바 설정 (보안 강화 버전) ---
st.sidebar.header("🔐 인증 설정")

# env나 secrets에서 먼저 값을 가져옴
env_token = st.secrets.get("MY_GITHUB_TOKEN", os.getenv("MY_GITHUB_TOKEN", ""))
env_gist_id = st.secrets.get("MY_GIST_ID", os.getenv("MY_GIST_ID", ""))

# 값이 없을 때만 입력창을 보여줌 (값이 있으면 자동 할당 후 숨김)
if not env_token:
    token = st.sidebar.text_input("GitHub Token", type="password")
else:
    token = env_token
    st.sidebar.success("GitHub Token 로드 완료")

if not env_gist_id:
    gist_id = st.sidebar.text_input("Gist ID")
else:
    gist_id = env_gist_id
    st.sidebar.success("Gist ID 로드 완료")

# 만약 관리자 모드에서 수정하고 싶을 때를 위해 숨겨진 체크박스 하나만 배치
if st.sidebar.checkbox("수동 입력 모드"):
    token = st.sidebar.text_input("수동 Token", value=token, type="password", key="manual_token")
    gist_id = st.sidebar.text_input("수동 Gist ID", value=gist_id, key="manual_gist")

# --- 유틸리티 함수 ---
def get_gist_data(token, gist_id):
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {token}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            files = res.json().get('files', {})
            content = files.get('stock_data.json', {}).get('content', '{}')
            return json.loads(content)
    except Exception as e:
        st.error(f"Gist 읽기 실패: {e}")
    return None

def update_gist_data(token, gist_id, data):
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {token}"}
    payload = {"files": {"stock_data.json": {"content": json.dumps(data, indent=2)}}}
    try:
        res = requests.patch(url, headers=headers, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        st.error(f"Gist 업데이트 실패: {e}")
        return False

# --- 메인 대시보드 로직 ---
if token and gist_id:
    data = get_gist_data(token, gist_id)
    
    if data:
        for ticker in ["QQQ", "SOXX"]:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="max")
                curr_p = hist['Close'].iloc[-1]
                ath_now = hist['Close'].max()
                drop_now = (curr_p / ath_now - 1) * 100
            except:
                st.error(f"{ticker} 데이터를 가져오는데 실패했습니다.")
                continue

            with st.expander(f"🔍 {ticker} 실시간 전략 모니터링 (ATH: ${ath_now:.2f})", expanded=True):
                m1, m2, m3 = st.columns(3)
                m1.metric("현재가", f"${curr_p:.2f}")
                m2.metric("ATH 대비 하락률", f"{drop_now:.2f}%")
                
                # 1. 무한매수 현황 계산
                infi = data[ticker].get("Infi", {})
                infi_ref = infi.get("High_After_End", 0.0)
                infi_drop = (curr_p / infi_ref - 1) * 100 if infi_ref > 0 else 0
                infi_limit = -3 if ticker == "QQQ" else -4
                
                status_rows = []
                
                # 무매 상태
                infi_status = "✅ 대기"
                if infi_drop <= infi_limit: infi_status = "🚨 즉시매수"
                elif infi_drop <= infi_limit + 1.5: infi_status = "🟡 진입준비"
                status_rows.append({"구분": "무한매수", "기준점": f"종료고가(${infi_ref:.1f})", "현재상태": f"{infi_drop:.1f}%", "액션": infi_status})

                # 신/구 사이클 상태
                for c_key in ["New", "Old"]:
                    cycle = data[ticker].get(c_key, {})
                    c_status = cycle.get("Status", "READY")
                    
                    if c_status == "ACTIVE":
                        frozen_ath = cycle.get("Target_ATH", 0.0)
                        r1 = 1.2 if ticker == "QQQ" else 1.3
                        dist_to_sell = (curr_p / (frozen_ath * r1) - 1) * 100
                        action = "🟢 익절대기" if dist_to_sell < -3 else "💰 매도준비"
                        status_rows.append({"구분": f"{c_key}사이클", "기준점": f"박제ATH(${frozen_ath:.1f})", "현재상태": f"익절까지 {dist_to_sell:.1f}%", "액션": action})
                    else:
                        action = "⚪ 관망"
                        target_pct = -19 if ticker == "QQQ" else -20
                        if drop_now <= target_pct: action = "🚨 즉시매수"
                        elif drop_now <= target_pct + 2.0: action = "🟡 진입준비"
                        status_rows.append({"구분": f"{c_key}사이클", "기준점": "현재 ATH", "현재상태": f"{drop_now:.1f}%", "액션": action})

                st.table(pd.DataFrame(status_rows))

                # --- 3. 설정 변경 섹션 ---
                st.markdown("#### ⚙️ 세부 설정 변경")
                e_col1, e_col2, e_col3 = st.columns(3)
                
                with e_col1:
                    new_infi_high = st.number_input(f"{ticker} 무매 종료 최고가", value=float(infi_ref), key=f"{ticker}_infi_input")
                    data[ticker]["Infi"]["High_After_End"] = new_infi_high
                
                with e_col2:
                    st.write("**[New 사이클]**")
                    new_status = st.selectbox(f"{ticker} New 상태", ["READY", "ACTIVE", "PAUSED"], 
                                              index=["READY", "ACTIVE", "PAUSED"].index(data[ticker]["New"]["Status"]), key=f"{ticker}_new_st")
                    new_ath = st.number_input(f"{ticker} New 박제 ATH", value=float(data[ticker]["New"]["Target_ATH"]), key=f"{ticker}_new_ath")
                    data[ticker]["New"] = {"Status": new_status, "Target_ATH": new_ath}

                with e_col3:
                    st.write("**[Old 사이클]**")
                    old_status = st.selectbox(f"{ticker} Old 상태", ["READY", "ACTIVE", "PAUSED"], 
                                              index=["READY", "ACTIVE", "PAUSED"].index(data[ticker]["Old"]["Status"]), key=f"{ticker}_old_st")
                    old_ath = st.number_input(f"{ticker} Old 박제 ATH", value=float(data[ticker]["Old"]["Target_ATH"]), key=f"{ticker}_old_ath")
                    data[ticker]["Old"] = {"Status": old_status, "Target_ATH": old_ath}
                
                st.divider()

        if st.button("💾 모든 전략 변경사항 Gist에 저장", use_container_width=True):
            if update_gist_data(token, gist_id, data):
                st.success("전략이 성공적으로 저장되었습니다!")
                st.balloons()
    else:
        st.error("데이터를 불러오지 못했습니다. 사이드바의 인증 정보를 확인하세요.")
else:
    st.warning("👈 사이드바에 GitHub Token과 Gist ID를 입력해주세요.")
