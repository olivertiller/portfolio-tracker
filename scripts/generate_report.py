"""Generate a daily portfolio report using Claude API and save to GitHub Gist."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import anthropic

SYSTEM_PROMPT = """You are a financial news analyst. You receive portfolio movers data and must explain each move.

You MUST respond with a valid JSON object and nothing else. No markdown, no commentary.

JSON schema:
{
  "summary": "1-2 sentences of macro context for the day (index moves, key events driving markets)",
  "movers": [
    {
      "name": "Company Name (from input data)",
      "ticker": "TICKER (from input data)",
      "change_pct": 3.5,
      "market": "Nordic|Europe|US (from input data)",
      "confirmed": true,
      "explanation": "Why the stock moved. 1-2 sentences max.",
      "source": "Reuters|Bloomberg|Newsweb|etc or null"
    }
  ]
}

Rules for the explanation field:
- Focus on WHY the stock moved — the catalyst only
- Never include company descriptions, history, sector overview, or background
- confirmed=true ONLY for hard news published on that specific trading day: earnings releases, contract wins, analyst upgrades/downgrades, regulatory decisions, M&A, profit warnings, etc.
- confirmed=false for everything else: pre-earnings positioning, "digesting" older news, sector spillovers, macro-driven moves, general sentiment
- When nothing plausible: "No confirmed catalyst. Likely followed the broad market."
- Max 1-2 sentences per stock

Order movers by market: Nordic first, then Europe, then US."""


def build_prompt(movers_data: dict) -> str:
    if movers_data.get("movers_count", 0) == 0 or not movers_data.get("movers"):
        return 'No movers today. Return: {"summary": "Quiet day — no stocks moved more than ±2%.", "movers": []}'

    movers_json = json.dumps(movers_data["movers"], indent=2)
    date = movers_data["movers"][0]["date"]

    return (
        f"Trading date: {date}\n"
        f"Movers (±{movers_data['threshold_pct']}% or more):\n\n"
        f"{movers_json}\n\n"
        f"For each mover, search for news published on {date} that explains the price movement.\n\n"
        f"Search strategy (follow this order):\n"
        f"1. Hard news: earnings, contracts, M&A, regulatory — Newsweb, Reuters, Bloomberg, FT\n"
        f"2. Analyst rating changes: search for «[company] nedgradering», «[company] oppgradering», "
        f"«[company] kursmål», «[company] downgrade/upgrade» on Finansavisen, E24, DN.no. "
        f"Nordic brokers (Pareto, DNB Markets, Arctic, ABG, Carnegie, SpareBank1 Markets) "
        f"are common catalysts for Nordic stocks.\n"
        f"3. Sector/macro: broad market moves, sector rotation, commodity prices\n\n"
        f"If a stock moved >4% and no hard catalyst is found, say so honestly. "
        f"Do not construct speculative explanations.\n\n"
        f"Return ONLY the JSON object, no other text."
    )


def _call_api(client, msgs):
    for attempt in range(5):
        try:
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[
                    {"type": "web_search_20250305", "name": "web_search"},
                ],
                messages=msgs,
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            wait = 60 * (attempt + 1)
            print(f"{type(e).__name__}, waiting {wait}s... (attempt {attempt + 1}/5)")
            time.sleep(wait)
    raise Exception("API call failed after 5 retries")


def _extract_json(response) -> dict:
    """Extract JSON from Claude's response, handling tool-use interleaving."""
    # Handle pause_turn
    text_parts = [block.text for block in response.content if block.type == "text"]

    for part in reversed(text_parts):
        text = part.strip()
        if "```" in text:
            parts = text.split("```")
            if "```json" in text:
                text = text.split("```json")[-1].split("```")[0]
            elif len(parts) >= 3:
                text = parts[1]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue

    all_text = "\n".join(text_parts)
    print(f"Could not parse JSON. Raw text:\n{all_text[:500]}")
    raise Exception("Claude did not return valid JSON")


def _analyze_market_batch(client, movers: list, date: str) -> dict:
    """Analyze a batch of movers for one market group."""
    batch_data = {
        "movers_count": len(movers),
        "threshold_pct": 2.0,
        "movers": movers,
    }
    messages = [{"role": "user", "content": build_prompt(batch_data)}]

    response = _call_api(client, messages)
    while response.stop_reason == "pause_turn":
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": "Continue."})
        response = _call_api(client, messages)

    return _extract_json(response)


