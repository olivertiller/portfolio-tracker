from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import yfinance as yf
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import json
import os
import time
import jwt
import httpx
import requests as http_requests
from server.portfolios import PORTFOLIOS

app = FastAPI(title="Portfolio Daily Movers")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_PORTFOLIOS = list(PORTFOLIOS.keys())


def _env(key, default=""):
    return os.environ.get(key, default)


def _validate_portfolio(portfolio: str) -> str:
    if portfolio not in VALID_PORTFOLIOS:
        raise HTTPException(status_code=400, detail=f"Invalid portfolio: {portfolio}")
    return portfolio


GIST_ID = os.environ.get("GIST_ID", "24236a25d105c46c64f122e4d60e12d6")

CACHE_TTL = timedelta(minutes=15)
_cache_lock = threading.Lock()
_cache = {}  # keyed by portfolio id

# Reports cache (fetched from GitHub Gist)
_reports_cache = {}  # keyed by portfolio id
REPORTS_CACHE_TTL = timedelta(minutes=5)


def _now():
    return datetime.now(timezone.utc)


def _fetch_reports_from_gist(portfolio: str = "private") -> list[dict]:
    """Fetch reports for a portfolio from the public GitHub Gist."""
    now = _now()
    cached = _reports_cache.get(portfolio)
    if (
        cached is not None
        and cached["data"] is not None
        and now - cached["timestamp"] < REPORTS_CACHE_TTL
    ):
        return cached["data"]

    try:
        resp = http_requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        gist = resp.json()
        files = gist.get("files", {})

        # Try portfolio-specific file, fall back to reports.json for private
        filename = f"reports_{portfolio}.json"
        if filename not in files and portfolio == "private" and "reports.json" in files:
            filename = "reports.json"

        if filename not in files:
            _reports_cache[portfolio] = {"data": [], "timestamp": now}
            return []

        content = files[filename].get("content", "[]")
        reports = json.loads(content)
        reports.sort(key=lambda r: r.get("date", ""), reverse=True)

        _reports_cache[portfolio] = {"data": reports, "timestamp": now}
        return reports
    except Exception as e:
        print(f"Failed to fetch reports from gist: {e}")
        cached = _reports_cache.get(portfolio)
        if cached and cached["data"] is not None:
            return cached["data"]
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


def get_daily_changes(portfolio: str = "private", refresh: bool = False):
    stocks = PORTFOLIOS[portfolio]["stocks"]
    with _cache_lock:
        cached = _cache.get(portfolio)
        if (
            not refresh
            and cached is not None
            and cached["data"] is not None
            and _now() - cached["timestamp"] < CACHE_TTL
        ):
            return cached["data"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_single, ticker, info): ticker
            for ticker, info in stocks.items()
        }
        results = []
        for future in futures:
            result = future.result()
            if result is not None:
                results.append(result)

    # Filter out stocks with stale dates
    dates = {}
    for r in results:
        d = r.get("date")
        if d:
            dates.setdefault(d, []).append(r["ticker"])
    if len(dates) > 1:
        expected_date = max(dates, key=lambda d: len(dates[d]))
        stale_tickers = {t for d, tickers in dates.items() if d != expected_date for t in tickers}
        results = [r for r in results if r["ticker"] not in stale_tickers]
        print(f"Filtered {len(stale_tickers)} stocks with stale data (expected {expected_date})")

    results.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)

    with _cache_lock:
        _cache[portfolio] = {"data": results, "timestamp": _now()}

    return results


def _verify_api_key(x_api_key: str | None):
    if not _env("API_SECRET"):
        raise HTTPException(status_code=500, detail="API_SECRET not configured")
    if x_api_key != _env("API_SECRET"):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _send_apns(token: str, title: str, body: str):
    """Send a push notification via APNs using a .p8 key."""
    key_id = _env("APNS_KEY_ID")
    team_id = _env("APNS_TEAM_ID")
    key_content = _env("APNS_KEY")
    bundle_id = "com.olivertiller.portefolje"

    if not all([key_id, team_id, key_content]):
        print("APNs not configured (need APNS_KEY_ID, APNS_TEAM_ID, APNS_KEY)")
        return False

    # Build JWT for APNs auth
    now = int(time.time())
    payload = {"iss": team_id, "iat": now}
    headers = {"alg": "ES256", "kid": key_id}
    apns_token = jwt.encode(payload, key_content, algorithm="ES256", headers=headers)

    apns_payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
            "badge": 1,
        }
    }

    url = f"https://api.push.apple.com/3/device/{token}"
    with httpx.Client(http2=True) as client:
        resp = client.post(
            url,
            json=apns_payload,
            headers={
                "authorization": f"bearer {apns_token}",
                "apns-topic": bundle_id,
                "apns-push-type": "alert",
            },
        )

    if resp.status_code == 200:
        print(f"APNs push sent to {token[:12]}...")
        return True
    elif resp.status_code in (400, 410):
        print(f"APNs token invalid/expired ({resp.status_code}): {token[:12]}...")
        return False
    else:
        print(f"APNs push failed ({resp.status_code}): {resp.text}")
        return True  # don't remove token on transient errors


