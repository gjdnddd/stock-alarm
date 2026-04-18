import streamlit as st
import pandas as pd
import os
import json
import requests

# 페이지 설정
st.set_page_config(page_title="US Stock Alarm Dashboard", layout="wide")

# Gist 연동 함수 (기존 클래스 활용 가능)
def get_gist_data(token, gist_id):
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {token}"}
    res = requests.get(url, headers=headers)
    
    if res.status_code != 200:
        st.error(f"Gist 데이터를 불러오지 못했습니다. 상태 코드: {res.status_code}")
        return {}

    files = res.json().get('files', {})
    content = files.get('stock_data.json', {}).get('content', '{}')
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        st.error(f"JSON 형식이 잘못되었습니다: {e}")
        st.info("Gist 웹페이지에서 주석(//) 등을 제거하고 올바른 JSON 형식인지 확인하세요.")
        return {}

def update_gist_data(token, gist_id, data):
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {token}"}
    payload = {"files": {"stock_data.json": {"content": json.dumps(data, indent=2)}}}
    requests.patch(url, headers=headers, json=payload)

# --- 대시보드 시작 ---
st.title("📈 미국주식 하락률 알람 관리")

# 사이드바에서 설정 (테스트용)
# 실제로는 .env나 Secrets 사용 권장
token = st.sidebar.text_input("GitHub Token", type="password")
gist_id = st.sidebar.text_input("Gist ID")

if token and gist_id:
    data = get_gist_data(token, gist_id)
    
    col1, col2 = st.columns(2)
    
    for i, (ticker, details) in enumerate(data.items()):
        with [col1, col2][i]:
            st.subheader(f"[{ticker}] 전략 상태")
            
            # 상태 변경 UI (수정 사항은 나중에 몰아서 구현하되, 입력창만 배치)
            status = st.selectbox(f"{ticker} Status", ["READY", "ACTIVE", "PAUSED"], index=["READY", "ACTIVE", "PAUSED"].index(details['Status']), key=f"{ticker}_status")
            infi_base = st.number_input(f"{ticker} 무매 기준가", value=float(details.get('Infi_Base', 0.0)), key=f"{ticker}_infi")
            
            # 데이터 저장 버튼
            if st.button(f"{ticker} 설정 저장"):
                data[ticker]['Status'] = status
                data[ticker]['Infi_Base'] = infi_base
                update_gist_data(token, gist_id, data)
                st.success(f"{ticker} 정보가 업데이트되었습니다.")

else:
    st.info("사이드바에 토큰과 Gist ID를 입력해주세요.")