def generate_report(movers_data: dict) -> dict:
    client = anthropic.Anthropic()
    movers = movers_data.get("movers", [])
    date = movers[0]["date"] if movers else ""

    # Split movers by market and process in separate API calls
    markets = {}
    for m in movers:
        market = m.get("market", "Other")
        markets.setdefault(market, []).append(m)

    all_movers = []
    summary = ""

    if not movers:
        return {"summary": "Ingen aksjer svingte mer enn 2% i dag.", "movers": []}

    market_order = ["Nordic", "Europe", "US"]
    remaining = [m for m in markets if m not in market_order]
    for market in market_order + remaining:
        batch = markets.get(market, [])
        if not batch:
            continue

        print(f"  Analyzing {market} ({len(batch)} movers)...")
        result = _analyze_market_batch(client, batch, date)

        if not summary and result.get("summary"):
            summary = result["summary"]
        all_movers.extend(result.get("movers", []))

        # Brief pause between batches to avoid rate limits
        time.sleep(5)

    return {"summary": summary, "movers": all_movers}


def save_report_to_gist(report: dict, date: str, gist_id: str, portfolio_id: str = "private"):
    """Read existing reports from gist, append new report, write back."""
    filename = f"reports_{portfolio_id}.json"
    existing = []

    # Try portfolio-specific file first, fall back to reports.json for private
    try:
        result = subprocess.run(
            ["gh", "gist", "view", gist_id, "--filename", filename],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            existing = json.loads(result.stdout)
        elif portfolio_id == "private":
            result = subprocess.run(
                ["gh", "gist", "view", gist_id, "--filename", "reports.json"],
                capture_output=True, text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                existing = json.loads(result.stdout)
    except (json.JSONDecodeError, Exception) as e:
        print(f"Could not read existing reports: {e}")

    if not isinstance(existing, list):
        print(f"Warning: gist data was not a list, resetting")
        existing = []

    # Remove existing report for same date (if re-running)
    existing = [r for r in existing if r.get("date") != date]

    # Add new report
    existing.append({
        "date": date,
        "report": report,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Sort newest first, keep last 90 days
    existing.sort(key=lambda r: r.get("date", ""), reverse=True)
    existing = existing[:90]

    # Write to gist via GitHub API (use temp file to avoid CLI arg length limits)
    content = json.dumps(existing, ensure_ascii=False, indent=2)
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        json.dump({"files": {filename: {"content": content}}}, tf, ensure_ascii=False)
        tf_path = tf.name
    try:
        subprocess.run(
            ["gh", "api", "--method", "PATCH", f"/gists/{gist_id}", "--input", tf_path],
            check=True,
            capture_output=True,
        )
    finally:
        os.unlink(tf_path)
    print(f"Report saved to gist ({filename}) for {date}")


def notify_app(api_url: str, api_secret: str, date: str, portfolio_name: str):
    """Tell the Railway app to send push notifications."""
    import requests
    try:
        resp = requests.post(
            f"{api_url}/api/push/notify",
            json={"title": f"{portfolio_name}-rapport", "body": f"Ny rapport for {date} er klar"},
            headers={"X-API-Key": api_secret},
            timeout=10,
        )
        resp.raise_for_status()
        print("Push notifications triggered")
    except Exception as e:
        print(f"Push notification failed (non-critical): {e}")


def main():
    import argparse
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from server.portfolios import PORTFOLIOS

    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio", default="private", choices=list(PORTFOLIOS.keys()))
    args = parser.parse_args()

    portfolio_id = args.portfolio
    portfolio_name = PORTFOLIOS[portfolio_id]["name"]

    movers_path = f"/tmp/movers_{portfolio_id}.json"
    if not os.path.exists(movers_path):
        print(f"No {movers_path} found. Run update_gist.py --portfolio {portfolio_id} first.")
        sys.exit(1)

    with open(movers_path) as f:
        movers_data = json.load(f)

    print(f"Generating {portfolio_name} report for {movers_data['movers_count']} movers...")
    report = generate_report(movers_data)
    date = movers_data["movers"][0]["date"] if movers_data.get("movers") else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(json.dumps(report, indent=2))

    gist_id = os.environ.get("GIST_ID")
    if not gist_id:
        print("\nNo GIST_ID set, skipping publish")
        return

    save_report_to_gist(report, date, gist_id, portfolio_id)

    # Trigger push notifications via the app
    api_url = os.environ.get("API_URL")
    api_secret = os.environ.get("API_SECRET")
    if api_url and api_secret:
        notify_app(api_url, api_secret, date, portfolio_name)


if __name__ == "__main__":
    main()
