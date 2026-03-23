# Daily Portfolio News Summary

## Portfolio
```
AMZN     Amazon                          US
BRK-B    Berkshire Hathaway B            US
META     Meta Platforms                  US
MSFT     Microsoft                       US
NVT      nVent Electric                  US
RCL      Royal Caribbean Cruises         US
RIVN     Rivian Automotive               US
VRT      Vertiv Holdings                 US
OR.PA    L'Oréal                         Europe
MC.PA    LVMH                            Europe
BMW.DE   BMW                             Europe
ENR.DE   Siemens Energy                  Europe
AKER.OL  Aker                            Nordic
GJF.OL   Gjensidige Forsikring           Nordic
KCC.OL   Klaveness Combination Carriers  Nordic
KID.OL   KID                             Nordic
KIT.OL   Kitron                          Nordic
KOMPL.OL Komplett                        Nordic
KOG.OL   Kongsberg Gruppen               Nordic
NORBT.OL NORBIT                          Nordic
NOD.OL   Nordic Semiconductor            Nordic
NHY.OL   Norsk Hydro                     Nordic
PARB.OL  Pareto Bank                     Nordic
SALM.OL  SalMar                          Nordic
TEL.OL   Telenor                         Nordic
VEND.OL  Vend Marketplaces               Nordic
```

## Step 1: Get price data
For each ticker above, fetch the last 5 days of closing prices from Yahoo Finance's public API:
`https://query1.finance.yahoo.com/v8/finance/chart/TICKER?range=5d&interval=1d`

Replace `TICKER` with each symbol (e.g. `AMZN`, `BRK-B`, `OR.PA`, `AKER.OL`).

From the JSON response, use the `indicators.quote[0].close` array — take the last two non-null values as `last_close` and `prev_close`. Calculate: `change_pct = ((last_close - prev_close) / prev_close) * 100`. Stocks with `abs(change_pct) >= 2.0` are "movers".

## Step 2: Analyze movers
For each mover (±2% or more), search for relevant news explaining the move. Use credible sources:
- US/European stocks: Reuters, Bloomberg, Financial Times
- Nordic stocks: Newsweb (Oslo Børs), E24, Finansavisen, DN.no

## Step 3: Format the summary
Group by market: **US → Europe → Nordics**

Format each mover as:
**TICKER (±X.X%)** — 1-2 sentence explanation of the move.

If there are no movers, just say: "Rolig dag — ingen aksjer beveget seg mer enn ±2%."

## Rules
- Skip stocks that did not move significantly
- Keep it concise — max 2 sentences per stock
- If you cannot find a clear news catalyst, say "ingen tydelig nyhetskatalysator funnet"
