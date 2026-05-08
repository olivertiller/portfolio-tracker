# TODO

Oppgaver og ideer for portfolio-tracker.

## Bugs / robusthet

- [ ] `unsubscribe` i `server/main.py:457` antar `s["endpoint"]` finnes — KeyError for APNs-abonnementer som kun har `token`. Bruk `s.get("endpoint")`.
- [ ] `_send_push_notifications` returnerer `True` på transiente APNs-feil (`server/main.py:222`), men kommentaren sier "don't remove token". Avklar at logikken matcher intensjonen.
- [ ] `get_daily_changes` filtrerer ut "stale" tickers basert på flertall — kan gi rar oppførsel når halve markedet er stengt. Vurder per-marked-gruppering.
- [ ] CORS er åpen for alle origins (`allow_origins=["*"]`). Lås ned til kjente domener i prod.

## Funksjoner

- [ ] Notater per ticker i frontend (lagret i `localStorage`, eller i Gist for sync).
- [ ] Historisk graf for hele porteføljen, ikke bare per aksje.
- [ ] Eksport av rapport til CSV/PDF.
- [ ] Varsling kun ved bevegelser over en konfigurerbar terskel (per bruker).

## Tester

- [ ] Ingen tester finnes ennå (`npm test` returnerer feil). Legg til pytest for `server/` og minst smoke-test av `/health`, `/api/portfolio`, `/api/movers`.
- [ ] Mock `yfinance` slik at testene ikke trenger nettverk.

## DevEx / opprydding

- [ ] `package.json` lister Capacitor-avhengigheter, men selve appen er FastAPI + statisk frontend. Avklar om iOS-wrapperen fortsatt er aktiv eller kan fjernes.
- [ ] `requirements.txt` mangler pinning av versjoner — låst miljø vil gi mer forutsigbare deploys.
- [ ] Flytt hardkodet `GIST_ID` (`server/main.py:36`) til ren env-variabel uten default.
- [ ] `CLAUDE_PROMPT.md` bør refereres fra README, eller flyttes til `docs/`.

## Dokumentasjon

- [ ] README beskriver kun `/portfolio` og `/movers` — legg til `/api/report*`, `/api/sparklines` og push-endepunktene.
- [ ] Dokumenter hvilke env-variabler som må settes (`API_SECRET`, `GH_TOKEN`/`GIST_TOKEN`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIMS`).
