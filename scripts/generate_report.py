"""Generate a daily portfolio report using Claude API and save to GitHub Gist."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import anthropic

SYSTEM_PROMPT = """You are a concise financial news analyst. You write in English.
You receive portfolio movers data (stocks that moved ±2% intraday) and must explain each move.

Rules:
- Only report news from the specific trading day in the data — never older news
- Group by market in this order: Nordics -> Europe -> US
- Start with 1-2 sentences of macro context for the day (index moves, key events)
- Format each mover as a plain paragraph (NOT a bullet list):
  **Company Name** (+X.X%) — explanation
- Use the full company name from the data, not just the ticker

Explanation guidelines:
- Focus on WHY the stock moved — the catalyst, not what the company does
- Never include general company descriptions (sector, history, name changes, etc.)
- When confirmed news exists: state the catalyst and source in 1-2 sentences
- When no confirmed news: write "Likely cause:" followed by the most plausible driver — sector trends, macro spillover, or relevant peer moves are good here
- When nothing plausible: write "No confirmed catalyst." plus brief market context if relevant (e.g. "Likely followed the broad market rally.")
- Macro/sector context IS useful when it explains the move — just don't pad with background info about the company itself
- If no movers at all, just say: "Quiet day — no stocks moved more than ±2%."
- Keep it concise — max 1-2 sentences per stock
- Start with the trading date as a header"""


def build_prompt(movers_data: dict) -> str:
    if movers_data["movers_count"] == 0:
        return "No movers today. Respond accordingly."

    movers_json = json.dumps(movers_data["movers"], indent=2)
    date = movers_data["movers"][0]["date"]

    return (
        f"Trading date: {date}\n"
        f"Movers (±{movers_data['threshold_pct']}% or more):\n\n"
        f"{movers_json}\n\n"
        f"For each mover, search for news published on {date} that explains the price movement. "
        f"Use credible sources: Reuters, Bloomberg, FT for US/Europe. "
        f"Newsweb (Oslo Børs), E24, Finansavisen, DN.no for Nordic stocks."
    )


def generate_report(movers_data: dict) -> str:
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": build_prompt(movers_data)}]

    def _call_api(msgs):
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
            except anthropic.RateLimitError:
                wait = 60 * (attempt + 1)
                print(f"Rate limited, waiting {wait}s... (attempt {attempt + 1}/5)")
                time.sleep(wait)
        raise Exception("Rate limit exceeded after 5 retries")

    response = _call_api(messages)

    # Handle pause_turn (server-side tool loop hit iteration limit)
    while response.stop_reason == "pause_turn":
        messages = [
            {"role": "user", "content": build_prompt(movers_data)},
            {"role": "assistant", "content": response.content},
        ]
        response = _call_api(messages)

    # Extract text from response
    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts)


def extract_date(report: str) -> str:
    """Extract date from report header, fallback to movers data."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", report)
    if match:
        return match.group(1)
    return ""


def save_report_to_gist(report: str, date: str, gist_id: str):
    """Read existing reports from gist, append new report, write back."""
    # Read existing reports.json from gist
    existing = []
    try:
        result = subprocess.run(
            ["gh", "gist", "view", gist_id, "--filename", "reports.json"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            existing = json.loads(result.stdout)
    except (json.JSONDecodeError, Exception) as e:
        print(f"Could not read existing reports: {e}")

    # Remove existing report for same date (if re-running)
    existing = [r for r in existing if r["date"] != date]

    # Add new report
    existing.append({
        "date": date,
        "content": report,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Sort newest first, keep last 90 days
    existing.sort(key=lambda r: r["date"], reverse=True)
    existing = existing[:90]

    # Write to gist via GitHub API (supports both creating and updating files)
    content = json.dumps(existing, ensure_ascii=False, indent=2)
    subprocess.run(
        [
            "gh", "api", "--method", "PATCH", f"/gists/{gist_id}",
            "-f", f"files[reports.json][content]={content}",
        ],
        check=True,
        capture_output=True,
    )
    print(f"Report saved to gist for {date}")


def notify_app(api_url: str, api_secret: str, date: str):
    """Tell the Railway app to send push notifications."""
    import requests
    try:
        resp = requests.post(
            f"{api_url}/api/push/notify",
            json={"title": "Porteføljerapport", "body": f"Ny rapport for {date} er klar"},
            headers={"X-API-Key": api_secret},
            timeout=10,
        )
        resp.raise_for_status()
        print("Push notifications triggered")
    except Exception as e:
        print(f"Push notification failed (non-critical): {e}")


def main():
    movers_path = "/tmp/movers.json"
    if not os.path.exists(movers_path):
        print("No movers.json found. Run update_gist.py first.")
        sys.exit(1)

    with open(movers_path) as f:
        movers_data = json.load(f)

    print(f"Generating report for {movers_data['movers_count']} movers...")
    report = generate_report(movers_data)
    print(report)

    gist_id = os.environ.get("GIST_ID")
    if not gist_id:
        print("\nNo GIST_ID set, skipping publish")
        return

    date = extract_date(report)
    if not date and movers_data["movers"]:
        date = movers_data["movers"][0]["date"]

    save_report_to_gist(report, date, gist_id)

    # Trigger push notifications via the app
    api_url = os.environ.get("API_URL")
    api_secret = os.environ.get("API_SECRET")
    if api_url and api_secret:
        notify_app(api_url, api_secret, date)


if __name__ == "__main__":
    main()
