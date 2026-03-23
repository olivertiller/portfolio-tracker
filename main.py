from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from datetime import datetime, timedelta
import json

app = FastAPI(title="Portfolio Daily Movers")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

PORTFOLIO = {
    # US-listed
    "AMZN":    {"name": "Amazon", "market": "US"},
    "BRK-B":   {"name": "Berkshire Hathaway B", "market": "US"},
    "META":    {"name": "Meta Platforms", "market": "US"},
    "MSFT":    {"name": "Microsoft", "market": "US"},
    "NVT":     {"name": "nVent Electric", "market": "US"},
    "RCL":     {"name": "Royal Caribbean Cruises", "market": "US"},
    "RIVN":    {"name": "Rivian Automotive", "market": "US"},
    "VRT":     {"name": "Vertiv Holdings", "market": "US"},
    # Europe-listed
    "OR.PA":   {"name": "L'Oréal", "market": "Europe"},
    "MC.PA":   {"name": "LVMH", "market": "Europe"},
    "BMW.DE":  {"name": "BMW", "market": "Europe"},
    "ENR.DE":  {"name": "Siemens Energy", "market": "Europe"},
    # Oslo Børs
    "AKER.OL":  {"name": "Aker", "market": "Nordic"},
    "GJF.OL":   {"name": "Gjensidige Forsikring", "market": "Nordic"},
    "KCC.OL":   {"name": "Klaveness Combination Carriers", "market": "Nordic"},
    "KID.OL":   {"name": "KID", "market": "Nordic"},
    "KIT.OL":   {"name": "Kitron", "market": "Nordic"},
    "KOMPL.OL": {"name": "Komplett", "market": "Nordic"},
    "KOG.OL":   {"name": "Kongsberg Gruppen", "market": "Nordic"},
    "NORBT.OL": {"name": "NORBIT", "market": "Nordic"},
    "NOD.OL":   {"name": "Nordic Semiconductor", "market": "Nordic"},
    "NHY.OL":   {"name": "Norsk Hydro", "market": "Nordic"},
    "PARB.OL":  {"name": "Pareto Bank", "market": "Nordic"},
    "SALM.OL":  {"name": "SalMar", "market": "Nordic"},
    "TEL.OL":   {"name": "Telenor", "market": "Nordic"},
    "VEND.OL":  {"name": "Vend Marketplaces", "market": "Nordic"},
}

def get_daily_changes():
    tickers_str = " ".join(PORTFOLIO.keys())
    data = yf.download(tickers_str, period="5d", group_by="ticker", progress=False)

    results = []
    for ticker, info in PORTFOLIO.items():
        try:
            if len(PORTFOLIO) == 1:
                ticker_data = data
            else:
                ticker_data = data[ticker]

            closes = ticker_data["Close"].dropna()
            if len(closes) < 2:
                continue

            prev_close = closes.iloc[-2]
            last_close = closes.iloc[-1]
            change_pct = ((last_close - prev_close) / prev_close) * 100
            last_date = closes.index[-1].strftime("%Y-%m-%d")

            results.append({
                "ticker": ticker,
                "name": info["name"],
                "market": info["market"],
                "price": round(float(last_close), 2),
                "prev_close": round(float(prev_close), 2),
                "change_pct": round(float(change_pct), 2),
                "date": last_date,
            })
        except Exception as e:
            results.append({
                "ticker": ticker,
                "name": info["name"],
                "market": info["market"],
                "error": str(e),
            })

    results.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)
    return results


@app.get("/")
def root():
    return {"status": "ok", "endpoints": ["/portfolio", "/movers"]}


@app.get("/portfolio")
def portfolio():
    """All stocks with daily change."""
    changes = get_daily_changes()
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(changes),
        "stocks": changes,
    }


@app.get("/movers")
def movers(threshold: float = Query(default=2.0, description="Min absolute % change")):
    """Only stocks that moved more than ±threshold%."""
    changes = get_daily_changes()
    significant = [s for s in changes if abs(s.get("change_pct", 0)) >= threshold]
    calm = [s for s in changes if abs(s.get("change_pct", 0)) < threshold and "error" not in s]

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "threshold_pct": threshold,
        "movers_count": len(significant),
        "movers": significant,
        "no_significant_move": [s["ticker"] for s in calm],
    }
