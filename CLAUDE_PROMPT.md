# Daily Portfolio News Summary

## Step 1: Get price data
Fetch the latest movers data from:
https://gist.githubusercontent.com/olivertiller/24236a25d105c46c64f122e4d60e12d6/raw/movers.json

This JSON is auto-updated every weekday after US market close via GitHub Actions using yfinance. The "date" field in each entry tells you which trading day the data is from.

## Step 2: Find intraday news for each mover
For each stock in the "movers" array (moved ±2% or more), search for news published **on that specific trading day only**. Do not include news from previous days or weeks.

Search strategy:
- Search for "[company name] stock [date]" or "[ticker] news [date]"
- Credible sources for US/European stocks: Reuters, Bloomberg, Financial Times, CNBC
- Credible sources for Nordic stocks: Newsweb (Oslo Børs), E24, Finansavisen, DN.no

## Step 3: Classify and report
For each mover, follow this logic:
1. **Intraday news found?** Report the specific catalyst (earnings, guidance, analyst upgrade/downgrade, deal, macro event, etc.)
2. **No intraday news found?** State the most likely cause based on sector moves, index correlation, or broader market trends that day. Clearly label this as "Sannsynlig årsak:" to distinguish it from confirmed news.

## Step 4: Format the summary
Note the trading date at the top. Group by market: **US → Europe → Nordics**

Format each mover as:
**TICKER (±X.X%)** — 1-2 sentence explanation.

If the "movers" array is empty, just say: "Rolig dag — ingen aksjer beveget seg mer enn ±2%."

## Rules
- Only report news from the trading day in the JSON — never older news
- Keep it concise — max 2 sentences per stock
- Always distinguish between confirmed news and inferred causes
