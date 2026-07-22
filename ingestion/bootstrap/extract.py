from __future__ import annotations

from pathlib import Path

import pandas as pd

from ingestion.bootstrap import column_maps

# IDs in these CSVs must be read as strings where they carry leading zeros
# (game_id, season_id) -- pandas' default type inference would otherwise
# silently strip them. Integer id columns use the nullable Int64 dtype so
# stray blank cells don't force a float upcast.
_STRING_ID_COLUMNS = {"game_id", "season_id"}
_INT_ID_COLUMNS = {"id", "person_id", "team_id_home", "team_id_away"}


def _dtype_for(columns: list[str]) -> dict[str, object]:
    dtype: dict[str, object] = {}
    for col in columns:
        if col in _STRING_ID_COLUMNS:
            dtype[col] = str
        elif col in _INT_ID_COLUMNS:
            dtype[col] = "Int64"
    return dtype


def _read_csv(data_dir: Path, filename: str, columns: list[str]) -> pd.DataFrame:
    return pd.read_csv(data_dir / "csv" / filename, usecols=columns, dtype=_dtype_for(columns))


def read_teams_raw(data_dir: Path) -> pd.DataFrame:
    return _read_csv(data_dir, column_maps.TEAMS_SOURCE, list(column_maps.TEAMS_RENAME))


def read_players_raw(data_dir: Path) -> pd.DataFrame:
    return _read_csv(data_dir, column_maps.PLAYERS_SOURCE, list(column_maps.PLAYERS_RENAME))


def read_players_bio_raw(data_dir: Path) -> pd.DataFrame:
    return _read_csv(data_dir, column_maps.PLAYERS_BIO_SOURCE, list(column_maps.PLAYERS_BIO_RENAME))


def read_games_raw(data_dir: Path) -> pd.DataFrame:
    extra_stat_columns = [
        "reb_home", "reb_away", "ast_home", "ast_away", "tov_home", "tov_away",
    ]
    columns = list(column_maps.GAMES_RENAME) + ["season_id"] + extra_stat_columns
    return _read_csv(data_dir, column_maps.GAMES_SOURCE, columns)


def read_player_game_stats_raw(data_dir: Path) -> pd.DataFrame:
    """Reads from box_scores/ (the eoinamoore dataset), not csv/ (the
    wyattowalsh dataset the other read_*_raw functions use) -- a different
    Kaggle export extracted to its own sibling subfolder. gameId is read as
    a string so zero-padding in clean.py operates on exact source digits.
    playerteamCity/playerteamName are read alongside playerteamId (not part
    of PLAYER_GAME_STATS_RENAME, since they're only used as a fallback team
    lookup in clean.py, not loaded as their own columns)."""
    columns = list(column_maps.PLAYER_GAME_STATS_RENAME) + ["gameId", "playerteamCity", "playerteamName"]
    dtype = {"gameId": str, "personId": "Int64", "playerteamId": "Int64"}
    return pd.read_csv(
        data_dir / "box_scores" / column_maps.PLAYER_GAME_STATS_SOURCE,
        usecols=columns,
        dtype=dtype,
    )


def read_games_backfill_raw(data_dir: Path) -> pd.DataFrame:
    columns = list(column_maps.GAMES_BACKFILL_RENAME) + ["gameId", "gameDate"]
    dtype = {"gameId": str, "hometeamId": "Int64", "awayteamId": "Int64"}
    return pd.read_csv(
        data_dir / "box_scores" / column_maps.GAMES_BACKFILL_SOURCE,
        usecols=columns,
        dtype=dtype,
    )


def read_team_game_stats_backfill_raw(data_dir: Path) -> pd.DataFrame:
    columns = list(column_maps.TEAM_GAME_STATS_BACKFILL_RENAME) + ["gameId"]
    dtype = {"gameId": str, "teamId": "Int64"}
    return pd.read_csv(
        data_dir / "box_scores" / column_maps.TEAM_GAME_STATS_BACKFILL_SOURCE,
        usecols=columns,
        dtype=dtype,
    )


def read_players_backfill_raw(data_dir: Path) -> pd.DataFrame:
    columns = list(column_maps.PLAYERS_BACKFILL_RENAME) + ["firstName", "lastName"]
    dtype = {"personId": "Int64", "heightInches": "Int64", "bodyWeightLbs": "Int64", "draftYear": "Int64"}
    return pd.read_csv(
        data_dir / "box_scores" / column_maps.PLAYERS_BACKFILL_SOURCE,
        usecols=columns,
        dtype=dtype,
    )


def read_team_history_raw(data_dir: Path) -> pd.DataFrame:
    dtype = {"teamId": "Int64"}
    return pd.read_csv(
        data_dir / "box_scores" / column_maps.TEAM_HISTORY_SOURCE,
        usecols=["teamId", "teamCity", "teamName"],
        dtype=dtype,
    )


_PLAY_BY_PLAY_OLD_COLUMNS = [
    "game_id", "eventnum", "eventmsgtype", "period", "pctimestring",
    "homedescription", "visitordescription", "neutraldescription", "score",
    "player1_id", "player1_team_id", "player2_id", "player3_id",
]


def read_play_by_play_old_raw(data_dir: Path) -> pd.DataFrame:
    """wyattowalsh's csv/play_by_play.csv, covering 1996-11-01 to
    2023-06-09 (confirmed against `games`). Only the columns actually used
    are read -- this file is 13.6M rows, and columns like
    player1_team_abbreviation are redundant with player1_team_id."""
    dtype = {"game_id": str, "player1_id": "Int64", "player1_team_id": "Int64", "player2_id": "Int64", "player3_id": "Int64"}
    return pd.read_csv(
        data_dir / "csv" / column_maps.PLAY_BY_PLAY_OLD_SOURCE,
        usecols=_PLAY_BY_PLAY_OLD_COLUMNS,
        dtype=dtype,
    )


_PLAY_BY_PLAY_NEW_COLUMNS = [
    "gameId", "orderNumber", "actionNumber", "gameDateTimeEst", "period", "clock",
    "actionType", "subType", "description",
    "teamId", "personId", "assistPersonId", "stealPersonId", "blockPersonId", "foulDrawnPersonId",
    "scoreHome", "scoreAway", "x", "y", "shotDistance", "shotResult",
]


def read_play_by_play_new_raw(
    data_dir: Path,
    date_from: str = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    """eoinamoore's box_scores/PlayByPlay.parquet, filtered at the row-group
    level -- avoids reading the full 18.7M rows when only a subset is
    needed. Defaults to gameDateTimeEst >= PLAY_BY_PLAY_OLD_CUTOVER_DATE
    (the normal 2023-06-10-onward load); pass an explicit date_from/date_to
    to backfill a specific gap discovered in the wyattowalsh CSV instead
    (e.g. the entire 2012-13 regular season, confirmed missing via a
    post-load coverage audit -- see run_bootstrap.py's
    backfill_play_by_play_gap command). gameDateTimeEst is stored as a
    plain ISO-format string (confirmed via the parquet schema), so a
    string comparison filter works correctly."""
    import pyarrow.parquet as pq

    date_from = date_from if date_from is not None else column_maps.PLAY_BY_PLAY_OLD_CUTOVER_DATE
    filters = [("gameDateTimeEst", ">=", date_from)]
    if date_to is not None:
        filters.append(("gameDateTimeEst", "<", date_to))

    table = pq.read_table(
        data_dir / "box_scores" / column_maps.PLAY_BY_PLAY_NEW_SOURCE,
        columns=_PLAY_BY_PLAY_NEW_COLUMNS,
        filters=filters,
    )
    return table.to_pandas()
