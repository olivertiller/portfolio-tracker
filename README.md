# Portfolio Daily Movers API

Lightweight API that returns daily price changes for a personal stock portfolio using yfinance. Designed to be fetched by Claude for daily portfolio news summaries.

## Endpoints

- `GET /portfolio` — All stocks with daily % change
- `GET /movers?threshold=2.0` — Only stocks that moved ±2% or more

## Deploy to Railway

1. Push this folder to a GitHub repo (or use `railway init`)
2. Connect the repo in Railway dashboard
3. Railway auto-detects Python + Procfile — no config needed
4. Note the public URL (e.g. `https://portfolio-api-production-xxxx.up.railway.app`)

## Local development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Usage in Claude prompt

Add this to your daily summary prompt:

```
Before analyzing news, fetch my portfolio data from:
https://YOUR-RAILWAY-URL.up.railway.app/movers

Use the returned JSON to identify which stocks moved ±2% today,
then search for news only on those movers.
```

## Example response from /movers

```json
{
  "generated_at": "2026-03-23T14:30:00Z",
  "threshold_pct": 2.0,
  "movers_count": 3,
  "movers": [
    {"ticker": "RIVN", "name": "Rivian Automotive", "market": "US", "price": 12.45, "prev_close": 12.85, "change_pct": -3.11, "date": "2026-03-23"},
    {"ticker": "ENR.DE", "name": "Siemens Energy", "market": "Europe", "price": 58.30, "prev_close": 56.80, "change_pct": 2.64, "date": "2026-03-23"},
    {"ticker": "NOD.OL", "name": "Nordic Semiconductor", "market": "Nordic", "price": 98.50, "prev_close": 101.20, "change_pct": -2.67, "date": "2026-03-23"}
  ],
  "no_significant_move": ["AMZN", "BRK-B", "META", "MSFT", ...]
}
```
