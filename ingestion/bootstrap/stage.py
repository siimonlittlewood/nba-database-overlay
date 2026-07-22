from __future__ import annotations

import io

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

STAGING_SCHEMA = "staging"

# Staging tables mirror the cleaned DataFrames' shape (already
# type-coerced/parsed by clean.py) -- still keyed by nba.com ids, since
# surrogate FK resolution happens later in load.py via joins against the
# already-loaded dimension tables.
_STAGING_DDL: dict[str, str] = {
    "teams": """
        nba_team_id INTEGER,
        abbreviation TEXT,
        city TEXT,
        name TEXT,
        conference TEXT,
        division TEXT
    """,
    "players": """
        nba_player_id INTEGER,
        full_name TEXT,
        birthdate DATE,
        height_in INTEGER,
        weight_lb INTEGER,
        draft_year INTEGER
    """,
    "seasons": """
        season_label TEXT,
        start_date DATE,
        end_date DATE
    """,
    "games": """
        nba_game_id TEXT,
        game_date DATE,
        game_type TEXT,
        home_nba_team_id INTEGER,
        away_nba_team_id INTEGER,
        home_score INTEGER,
        away_score INTEGER,
        season_label TEXT
    """,
    "team_game_stats": """
        nba_game_id TEXT,
        nba_team_id INTEGER,
        rebounds INTEGER,
        assists INTEGER,
        turnovers INTEGER,
        points INTEGER
    """,
    "player_game_stats": """
        nba_game_id TEXT,
        nba_player_id INTEGER,
        nba_team_id INTEGER,
        minutes NUMERIC(4,1),
        points INTEGER,
        rebounds INTEGER,
        assists INTEGER,
        steals INTEGER,
        blocks INTEGER,
        turnovers INTEGER,
        fg_made INTEGER,
        fg_attempted INTEGER,
        fg3_made INTEGER,
        fg3_attempted INTEGER,
        ft_made INTEGER,
        ft_attempted INTEGER
    """,
    "play_by_play": """
        nba_game_id TEXT,
        sequence INTEGER,
        period SMALLINT,
        clock TEXT,
        event_type TEXT,
        sub_type TEXT,
        description TEXT,
        nba_player_id INTEGER,
        nba_player2_id INTEGER,
        nba_player3_id INTEGER,
        nba_team_id INTEGER,
        score_home INTEGER,
        score_away INTEGER,
        shot_x NUMERIC(6,2),
        shot_y NUMERIC(6,2),
        shot_distance INTEGER,
        shot_made BOOLEAN
    """,
}


def create_staging_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {STAGING_SCHEMA}"))


def drop_staging_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {STAGING_SCHEMA} CASCADE"))


def copy_dataframe_to_staging(engine: Engine, df: pd.DataFrame, table_name: str) -> int:
    """Bulk-loads a cleaned DataFrame into staging.<table_name> via Postgres
    COPY (not row-by-row inserts). Recreates the staging table each call so
    the whole bootstrap is safely re-runnable from scratch."""
    qualified = f"{STAGING_SCHEMA}.{table_name}"

    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {qualified}")
        cursor.execute(f"CREATE TABLE {qualified} ({_STAGING_DDL[table_name]})")

        buffer = io.StringIO()
        df.to_csv(buffer, index=False, header=False, na_rep="")
        buffer.seek(0)

        columns = ", ".join(df.columns)
        copy_sql = f"COPY {qualified} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '')"
        with cursor.copy(copy_sql) as copy:
            copy.write(buffer.read())

        raw_conn.commit()
        return len(df)
    finally:
        raw_conn.close()
