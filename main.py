from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import yfinance as yf
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import json
import os
import requests as http_requests

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
    "ENR.DE":  {"name": "Siemens Energy", "market": "Europe"},
    # Oslo Børs
    "AKER.OL":  {"name": "Aker", "market": "Nordic"},
    "GJF.OL":   {"name": "Gjensidige Forsikring", "market": "Nordic"},
    "KID.OL":   {"name": "KID", "market": "Nordic"},
    "KIT.OL":   {"name": "Kitron", "market": "Nordic"},
    "KOMPL.OL": {"name": "Komplett", "market": "Nordic"},
    "KOG.OL":   {"name": "Kongsberg Gruppen", "market": "Nordic"},
    "NOD.OL":   {"name": "Nordic Semiconductor", "market": "Nordic"},
    "NHY.OL":   {"name": "Norsk Hydro", "market": "Nordic"},
    "NORBIT.OL": {"name": "NORBIT", "market": "Nordic"},
    "PARB.OL":  {"name": "Pareto Bank", "market": "Nordic"},
    "VEND.OL":  {"name": "Vend Marketplaces", "market": "Nordic"},
}

CACHE_TTL = timedelta(minutes=15)
_cache_lock = threading.Lock()
_cache = {"data": None, "timestamp": None}

# Reports cache (fetched from GitHub Gist)
_reports_cache = {"data": None, "timestamp": None}
REPORTS_CACHE_TTL = timedelta(minutes=5)


def _now():
    return datetime.now(timezone.utc)


def _fetch_reports_from_gist() -> list[dict]:
    """Fetch reports.json from the public GitHub Gist."""
    now = _now()
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
        reports.sort(key=lambda r: r.get("date", ""), reverse=True)

        _reports_cache["data"] = reports
        _reports_cache["timestamp"] = now
        return reports
    except Exception as e:
        print(f"Failed to fetch reports from gist: {e}")
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
            and _now() - _cache["timestamp"] < CACHE_TTL
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
        _cache["timestamp"] = _now()

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

    try:
        claims = json.loads(_env("VAPID_CLAIMS", '{"sub": "mailto:admin@example.com"}'))
    except json.JSONDecodeError:
        print("VAPID_CLAIMS is not valid JSON, skipping push")
        return

    subscriptions = _load_push_subs()
    print(f"Sending push to {len(subscriptions)} subscribers")

    for sub in subscriptions:
        sub_info = {"endpoint": sub["endpoint"], "keys": sub.get("keys", {})}
        try:
            webpush(
                subscription_info=sub_info,
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=_env("VAPID_PRIVATE_KEY"),
                vapid_claims=claims,
            )
        except WebPushException as e:
            resp = getattr(e, "response", None)
            if resp and resp.status_code in (404, 410):
                subs = [s for s in _load_push_subs() if s["endpoint"] != sub["endpoint"]]
                _save_push_subs(subs)
                print(f"Removed expired subscription: {sub['endpoint'][:50]}...")
            else:
                print(f"Push failed for {sub['endpoint'][:50]}: {e}")


# --- Push subscription storage (in Gist, persists across deploys) ---

_push_subs_cache = {"data": None}
_push_subs_lock = threading.Lock()


def _load_push_subs() -> list[dict]:
    with _push_subs_lock:
        if _push_subs_cache["data"] is not None:
            return _push_subs_cache["data"]
    try:
        resp = http_requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        files = resp.json().get("files", {})
        if "push_subscriptions.json" in files:
            content = files["push_subscriptions.json"].get("content", "[]")
            subs = json.loads(content)
            with _push_subs_lock:
                _push_subs_cache["data"] = subs
            return subs
    except Exception as e:
        print(f"Failed to load push subs: {e}")
    with _push_subs_lock:
        _push_subs_cache["data"] = []
    return []


def _save_push_subs(subs: list[dict]):
    with _push_subs_lock:
        _push_subs_cache["data"] = subs
    token = _env("GH_TOKEN") or _env("GIST_TOKEN")
    if not token:
        print("No GH_TOKEN, cannot save push subscriptions")
        return
    try:
        content = json.dumps(subs, indent=2)
        http_requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"files": {"push_subscriptions.json": {"content": content}}},
            timeout=10,
        )
    except Exception as e:
        print(f"Failed to save push subs: {e}")


# --- API endpoints ---

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/portfolio")
def portfolio(refresh: bool = Query(default=False, description="Bypass cache")):
    changes = get_daily_changes(refresh=refresh)
    return {
        "generated_at": _now().isoformat(),
        "count": len(changes),
        "stocks": changes,
    }


@app.get("/api/movers")
def movers(
    threshold: float = Query(default=2.0, description="Min absolute % change"),
    refresh: bool = Query(default=False, description="Bypass cache"),
):
    changes = get_daily_changes(refresh=refresh)
    significant = [s for s in changes if abs(s.get("change_pct", 0)) >= threshold]
    calm = [s for s in changes if abs(s.get("change_pct", 0)) < threshold and "error" not in s]

    return {
        "generated_at": _now().isoformat(),
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
    return [
        {"date": r.get("date", ""), "created_at": r.get("created_at", "")}
        for r in reports[offset:offset + limit]
    ]


@app.get("/api/report/{date}")
def report_by_date(date: str):
    reports = _fetch_reports_from_gist()
    for r in reports:
        if r.get("date") == date:
            return r
    raise HTTPException(status_code=404, detail="Report not found")


# Trigger push notifications when a new report is published
@app.post("/api/push/notify")
def trigger_push(request_body: dict, x_api_key: str = Header(default=None)):
    _verify_api_key(x_api_key)
    _reports_cache["data"] = None
    try:
        _send_push_notifications(
            title=request_body.get("title", "Porteføljerapport"),
            body=request_body.get("body", "Ny rapport er klar"),
        )
        return {"status": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}


# --- Push subscription endpoints ---

@app.get("/api/push/vapid-key")
def vapid_key():
    if not _env("VAPID_PUBLIC_KEY"):
        raise HTTPException(status_code=500, detail="VAPID keys not configured")
    return {"publicKey": _env("VAPID_PUBLIC_KEY")}


@app.post("/api/push/subscribe")
def subscribe(subscription: dict):
    if not subscription.get("endpoint") and not subscription.get("token"):
        raise HTTPException(status_code=400, detail="Invalid subscription")
    subs = _load_push_subs()
    # Deduplicate by endpoint or APNs token
    key = subscription.get("token") or subscription.get("endpoint")
    subs = [s for s in subs if (s.get("token") or s.get("endpoint")) != key]
    subs.append(subscription)
    _save_push_subs(subs)
    return {"status": "subscribed"}


@app.delete("/api/push/subscribe")
def unsubscribe(body: dict):
    endpoint = body.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint required")
    subs = [s for s in _load_push_subs() if s["endpoint"] != endpoint]
    _save_push_subs(subs)
    return {"status": "unsubscribed"}


# --- Sparkline data ---

_sparkline_cache = {"data": None, "timestamp": None}
SPARKLINE_TTL = timedelta(hours=1)


@app.get("/api/sparklines")
def sparklines():
    now = _now()
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
