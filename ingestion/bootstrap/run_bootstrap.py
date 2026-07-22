from __future__ import annotations

from pathlib import Path

import typer
from sqlalchemy import text

from db.session import engine
from ingestion.bootstrap import clean, extract, load, stage

app = typer.Typer()


def _report(table: str, staged: int, inserted: int) -> None:
    # "skipped" covers two distinct cases we don't distinguish here: rows
    # already loaded by a prior run (ON CONFLICT DO NOTHING -- expected,
    # makes reruns idempotent) and rows whose FK couldn't be resolved (an
    # inner join drops them -- would indicate a real data-quality issue).
    typer.echo(f"{table}: staged={staged} inserted={inserted} skipped={staged - inserted}")


@app.command()
def main(
    data_dir: Path = typer.Option(Path("data/kaggle"), help="Directory containing the Kaggle csv/ export"),
    keep_staging: bool = typer.Option(False, help="Don't drop the staging schema after loading"),
) -> None:
    """Bootstraps teams/players/seasons/games/team_game_stats from the
    Kaggle "wyattowalsh/basketball" csv/ export. player_game_stats is
    intentionally left empty -- this dataset has no per-player-per-game
    box scores; Phase 3's nba_api sync populates it going forward.

    Load order matters: teams and seasons must exist before games (FKs),
    and games must exist before team_game_stats.
    """
    stage.create_staging_schema(engine)

    raw_teams = extract.read_teams_raw(data_dir)
    valid_team_ids = set(raw_teams["id"])
    raw_games = extract.read_games_raw(data_dir)

    teams_df = clean.clean_teams(raw_teams)
    stage.copy_dataframe_to_staging(engine, teams_df, "teams")
    _report("teams", *load.load_teams(engine))

    raw_players = extract.read_players_raw(data_dir)
    raw_bio = extract.read_players_bio_raw(data_dir)
    players_df = clean.clean_players(raw_players, raw_bio)
    stage.copy_dataframe_to_staging(engine, players_df, "players")
    _report("players", *load.load_players(engine))

    games_df = clean.clean_games(raw_games, valid_team_ids)
    seasons_df = clean.clean_seasons(games_df)
    stage.copy_dataframe_to_staging(engine, seasons_df, "seasons")
    _report("seasons", *load.load_seasons(engine))

    stage.copy_dataframe_to_staging(engine, games_df, "games")
    _report("games", *load.load_games(engine))

    tgs_df = clean.clean_team_game_stats(raw_games, valid_team_ids)
    stage.copy_dataframe_to_staging(engine, tgs_df, "team_game_stats")
    _report("team_game_stats", *load.load_team_game_stats(engine))

    if not keep_staging:
        stage.drop_staging_schema(engine)


@app.command()
def backfill_history(
    data_dir: Path = typer.Option(Path("data/kaggle"), help="Directory containing the box_scores/ export"),
    keep_staging: bool = typer.Option(False, help="Don't drop the staging schema after loading"),
) -> None:
    """Backfills real gaps in the already-loaded games/seasons/team_game_stats/
    players tables (e.g. the entire 1960-61 season and nearly all of 1961-62
    missing from the original wyattowalsh bootstrap, and players missing
    because that dataset predates their draft class) using box_scores/
    Games.csv, TeamStatistics.csv, and Players.csv. Purely additive --
    ON CONFLICT DO NOTHING (DO UPDATE widening for seasons) means existing
    correct rows are untouched. Run this before load-player-stats so more
    player-game rows can resolve their game_id/player_id FKs."""
    stage.create_staging_schema(engine)

    with engine.connect() as conn:
        valid_team_ids = set(conn.execute(text("SELECT nba_team_id FROM teams")).scalars().all())

    raw_games = extract.read_games_backfill_raw(data_dir)
    games_df = clean.clean_games_backfill(raw_games, valid_team_ids)
    seasons_df = clean.clean_seasons(games_df)
    stage.copy_dataframe_to_staging(engine, seasons_df, "seasons")
    _report("seasons", *load.load_seasons_widen(engine))

    stage.copy_dataframe_to_staging(engine, games_df, "games")
    _report("games", *load.load_games(engine))

    raw_tgs = extract.read_team_game_stats_backfill_raw(data_dir)
    tgs_df = clean.clean_team_game_stats_backfill(raw_tgs)
    stage.copy_dataframe_to_staging(engine, tgs_df, "team_game_stats")
    _report("team_game_stats", *load.load_team_game_stats(engine))

    raw_players = extract.read_players_backfill_raw(data_dir)
    players_df = clean.clean_players_backfill(raw_players)
    stage.copy_dataframe_to_staging(engine, players_df, "players")
    _report("players", *load.load_players(engine))

    if not keep_staging:
        stage.drop_staging_schema(engine)


