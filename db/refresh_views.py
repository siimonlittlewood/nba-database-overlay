"""Refreshes materialized views after new data is loaded (bootstrap,
box-score backfill, play-by-play load, or a future nba_api sync). Not run
automatically by any of those commands -- run this as an explicit final
step, since a materialized view is a snapshot that goes stale the moment
new rows are inserted underneath it.
"""

from __future__ import annotations

import typer
from sqlalchemy import text

from db.session import engine

app = typer.Typer()


@app.callback()
def _callback() -> None:
    """Forces Typer to keep requiring an explicit subcommand name (see
    ingestion/sync/run_sync.py for why this is needed with one command)."""


@app.command()
def player_season_stats() -> None:
    """CONCURRENTLY avoids locking out readers during refresh -- requires
    the unique index created alongside the view (see the migration that
    added player_season_stats)."""
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY player_season_stats"))
    typer.echo("player_season_stats refreshed.")


if __name__ == "__main__":
    app()
