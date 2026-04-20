"""Fetch portfolio movers and update a GitHub Gist with the results."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from portfolios import PORTFOLIOS

THRESHOLD = 2.0


def fetch_single(ticker: str, info: dict) -> dict | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        prev_close = closes.iloc[-2]
        last_close = closes.iloc[-1]
        change_pct = ((last_close - prev_close) / prev_close) * 100
        return {
            "ticker": ticker,
            "name": info["name"],
            "market": info["market"],
            "price": round(float(last_close), 2),
            "prev_close": round(float(prev_close), 2),
            "change_pct": round(float(change_pct), 2),
            "date": closes.index[-1].strftime("%Y-%m-%d"),
        }
    except Exception as e:
        print(f"Warning: {ticker} failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio", default="private", choices=list(PORTFOLIOS.keys()))
    args = parser.parse_args()

    portfolio_id = args.portfolio
    stocks = PORTFOLIOS[portfolio_id]["stocks"]
    print(f"Fetching movers for portfolio: {portfolio_id} ({len(stocks)} stocks)")

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_single, ticker, info): ticker
            for ticker, info in stocks.items()
        }
        raw = [f.result() for f in futures]
        results = [r for r in raw if r is not None]

    results.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)

    movers = [s for s in results if abs(s["change_pct"]) >= THRESHOLD]
    calm = [s for s in results if abs(s["change_pct"]) < THRESHOLD]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_pct": THRESHOLD,
        "movers_count": len(movers),
        "movers": movers,
        "no_significant_move": [s["ticker"] for s in calm],
    }

    json_str = json.dumps(payload, indent=2)
    print(json_str)

    gist_id = os.environ.get("GIST_ID")
    if not gist_id:
        print("No GIST_ID set, skipping gist update")
        return

    tmp_path = f"/tmp/movers_{portfolio_id}.json"
    with open(tmp_path, "w") as f:
        f.write(json_str)

    filename = f"movers_{portfolio_id}.json"
    subprocess.run(
        [
            "gh", "api", "--method", "PATCH", f"/gists/{gist_id}",
            "-f", f"files[{filename}][content]={json_str}",
        ],
        check=True,
        capture_output=True,
    )
    print(f"Gist updated: https://gist.github.com/{gist_id}")


if __name__ == "__main__":
    main()
