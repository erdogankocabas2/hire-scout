# Hire Scout

Personal job-hunt agent for **GTM / Product / Business Development** roles in **Turkey**.

It runs on a schedule (default 07:00 local), searches the public web (Tavily), extracts companies + hiring signals + people with ChatGPT, enriches emails via Hunter, and stores everything in a local dashboard pipeline.

## Quick start

```bash
cd ~/Projects/hire-scout
cp .env.example .env   # if needed — keys already set locally
chmod +x run.sh
./run.sh
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Click **Run scout now** for a first pass (a few minutes). Nightly runs continue automatically while the server is up.

## Required API keys (`.env`)

| Key | Purpose |
|---|---|
| `TAVILY_API_KEY` | Web research |
| `OPENAI_API_KEY` | Structured extraction (gpt-4o-mini) |
| `HUNTER_API_KEY` | Domain email / people enrichment |

Also configurable:

- `SCOUT_GEO` (default `Turkey`)
- `SCOUT_ROLE_FAMILIES` (default `gtm,product,bd`)
- `SCOUT_CRON_HOUR` / `SCOUT_CRON_MINUTE`
- `SCOUT_MAX_COMPANIES_PER_RUN`

## Dashboard

- **Pipeline** — move companies through `new → … → interview → offer`
- **Companies** — hiring signals, careers links
- **People** — cofounders, HR, GTM/Product/BD contacts + emails
- **Scout** — schedule info + recent run stats

## Notes

- Single-user local app; SQLite DB lives in `data/hire_scout.db`
- No LinkedIn scraping; no auto-send outreach in v1
- Keep `.env` out of git (already gitignored)
- If you pasted keys into chat, rotate them in each provider console
