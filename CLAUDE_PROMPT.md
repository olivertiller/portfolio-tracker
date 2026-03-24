# Daily Portfolio News Summary

## Step 1: Get price data
Fetch the latest movers data from:
https://gist.githubusercontent.com/olivertiller/24236a25d105c46c64f122e4d60e12d6/raw/movers.json

This JSON is auto-updated every weekday after US market close via GitHub Actions using yfinance. The "date" field in each entry tells you which trading day the data is from.

## Step 2: Diagnose each mover
For each stock in the "movers" array (moved ±2 % or more), work through the following pipeline **in order**. Stop as soon as you find a probable explanation. The order is based on empirical variance decomposition of single-stock returns.

### Level 1 — Firm-specific news (~50-70 % of variance)
Search for company-specific events **published on that trading day**:
- Earnings releases, guidance changes, profit warnings
- M&A activity, contract wins/losses, product launches
- Management changes, regulatory rulings, lawsuits
- Insider transactions, share buybacks, dividend announcements

Search: "[company name] stock [date]" or "[ticker] news [date]"

### Level 2 — Analyst actions (frequent trigger when no firm news)
Look for:
- Rating upgrades / downgrades
- Price target changes
- Initiation or termination of coverage

Search: "[ticker] analyst upgrade downgrade [date]"

### Level 3 — Sector / peer-group move (~10-20 % of variance)
Check whether sector peers moved in the same direction:
- If the whole sector is up/down similarly → sector rotation, not firm-specific
- Identify the sector catalyst (regulatory change, commodity price, tariffs, earnings from a sector bellwether, etc.)

### Level 4 — Broad market / systematic risk (beta-driven)
Check index performance that day (S&P 500, OBX, STOXX 600):
- High-beta stocks (e.g. RIVN, VRT) amplify market moves
- If the stock moved roughly in line with beta × index move → market-driven

### Level 5 — Macro / monetary policy
Look for macro events that day:
- Central bank decisions (Fed, ECB, Norges Bank), rate expectations
- Inflation data (CPI, PPI), employment data (NFP, ADP)
- PMI, GDP, trade data, geopolitical developments

### Level 6 — Technical / flow factors (lower frequency, but real)
Consider if relevant:
- Options expiry (OPEX), index rebalancing
- Short squeeze, lock-up expiry
- ETF inflows/outflows, margin calls

## Step 3: Classify confidence
For each mover, label the explanation:
- **Bekreftet:** Direct firm-specific news found on that date
- **Sannsynlig årsak:** No direct news, but strong circumstantial evidence (analyst action, sector move, macro event)
- **Uklar:** No clear catalyst found at any level

## Step 4: Format the summary
Note the trading date at the top. Group by market: **US → Europe → Nordics**

Format each mover as:
**TICKER (±X.X%)** — [Bekreftet/Sannsynlig årsak/Uklar] 1-2 sentence explanation. Note which pipeline level the explanation comes from.

Example:
**VRT (+4.2%)** — [Bekreftet] Oppjustert kursmål fra Goldman Sachs til $135 (Level 2 — Analyst).
**NHY.OL (-2.8%)** — [Sannsynlig årsak] Aluminiumsprisen falt 1.8% på LME etter svake PMI-tall fra Kina. Hele materialsektoren var ned (Level 3/5 — Sektor + Makro).

If the "movers" array is empty, just say: "Rolig dag — ingen aksjer beveget seg mer enn ±2%."

## Sources
- US/European stocks: Reuters, Bloomberg, Financial Times, CNBC, Seeking Alpha
- Nordic stocks: Newsweb (Oslo Børs), E24, Finansavisen, DN.no
- Analyst actions: MarketBeat, TipRanks, Seeking Alpha
- Sector/index data: Yahoo Finance, Google Finance
- Macro calendar: Investing.com, ForexFactory

## Rules
- Only report news/events from the trading day in the JSON — never older news
- Keep it concise — max 2 sentences per stock
- Work through the pipeline in order — don't skip to macro if there's firm-specific news
- Always label confidence level and pipeline level
- Write the summary in Norwegian
