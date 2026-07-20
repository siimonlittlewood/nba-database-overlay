# NBA SQL + agentic analytics platform — project spec

## Purpose

Portfolio project to demonstrate strong SQL/PostgreSQL fundamentals, applied
data engineering, and an agentic LLM feature (text-to-SQL). Built as an
ongoing project, not a weekend hack — favor correctness and clean design
over speed.

**What this needs to prove:**
- Real relational schema design (normalization, keys, indexing decisions)
- Non-trivial SQL (window functions, CTEs, materialized views, query
  tuning with `EXPLAIN ANALYZE`)
- A working ETL pipeline against a messy, unofficial upstream API
- A Streamlit dashboard as the human-facing layer
- An agentic text-to-SQL assistant as the "ask the data a question" layer

---

## 1. Data sourcing

**Primary source:** [`nba_api`](https://github.com/swar/nba_api) — an
open-source Python client wrapping stats.nba.com's internal endpoints. No
API key required. Two relevant modules:
- `nba_api.stats.endpoints` — historical data: `playercareerstats`,
  `leaguegamefinder`, `boxscoretraditionalv2`, `playbyplayv2`,
  `leaguedashplayerstats`
- `nba_api.live.nba.endpoints` — same-day data: `scoreboard`, live box
  scores

**Bootstrap (historical backfill):** seed the database from the Kaggle
["NBA Database"](https://www.kaggle.com/datasets/wyattowalsh/basketball)
dataset (games back to 1946, itself sourced from stats.nba.com). Load via
Postgres `COPY` rather than row-by-row inserts — this is a good place to
demonstrate handling type coercion, duplicate handling, and constraint
violations during bulk load.

**Incremental sync:** scheduled job pulling new games/box scores via
`nba_api` going forward from the bootstrap cutoff date.

**Known constraint — design around this, don't ignore it:**
stats.nba.com is unofficial-client-unfriendly: it rate-limits, occasionally
blocks requests outright, and is particularly prone to blocking
datacenter/cloud IPs (i.e. a bare GitHub Actions runner or cheap cloud VM
may get blocked even at low request rates). Mitigations to build in:
- Custom request headers (User-Agent, Referer, Accept-Language) mimicking
  a browser — see `nba_api` docs for the pattern
- Deliberate delay between calls (~600ms+)
- Retry with exponential backoff
- Idempotent ingestion (safe to re-run without duplicating rows)
- Document this constraint explicitly in the README as a design decision,
  not a bug

---

## 2. Schema design (starting point — refine during implementation)

Core tables:

```sql
CREATE TABLE teams (
    team_id     INTEGER PRIMARY KEY,   -- nba.com team id
    abbreviation TEXT NOT NULL,
    city        TEXT NOT NULL,
    name        TEXT NOT NULL,
    conference  TEXT,
    division    TEXT
);

CREATE TABLE players (
    player_id   INTEGER PRIMARY KEY,   -- nba.com player id
    full_name   TEXT NOT NULL,
    birthdate   DATE,
    height_in   SMALLINT,
    weight_lb   SMALLINT,
    draft_year  SMALLINT
);

CREATE TABLE seasons (
    season_id   TEXT PRIMARY KEY,      -- e.g. '2025-26'
    start_date  DATE,
    end_date    DATE
);

CREATE TABLE games (
    game_id     TEXT PRIMARY KEY,      -- nba.com game id
    season_id   TEXT REFERENCES seasons(season_id),
    game_date   DATE NOT NULL,
    home_team_id INTEGER REFERENCES teams(team_id),
    away_team_id INTEGER REFERENCES teams(team_id),
    home_score  SMALLINT,
    away_score  SMALLINT
);

CREATE TABLE player_game_stats (
    game_id     TEXT REFERENCES games(game_id),
    player_id   INTEGER REFERENCES players(player_id),
    team_id     INTEGER REFERENCES teams(team_id),
    minutes     NUMERIC(4,1),
    points      SMALLINT,
    rebounds    SMALLINT,
    assists     SMALLINT,
    steals      SMALLINT,
    blocks      SMALLINT,
    turnovers   SMALLINT,
    fg_made     SMALLINT,
    fg_attempted SMALLINT,
    fg3_made    SMALLINT,
    fg3_attempted SMALLINT,
    ft_made     SMALLINT,
    ft_attempted SMALLINT,
    PRIMARY KEY (game_id, player_id)
);

CREATE TABLE team_game_stats (
    game_id     TEXT REFERENCES games(game_id),
    team_id     INTEGER REFERENCES teams(team_id),
    points      SMALLINT,
    rebounds    SMALLINT,
    assists     SMALLINT,
    turnovers   SMALLINT,
    PRIMARY KEY (game_id, team_id)
);

-- Stretch: play_by_play, partitioned by season once it's large
```

**Indexing / design decisions to make deliberately (and be able to defend):**
- `player_game_stats(player_id, game_id)` composite index to support
  rolling-average window queries ordered by game date
- A materialized view for season averages per player (`REFRESH` on a
  schedule after ingestion, not computed live)
- Surrogate vs. natural keys — nba.com IDs are stable enough to use
  directly as primary keys; document why
- Partitioning strategy for `play_by_play` if/when it's added (by season)

**Migrations:** use Alembic from the start rather than hand-editing the
schema — signals awareness of schema evolution, not just a one-off script.

---

## 3. Tech stack

| Layer | Choice |
|---|---|
| Database | PostgreSQL (Docker Compose locally; Neon or Supabase free tier for hosted demo) |
| ORM / DB access | SQLAlchemy or raw `psycopg` |
| Migrations | Alembic |
| Ingestion | Python (`requests`/`nba_api`, `pandas` for cleaning) |
| Scheduling | GitHub Actions cron (simple) or Prefect (more resume weight) — see IP-blocking constraint above when choosing where this actually runs |
| Dashboard | Streamlit + Plotly/Altair |
| Testing | pytest for ETL logic and query correctness |
| CI | GitHub Actions running lint + tests |
| Agent | Custom tool-use loop against Claude/OpenAI API (see below) |

---

## 4. Text-to-SQL agent

Build the agent loop yourself rather than reaching for a framework —
more resume-worthy and not much harder.

**Tools exposed to the model:**
1. `get_schema()` — returns table/column definitions (from
   `information_schema` or a maintained schema doc)
2. `run_query(sql)` — executes against Postgres using a **dedicated
   read-only role**, with a statement timeout and a hard row limit

**Safety requirements (non-negotiable, not optional polish):**
- DB role for this tool has `SELECT`-only grants — no `INSERT`/`UPDATE`/
  `DELETE`/DDL permissions at the database level, not just app-level checks
- Reject any query that isn't a single `SELECT` before execution — parse
  with `sqlglot` or an equivalent, don't just trust the model's output
- `statement_timeout` set on the connection/role
- Row limit enforced (e.g. `LIMIT 200` injected if absent)

**Loop:**
1. User asks a question in plain English
2. Model calls `get_schema` if needed
3. Model writes SQL, calls `run_query`
4. On error, model sees the error and retries (this self-correction step
   is the actual "agentic" part worth highlighting on a resume/in
   interviews)
5. Model synthesizes a natural-language answer from the result set
6. Surface the SQL it ran in the UI so the answer is verifiable, not a
   black box

---

## 5. Phased roadmap

1. **Bootstrap** — schema (with Alembic migrations) + historical backfill
   from the Kaggle dataset via `COPY`
2. **Dashboard** — Streamlit on top of the bootstrapped data: filters,
   player/team comparisons, trend charts
3. **Incremental sync** — scheduled `nba_api` ingestion job with
   retry/backoff, extending the dataset forward from the bootstrap cutoff
4. **Text-to-SQL agent** — the loop described above, safety constraints
   included from day one, not bolted on after
5. **Polish** — tests, CI, migrations finalized, deployed demo (Streamlit
   Community Cloud + hosted Postgres), README documenting the schema,
   architecture, and the stats.nba.com reliability constraint
6. **Stretch (later)** — pgvector extension for embedding game
   recaps/injury news, extending the agent into hybrid RAG (structured +
   unstructured retrieval); optional predictive ML layer (win probability
   or player projections)

---

## 6. Deployment target

Get something demoable early (by end of phase 2, not phase 5):
- Streamlit Community Cloud for the app
- Neon or Supabase free tier for hosted Postgres
- A live link is far stronger on a resume than a repo alone

---

## 7. Open questions for implementation

- Exact set of `player_game_stats` columns (how wide vs. how normalized —
  decide and document the tradeoff)
- Where the scheduled ingestion job actually runs, given the datacenter-IP
  blocking risk
- Whether to expose the agent through Streamlit directly or behind a
  small FastAPI layer (the latter adds API-design scope if there's time
  for it)
