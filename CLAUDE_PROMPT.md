# Daily Portfolio News Summary

## Step 1: Get price data
Fetch the latest movers data from:
https://gist.githubusercontent.com/olivertiller/24236a25d105c46c64f122e4d60e12d6/raw/movers.json

This JSON is auto-updated every weekday after US market close via GitHub Actions using yfinance.

## Step 2: Analyze movers
For each stock in the "movers" array (moved ±2% or more), search for relevant news explaining the move. Use credible sources:
- US/European stocks: Reuters, Bloomberg, Financial Times
- Nordic stocks: Newsweb (Oslo Børs), E24, Finansavisen, DN.no

## Step 3: Format the summary
Group by market: **US → Europe → Nordics**

Format each mover as:
**TICKER (±X.X%)** — 1-2 sentence explanation of the move.

If the "movers" array is empty, just say: "Rolig dag — ingen aksjer beveget seg mer enn ±2%."

## Rules
- Skip stocks that did not move significantly (they are already filtered out)
- Keep it concise — max 2 sentences per stock
- Always note the date from the JSON response
- If you cannot find a clear news catalyst, say "ingen tydelig nyhetskatalysator funnet"
