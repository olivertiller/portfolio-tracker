# Daily Portfolio News Summary

## Step 1: Get price data
Fetch my portfolio data from: web-production-96969.up.railway.app/movers?threshold=2

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
