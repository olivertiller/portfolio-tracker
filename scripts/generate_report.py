"""Generate a daily portfolio report using Claude API and send via ntfy."""

import json
import os
import sys

import anthropic
import requests

SYSTEM_PROMPT = """You are a concise financial news analyst. You write in English.
You receive portfolio movers data (stocks that moved ±2% intraday) and must explain each move.

Rules:
- Only report news from the specific trading day in the data — never older news
- Group by market in this order: Nordics -> Europe -> US
- Format each mover like this:
  - Positive move: **Company Name** (🟢 +X.X%) — explanation
  - Negative move: **Company Name** (🔴 -X.X%) — explanation
- Use the full company name from the data, not just the ticker
- If you find confirmed intraday news, report the catalyst
- If no intraday news found, state the most likely cause and label it "Likely cause:"
- If no movers, just say: "Quiet day — no stocks moved more than ±2%."
- Keep it concise — max 1-2 sentences per stock, aim for under 3500 characters total
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

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[
            {"type": "web_search_20250305", "name": "web_search"},
        ],
        messages=messages,
    )

    # Handle pause_turn (server-side tool loop hit iteration limit)
    while response.stop_reason == "pause_turn":
        messages = [
            {"role": "user", "content": build_prompt(movers_data)},
            {"role": "assistant", "content": response.content},
        ]
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[
                {"type": "web_search_20250305", "name": "web_search"},
            ],
            messages=messages,
        )

    # Extract text from response
    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts)


def send_ntfy(report: str, topic: str):
    # ntfy limit is 4096 bytes; truncate if needed to avoid silent attachment conversion
    max_bytes = 4000  # leave headroom for JSON envelope
    encoded = report.encode("utf-8")
    if len(encoded) > max_bytes:
        report = encoded[:max_bytes].decode("utf-8", errors="ignore").rsplit("\n", 1)[0]
        report += "\n\n_(truncated)_"

    resp = requests.post(
        "https://ntfy.sh/",
        json={
            "topic": topic,
            "title": "Daily Portfolio Report",
            "tags": ["chart_with_upwards_trend"],
            "markdown": True,
            "message": report,
        },
    )
    resp.raise_for_status()


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

    ntfy_topic = os.environ.get("NTFY_TOPIC")
    if ntfy_topic:
        send_ntfy(report, ntfy_topic)
        print(f"\nReport sent to ntfy topic: {ntfy_topic}")
    else:
        print("\nNo NTFY_TOPIC set, skipping notification")


if __name__ == "__main__":
    main()
