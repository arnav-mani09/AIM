# Stats ingestion workflow

Endpoint: `POST /api/v1/ingest/possessions`

Fields:
- `matchup` – e.g., `Valley vs Central`
- `scheduled_at` – ISO timestamp (e.g., `2025-11-26T19:00:00`)
- `file` – CSV with columns: `player`, `jersey`, `team`, `label`, `outcome`

Each row becomes a possession and auto-creates players/teams as needed.