@app.command()
def load_player_stats(
    data_dir: Path = typer.Option(Path("data/kaggle"), help="Directory containing the box_scores/ export"),
    keep_staging: bool = typer.Option(False, help="Don't drop the staging schema after loading"),
) -> None:
    """Populates player_game_stats from the eoinamoore box-score dataset's
    box_scores/PlayerStatistics.csv (a separate command from `main` since
    this file is much larger/slower, and requires games/teams/players to
    already be loaded for FK resolution). Run backfill-history first so as
    many rows as possible can resolve their game/player/team FKs."""
    stage.create_staging_schema(engine)

    raw_history = extract.read_team_history_raw(data_dir)
    team_name_lookup = clean.build_team_name_lookup(raw_history)

    raw = extract.read_player_game_stats_raw(data_dir)
    cleaned = clean.clean_player_game_stats(raw, team_name_lookup)
    stage.copy_dataframe_to_staging(engine, cleaned, "player_game_stats")
    _report("player_game_stats", *load.load_player_game_stats(engine))

    if not keep_staging:
        stage.drop_staging_schema(engine)


@app.command()
def load_play_by_play(
    data_dir: Path = typer.Option(Path("data/kaggle"), help="Directory containing the csv/ and box_scores/ exports"),
    keep_staging: bool = typer.Option(False, help="Don't drop the staging schema after loading"),
) -> None:
    """Populates play_by_play from TWO non-overlapping sources: csv/
    play_by_play.csv (1996-11-01 to 2023-06-09) and box_scores/
    PlayByPlay.parquet (2023-06-10 onward, filtered at read time). Loading
    only the non-overlapping portion of the second source is deliberate --
    the two datasets' coverage overlaps for ~27 seasons, and reloading that
    overlap would be pure wasted work (same games, same events, already
    covered). Requires games/players/teams to already be loaded."""
    stage.create_staging_schema(engine)

    raw_old = extract.read_play_by_play_old_raw(data_dir)
    old_df = clean.clean_play_by_play_old(raw_old)
    stage.copy_dataframe_to_staging(engine, old_df, "play_by_play")
    _report("play_by_play (pre-2023-06-10)", *load.load_play_by_play(engine))

    raw_new = extract.read_play_by_play_new_raw(data_dir)
    new_df = clean.clean_play_by_play_new(raw_new)
    stage.copy_dataframe_to_staging(engine, new_df, "play_by_play")
    _report("play_by_play (2023-06-10+)", *load.load_play_by_play(engine))

    if not keep_staging:
        stage.drop_staging_schema(engine)


@app.command()
def backfill_play_by_play_gap(
    date_from: str = typer.Argument(..., help="YYYY-MM-DD, inclusive"),
    date_to: str = typer.Argument(..., help="YYYY-MM-DD, exclusive"),
    data_dir: Path = typer.Option(Path("data/kaggle"), help="Directory containing the box_scores/ export"),
    keep_staging: bool = typer.Option(False, help="Don't drop the staging schema after loading"),
) -> None:
    """Backfills a specific date range from box_scores/PlayByPlay.parquet
    that turned out to be missing from the wyattowalsh CSV despite being
    "pre-2023" (that source is NOT uniformly complete pre-2023 -- e.g. the
    entire 2012-13 regular season, 1,229 games, had zero play-by-play rows,
    confirmed via a post-load per-season coverage audit that found every
    other season at the expected ~87-92% while 2012-13 was at 0%). Use this
    for a specific discovered gap, not as a substitute for load-play-by-play
    -- reloading already-covered seasons would be pure wasted work."""
    stage.create_staging_schema(engine)

    raw = extract.read_play_by_play_new_raw(data_dir, date_from=date_from, date_to=date_to)
    cleaned = clean.clean_play_by_play_new(raw)
    stage.copy_dataframe_to_staging(engine, cleaned, "play_by_play")
    _report(f"play_by_play ({date_from} to {date_to})", *load.load_play_by_play(engine))

    if not keep_staging:
        stage.drop_staging_schema(engine)


if __name__ == "__main__":
    app()
