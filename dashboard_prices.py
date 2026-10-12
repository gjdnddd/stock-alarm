import os, re, json, requests, yfinance as yf
from datetime import datetime, timezone

US_TICKERS = ["TQQQ", "SOXL"]
KR_TICKERS = ["157450", "232080", "390390", "0069M0", "0046A0"]  # 기본 목록 (항상 포함)
KR_TICKER_RE = re.compile(r"^[0-9A-Z]{6}$")


def clean_env(name):
    return os.environ.get(name, "").strip().lstrip("﻿")


def get_price(yahoo_symbol):
    try:
        df = yf.Ticker(yahoo_symbol).history(period="5d")
        if df.empty:
            return None
        return round(float(df["Close"].iloc[-1]), 2)
    except Exception:
        return None


def load_kr_tickers(gist_id, token):
    """대시보드(invest_data.json)의 퇴직연금 보유종목 티커를 기본 목록에 합친다.
    읽기에 실패하면 기본 목록만 사용한다 (수집 자체는 계속)."""
    tickers = list(KR_TICKERS)
    try:
        headers = {"Authorization": f"token {token}"} if token else {}
        res = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers, timeout=20)
        res.raise_for_status()
        content = res.json()["files"]["invest_data.json"]["content"]
        for h in json.loads(content).get("pension_holdings", []):
            t = str(h.get("ticker", "")).strip().upper()
            if KR_TICKER_RE.match(t) and t not in tickers:
                tickers.append(t)
    except Exception as e:
        print(f"pension ticker list fallback to defaults: {e}")
    return tickers


def main():
    token, gist_id = clean_env("MY_GITHUB_TOKEN"), clean_env("MY_GIST_ID")
    kr_tickers = load_kr_tickers(gist_id, token)

    data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "us": {t: p for t in US_TICKERS if (p := get_price(t)) is not None},
        "pension": {t: p for t in kr_tickers if (p := get_price(t + ".KS")) is not None},
    }

    payload = {"files": {"dashboard_prices.json": {"content": json.dumps(data, ensure_ascii=False, indent=2)}}}
    res = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {token}"},
        json=payload,
    )
    res.raise_for_status()
    print(f"Saved: {data}")


if __name__ == "__main__":
    main()
