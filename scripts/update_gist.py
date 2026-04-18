"""Fetch portfolio movers and update a GitHub Gist with the results."""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yfinance as yf

PORTFOLIO = {
    "AMZN": {"name": "Amazon", "market": "US"},
    "BRK-B": {"name": "Berkshire Hathaway B", "market": "US"},
    "META": {"name": "Meta Platforms", "market": "US"},
    "MSFT": {"name": "Microsoft", "market": "US"},
    "NVT": {"name": "nVent Electric", "market": "US"},
    "RCL": {"name": "Royal Caribbean Cruises", "market": "US"},
    "RIVN": {"name": "Rivian Automotive", "market": "US"},
    "VRT": {"name": "Vertiv Holdings", "market": "US"},
    "OR.PA": {"name": "L'Oréal", "market": "Europe"},
    "MC.PA": {"name": "LVMH", "market": "Europe"},
    "BMW.DE": {"name": "BMW", "market": "Europe"},
    "ENR.DE": {"name": "Siemens Energy", "market": "Europe"},
    "AKER.OL": {"name": "Aker", "market": "Nordic"},
    "GJF.OL": {"name": "Gjensidige Forsikring", "market": "Nordic"},
    "KCC.OL": {"name": "Klaveness Combination Carriers", "market": "Nordic"},
    "KID.OL": {"name": "KID", "market": "Nordic"},
    "KIT.OL": {"name": "Kitron", "market": "Nordic"},
    "KOMPL.OL": {"name": "Komplett", "market": "Nordic"},
    "KOG.OL": {"name": "Kongsberg Gruppen", "market": "Nordic"},
    "NOD.OL": {"name": "Nordic Semiconductor", "market": "Nordic"},
    "NHY.OL": {"name": "Norsk Hydro", "market": "Nordic"},
    "PARB.OL": {"name": "Pareto Bank", "market": "Nordic"},
    "SALM.OL": {"name": "SalMar", "market": "Nordic"},
    "TEL.OL": {"name": "Telenor", "market": "Nordic"},
    "VEND.OL": {"name": "Vend Marketplaces", "market": "Nordic"},
}

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
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_single, ticker, info): ticker
            for ticker, info in PORTFOLIO.items()
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

    tmp_path = "/tmp/movers.json"
    with open(tmp_path, "w") as f:
        f.write(json_str)

    subprocess.run(
        ["gh", "gist", "edit", gist_id, "--filename", "movers.json", tmp_path],
        check=True,
    )
    print(f"Gist updated: https://gist.github.com/{gist_id}")


if __name__ == "__main__":
    main()
