from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import yfinance as yf
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import threading
import json
import os
import requests as http_requests

from db import init_db, save_subscription, delete_subscription, get_all_subscriptions

app = FastAPI(title="Portfolio Daily Movers")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def _env(key, default=""):
    return os.environ.get(key, default)
GIST_ID = os.environ.get("GIST_ID", "24236a25d105c46c64f122e4d60e12d6")

DEFAULT_PORTFOLIO = {
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
    "NOD.OL":   {"name": "Nordic Semiconductor", "market": "Nordic"},
    "NHY.OL":   {"name": "Norsk Hydro", "market": "Nordic"},
    "PARB.OL":  {"name": "Pareto Bank", "market": "Nordic"},
    "SALM.OL":  {"name": "SalMar", "market": "Nordic"},
    "TEL.OL":   {"name": "Telenor", "market": "Nordic"},
    "VEND.OL":  {"name": "Vend Marketplaces", "market": "Nordic"},
}

CACHE_TTL = timedelta(minutes=15)
_cache_lock = threading.Lock()
_cache = {"data": None, "timestamp": None}

# Reports cache (fetched from GitHub Gist)
_reports_cache = {"data": None, "timestamp": None}
REPORTS_CACHE_TTL = timedelta(minutes=5)


def _fetch_reports_from_gist() -> list[dict]:
    """Fetch reports.json from the public GitHub Gist."""
    now = datetime.utcnow()
    if (
        _reports_cache["data"] is not None
        and now - _reports_cache["timestamp"] < REPORTS_CACHE_TTL
    ):
        return _reports_cache["data"]

    try:
        resp = http_requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        gist = resp.json()
        files = gist.get("files", {})

        if "reports.json" not in files:
            _reports_cache["data"] = []
            _reports_cache["timestamp"] = now
            return []

        content = files["reports.json"].get("content", "[]")
        reports = json.loads(content)
        reports.sort(key=lambda r: r["date"], reverse=True)

        _reports_cache["data"] = reports
        _reports_cache["timestamp"] = now
        return reports
    except Exception as e:
        print(f"Failed to fetch reports from gist: {e}")
        # Return stale cache if available
        if _reports_cache["data"] is not None:
            return _reports_cache["data"]
        return []


def _fetch_single(ticker: str, info: dict) -> dict:
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
        return {
            "ticker": ticker,
            "name": info["name"],
            "market": info["market"],
            "error": str(e),
        }


def get_daily_changes(refresh: bool = False):
    with _cache_lock:
        if (
            not refresh
            and _cache["data"] is not None
            and datetime.utcnow() - _cache["timestamp"] < CACHE_TTL
        ):
            return _cache["data"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_single, ticker, info): ticker
            for ticker, info in DEFAULT_PORTFOLIO.items()
        }
        results = []
        for future in futures:
            result = future.result()
            if result is not None:
                results.append(result)

    results.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)

    with _cache_lock:
        _cache["data"] = results
        _cache["timestamp"] = datetime.utcnow()

    return results


def _verify_api_key(x_api_key: str | None):
    if not _env("API_SECRET"):
        raise HTTPException(status_code=500, detail="API_SECRET not configured")
    if x_api_key != _env("API_SECRET"):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _send_push_notifications(title: str, body: str):
    if not _env("VAPID_PRIVATE_KEY"):
        print("VAPID keys not configured, skipping push")
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("pywebpush not installed, skipping push")
        return

    claims = json.loads(_env("VAPID_CLAIMS", '{"sub": "mailto:admin@example.com"}'))
    subscriptions = get_all_subscriptions()
    print(f"Sending push to {len(subscriptions)} subscribers")

    for sub in subscriptions:
        sub_info = {"endpoint": sub["endpoint"], "keys": sub["keys"]}
        try:
            webpush(
                subscription_info=sub_info,
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=_env("VAPID_PRIVATE_KEY"),
                vapid_claims=claims,
            )
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                delete_subscription(sub["endpoint"])
                print(f"Removed expired subscription: {sub['endpoint'][:50]}...")
            else:
                print(f"Push failed: {e}")


# --- Startup ---

@app.on_event("startup")
def startup():
    init_db()


# --- API endpoints ---

@app.get("/health")
def health():
    """Lightweight endpoint to wake the service without fetching data."""
    return {"status": "ok"}


