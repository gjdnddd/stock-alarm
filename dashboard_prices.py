import os, json, requests, yfinance as yf
from datetime import datetime, timezone

US_TICKERS = ["TQQQ", "SOXL"]
KR_TICKERS = ["157450", "232080", "390390", "0069M0", "0046A0"]


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


def main():
    token, gist_id = clean_env("MY_GITHUB_TOKEN"), clean_env("MY_GIST_ID")

    data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "us": {t: p for t in US_TICKERS if (p := get_price(t)) is not None},
        "pension": {t: p for t in KR_TICKERS if (p := get_price(t + ".KS")) is not None},
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
