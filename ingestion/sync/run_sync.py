"""Phase 3: nba_api sync -- keeps games/team_game_stats/player_game_stats
current going forward, past the eoinamoore Kaggle dataset's export cutoff.

DOES NOT WORK FROM THIS SANDBOX. Confirmed: stats.nba.com and cdn.nba.com
both sit behind an Akamai WAF that blocks this sandbox's outbound IP --
TCP/TLS connects instantly, but stats.nba.com never sends an HTTP response
(silent tarpit) and cdn.nba.com returns an explicit 403 "Access Denied"
from errors.edgesuite.net. nba_api's own actively-maintained default
headers (realistic Chrome UA, Referer, Sec-Ch-Ua, etc.) didn't help,
which points to IP-reputation or TLS-fingerprint-level blocking, not a
header-completeness gap -- not something request pacing or better headers
can fix. Run this from a network where stats.nba.com isn't blocked (a
home/residential connection is the most likely to just work).

Every column mapping and endpoint call here was written against nba_api's
own installed source (endpoint signatures in stats/endpoints/*.py, response
field lists in stats/endpoints/_parsers/*.py and each endpoint's
expected_data), not a live response -- verify the flagged assumptions
(see column_maps.py) on first real run:
- BoxScoreTraditionalV3's "minutes" format (MM:SS vs ISO-8601 duration)
- SEASON_ID type codes 3 (All-Star) and 5 (Play-In)
If sync_recent_games loads 0 player rows despite staging > 0, check
clean.parse_box_v3_minutes first -- that's the most likely culprit.
"""

from __future__ import annotations

from datetime import date, timedelta

import typer
from sqlalchemy import text

from db.session import engine
from ingestion.bootstrap import load, stage
from ingestion.bootstrap.clean import clean_seasons
from ingestion.sync import clean, extract

app = typer.Typer()


@app.callback()
def _callback() -> None:
    """Forces Typer to keep requiring an explicit subcommand name (e.g.
    `sync-recent-games`) even though there's currently only one command --
    without this, Typer collapses a single-command app so the command
    name itself is rejected as an unexpected extra argument."""


def _report(table: str, staged: int, inserted: int) -> None:
    typer.echo(f"{table}: staged={staged} inserted={inserted} skipped={staged - inserted}")


@app.command()
def sync_recent_games(
    since: str = typer.Option(None, help="YYYY-MM-DD; defaults to the day after MAX(games.game_date)"),
    until: str = typer.Option(None, help="YYYY-MM-DD; defaults to today"),
    request_delay: float = typer.Option(1.2, help="Seconds to sleep between per-game box score requests"),
    keep_staging: bool = typer.Option(False, help="Don't drop the staging schema after loading"),
) -> None:
    """Pulls games/team stats/player box scores for [since, until] and
    loads them via the same staging + ON CONFLICT DO NOTHING pattern as
    the bootstrap pipeline -- safe to re-run (e.g. daily during the
    season); already-loaded games are just skipped."""
    with engine.connect() as conn:
        existing_game_ids = set(conn.execute(text("SELECT nba_game_id FROM games")).scalars().all())
        if since is None:
            max_date = conn.execute(text("SELECT MAX(game_date) FROM games")).scalar_one()
            since = (max_date + timedelta(days=1)).isoformat()
    until = until or date.today().isoformat()

    typer.echo(f"Fetching games from {since} to {until}...")
    raw_games = extract.fetch_games_since(since, until)
    if raw_games.empty:
        typer.echo("No games found in range -- nothing to sync.")
        return

    stage.create_staging_schema(engine)

    games_df = clean.clean_games_from_gamefinder(raw_games)
    seasons_df = clean_seasons(games_df)
    stage.copy_dataframe_to_staging(engine, seasons_df, "seasons")
    _report("seasons", *load.load_seasons_widen(engine))

    stage.copy_dataframe_to_staging(engine, games_df, "games")
    _report("games", *load.load_games(engine))

    tgs_df = clean.clean_team_game_stats_from_gamefinder(raw_games)
    stage.copy_dataframe_to_staging(engine, tgs_df, "team_game_stats")
    _report("team_game_stats", *load.load_team_game_stats(engine))

    new_game_ids = sorted(set(games_df["nba_game_id"]) - existing_game_ids)
    typer.echo(f"Fetching player box scores for {len(new_game_ids)} new games (~{request_delay}s apart)...")
    raw_box = extract.fetch_player_box_scores(new_game_ids, request_delay_seconds=request_delay)
    if not raw_box.empty:
        player_df = clean.clean_player_game_stats_from_boxscore(raw_box)
        stage.copy_dataframe_to_staging(engine, player_df, "player_game_stats")
        _report("player_game_stats", *load.load_player_game_stats(engine))
    else:
        typer.echo("player_game_stats: no new games to fetch box scores for")

    if not keep_staging:
        stage.drop_staging_schema(engine)


if __name__ == "__main__":
    app()