@app.get("/api/portfolio")
def portfolio(refresh: bool = Query(default=False, description="Bypass cache")):
    """All stocks with daily change."""
    changes = get_daily_changes(refresh=refresh)
    cached = not refresh and _cache["data"] is changes
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cached": cached,
        "count": len(changes),
        "stocks": changes,
    }


@app.get("/api/movers")
def movers(
    threshold: float = Query(default=2.0, description="Min absolute % change"),
    refresh: bool = Query(default=False, description="Bypass cache"),
):
    """Only stocks that moved more than +/-threshold%."""
    changes = get_daily_changes(refresh=refresh)
    significant = [s for s in changes if abs(s.get("change_pct", 0)) >= threshold]
    calm = [s for s in changes if abs(s.get("change_pct", 0)) < threshold and "error" not in s]
    cached = not refresh and _cache["data"] is changes

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cached": cached,
        "threshold_pct": threshold,
        "movers_count": len(significant),
        "movers": significant,
        "no_significant_move": [s["ticker"] for s in calm],
    }


# Keep old endpoints working
@app.get("/portfolio")
def portfolio_compat(refresh: bool = Query(default=False)):
    return portfolio(refresh=refresh)


@app.get("/movers")
def movers_compat(
    threshold: float = Query(default=2.0),
    refresh: bool = Query(default=False),
):
    return movers(threshold=threshold, refresh=refresh)


# --- Report endpoints (read from Gist) ---

@app.get("/api/report")
def latest_report():
    reports = _fetch_reports_from_gist()
    if not reports:
        raise HTTPException(status_code=404, detail="No reports yet")
    return reports[0]


@app.get("/api/reports")
def list_reports(
    limit: int = Query(default=30),
    offset: int = Query(default=0),
):
    reports = _fetch_reports_from_gist()
    return [{"date": r["date"], "created_at": r["created_at"]} for r in reports[offset:offset + limit]]


@app.get("/api/report/{date}")
def report_by_date(date: str):
    reports = _fetch_reports_from_gist()
    for r in reports:
        if r["date"] == date:
            return r
    raise HTTPException(status_code=404, detail="Report not found")


# Trigger push notifications when a new report is published
@app.post("/api/push/notify")
def trigger_push(request_body: dict, x_api_key: str = Header(default=None)):
    _verify_api_key(x_api_key)
    # Invalidate reports cache so next read picks up the new report
    _reports_cache["data"] = None
    _send_push_notifications(
        title=request_body.get("title", "Porteføljerapport"),
        body=request_body.get("body", "Ny rapport er klar"),
    )
    return {"status": "ok"}


# --- Push subscription endpoints ---

@app.get("/api/push/vapid-key")
def vapid_key():
    if not _env("VAPID_PUBLIC_KEY"):
        raise HTTPException(status_code=500, detail="VAPID keys not configured")
    return {"publicKey": _env("VAPID_PUBLIC_KEY")}


@app.post("/api/push/subscribe")
def subscribe(subscription: dict):
    if not subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="Invalid subscription")
    save_subscription(subscription)
    return {"status": "subscribed"}


@app.delete("/api/push/subscribe")
def unsubscribe(body: dict):
    endpoint = body.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint required")
    delete_subscription(endpoint)
    return {"status": "unsubscribed"}


# --- Sparkline data ---

_sparkline_cache = {"data": None, "timestamp": None}
SPARKLINE_TTL = timedelta(hours=1)


@app.get("/api/sparklines")
def sparklines():
    """3-month daily closes for all portfolio stocks."""
    now = datetime.utcnow()
    if (
        _sparkline_cache["data"] is not None
        and now - _sparkline_cache["timestamp"] < SPARKLINE_TTL
    ):
        return _sparkline_cache["data"]

    result = {}

    def fetch_sparkline(ticker):
        try:
            hist = yf.Ticker(ticker).history(period="3mo")
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                return ticker, []
            prices = [round(float(c), 2) for c in closes.values]
            return ticker, prices
        except Exception:
            return ticker, []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_sparkline, t) for t in DEFAULT_PORTFOLIO]
        for f in futures:
            ticker, prices = f.result()
            result[ticker] = prices

    _sparkline_cache["data"] = result
    _sparkline_cache["timestamp"] = now
    return result


# --- Static files (must be last) ---

app.mount("/", StaticFiles(directory="static", html=True), name="static")