def _send_push_notifications(title: str, body: str):
    subscriptions = _load_push_subs()
    if not subscriptions:
        print("No push subscribers")
        return

    print(f"Sending push to {len(subscriptions)} subscribers")
    removed = []

    for sub in subscriptions:
        apns_token = sub.get("token")
        if apns_token:
            ok = _send_apns(apns_token, title, body)
            if not ok:
                removed.append(sub)
            continue

        # Web push fallback
        endpoint = sub.get("endpoint")
        if not endpoint or not _env("VAPID_PRIVATE_KEY"):
            continue
        try:
            from pywebpush import webpush, WebPushException
            claims = json.loads(_env("VAPID_CLAIMS", '{"sub": "mailto:admin@example.com"}'))
            webpush(
                subscription_info={"endpoint": endpoint, "keys": sub.get("keys", {})},
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=_env("VAPID_PRIVATE_KEY"),
                vapid_claims=claims,
            )
        except Exception as e:
            resp = getattr(e, "response", None)
            if resp and getattr(resp, "status_code", 0) in (404, 410):
                removed.append(sub)
            else:
                print(f"Web push failed: {e}")

    if removed:
        current = _load_push_subs()
        removed_keys = {s.get("token") or s.get("endpoint") for s in removed}
        current = [s for s in current if (s.get("token") or s.get("endpoint")) not in removed_keys]
        _save_push_subs(current)
        print(f"Removed {len(removed)} expired subscriptions")


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
def portfolio(
    portfolio: str = Query(default="private"),
    refresh: bool = Query(default=False, description="Bypass cache"),
):
    _validate_portfolio(portfolio)
    changes = get_daily_changes(portfolio=portfolio, refresh=refresh)
    return {
        "generated_at": _now().isoformat(),
        "count": len(changes),
        "stocks": changes,
    }


@app.get("/api/movers")
def movers(
    portfolio: str = Query(default="private"),
    threshold: float = Query(default=2.0, description="Min absolute % change"),
    refresh: bool = Query(default=False, description="Bypass cache"),
):
    _validate_portfolio(portfolio)
    changes = get_daily_changes(portfolio=portfolio, refresh=refresh)
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
    return portfolio(portfolio="private", refresh=refresh)


@app.get("/movers")
def movers_compat(
    threshold: float = Query(default=2.0),
    refresh: bool = Query(default=False),
):
    return movers(portfolio="private", threshold=threshold, refresh=refresh)


# --- Report endpoints (read from Gist) ---

@app.get("/api/report")
def latest_report(portfolio: str = Query(default="private")):
    _validate_portfolio(portfolio)
    reports = _fetch_reports_from_gist(portfolio)
    if not reports:
        raise HTTPException(status_code=404, detail="No reports yet")
    return reports[0]


@app.get("/api/reports")
def list_reports(
    portfolio: str = Query(default="private"),
    limit: int = Query(default=30),
    offset: int = Query(default=0),
):
    _validate_portfolio(portfolio)
    reports = _fetch_reports_from_gist(portfolio)
    return [
        {"date": r.get("date", ""), "created_at": r.get("created_at", "")}
        for r in reports[offset:offset + limit]
    ]


@app.get("/api/report/{date}")
def report_by_date(date: str, portfolio: str = Query(default="private")):
    _validate_portfolio(portfolio)
    reports = _fetch_reports_from_gist(portfolio)
    for r in reports:
        if r.get("date") == date:
            return r
    raise HTTPException(status_code=404, detail="Report not found")


# Trigger push notifications when a new report is published
@app.post("/api/push/notify")
def trigger_push(request_body: dict, x_api_key: str = Header(default=None)):
    _verify_api_key(x_api_key)
    _reports_cache.clear()
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

_sparkline_cache = {}  # keyed by portfolio id
SPARKLINE_TTL = timedelta(hours=1)


@app.get("/api/sparklines")
def sparklines(portfolio: str = Query(default="private")):
    _validate_portfolio(portfolio)
    now = _now()
    cached = _sparkline_cache.get(portfolio)
    if (
        cached is not None
        and cached["data"] is not None
        and now - cached["timestamp"] < SPARKLINE_TTL
    ):
        return cached["data"]

    stocks = PORTFOLIOS[portfolio]["stocks"]
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
        futures = [executor.submit(fetch_sparkline, t) for t in stocks]
        for f in futures:
            ticker, prices = f.result()
            result[ticker] = prices

    _sparkline_cache[portfolio] = {"data": result, "timestamp": now}
    return result


# --- Static files with no-cache headers (must be last) ---

from starlette.responses import Response


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".html", ".js", ".css")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


import pathlib
_ROOT = pathlib.Path(__file__).resolve().parent.parent
app.mount("/", StaticFiles(directory=str(_ROOT / "static"), html=True), name="static")
