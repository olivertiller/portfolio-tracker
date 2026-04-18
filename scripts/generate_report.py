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
- When you find confirmed news: set confirmed=true, cite the source
- When no confirmed news: set confirmed=false, give the most plausible driver (sector trends, macro spillover, peer moves)
- When nothing plausible: "No confirmed catalyst. Likely followed the broad market rally."
- Macro/sector context IS useful when it explains the move
- Max 1-2 sentences per stock

Order movers by market: Nordic first, then Europe, then US."""


def build_prompt(movers_data: dict) -> str:
    if movers_data["movers_count"] == 0:
        return 'No movers today. Return: {"summary": "Quiet day — no stocks moved more than ±2%.", "movers": []}'

    movers_json = json.dumps(movers_data["movers"], indent=2)
    date = movers_data["movers"][0]["date"]

    return (
        f"Trading date: {date}\n"
        f"Movers (±{movers_data['threshold_pct']}% or more):\n\n"
        f"{movers_json}\n\n"
        f"For each mover, search for news published on {date} that explains the price movement. "
        f"Use credible sources: Reuters, Bloomberg, FT for US/Europe. "
        f"Newsweb (Oslo Børs), E24, Finansavisen, DN.no for Nordic stocks.\n\n"
        f"Return ONLY the JSON object, no other text."
    )


def generate_report(movers_data: dict) -> dict:
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

    # Extract text from response — try all text blocks, find the one with JSON
    text_parts = [block.text for block in response.content if block.type == "text"]

    for part in reversed(text_parts):  # JSON is usually in the last text block
        text = part.strip()
        # Handle markdown code blocks
        if "```" in text:
            text = text.split("```json")[-1].split("```")[-2] if "```json" in text else text.split("```")[1]
            text = text.strip()
        # Try to find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue

    # Fallback: dump raw text for debugging
    all_text = "\n".join(text_parts)
    print(f"Could not parse JSON from response. Raw text:\n{all_text[:500]}")
    raise Exception("Claude did not return valid JSON")


def save_report_to_gist(report: dict, date: str, gist_id: str):
    """Read existing reports from gist, append new report, write back."""
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
        "report": report,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Sort newest first, keep last 90 days
    existing.sort(key=lambda r: r["date"], reverse=True)
    existing = existing[:90]

    # Write to gist via GitHub API
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
    date = movers_data["movers"][0]["date"] if movers_data["movers"] else datetime.now().strftime("%Y-%m-%d")

    print(json.dumps(report, indent=2))

    gist_id = os.environ.get("GIST_ID")
    if not gist_id:
        print("\nNo GIST_ID set, skipping publish")
        return

    save_report_to_gist(report, date, gist_id)

    # Trigger push notifications via the app
    api_url = os.environ.get("API_URL")
    api_secret = os.environ.get("API_SECRET")
    if api_url and api_secret:
        notify_app(api_url, api_secret, date)


if __name__ == "__main__":
    main()
