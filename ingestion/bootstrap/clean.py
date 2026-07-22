from __future__ import annotations

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pandas as pd

from ingestion.bootstrap import column_maps


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def parse_height(value) -> int | None:
    """Parse a "feet-inches" height string (e.g. "6-9") into total inches.

    Confirmed against the real Kaggle common_player_info.csv `height`
    column, which uses this format (e.g. "6-10").
    """
    if _is_missing(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    feet_str, sep, inches_str = text.partition("-")
    if not sep:
        return None
    try:
        feet = int(feet_str)
        inches = int(inches_str) if inches_str else 0
    except ValueError:
        return None
    return feet * 12 + inches


def parse_minutes(value) -> Decimal | None:
    """Parse a "MM:SS" minutes-played string (e.g. "34:12") into decimal
    minutes (e.g. Decimal("34.2")), matching player_game_stats.minutes'
    NUMERIC(4,1) column. Falls back to parsing plain decimal strings.

    Not used by this bootstrap (the Kaggle dataset has no player-level box
    scores -- see column_maps.py); kept here for Phase 3's nba_api sync,
    whose boxscoretraditionalv2 endpoint returns minutes in this format.
    """
    if _is_missing(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if ":" in text:
            minutes_str, _, seconds_str = text.partition(":")
            total = Decimal(minutes_str) + (Decimal(seconds_str) / Decimal(60))
        else:
            total = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def parse_date(value) -> date | None:
    """Parse a date-like value (string, pandas Timestamp, or None/NaN)."""
    if _is_missing(value):
        return None
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        return None
    return parsed.date()


def dedupe_by_key(df: pd.DataFrame, key_column: str) -> pd.DataFrame:
    """Drop duplicate rows by a natural/source key, keeping the last
    occurrence (later rows in a source export are treated as more
    authoritative). Used by every per-table clean_*() function."""
    return df.drop_duplicates(subset=[key_column], keep="last")


def _as_nullable_int(series: pd.Series) -> pd.Series:
    """Cast a column that may hold NaN/None to pandas' nullable Int64
    dtype, so it serializes as "66" (or empty, for NULL) rather than
    "66.0" -- COPY into a SMALLINT staging column rejects the latter."""
    return pd.to_numeric(series, errors="coerce").round().astype("Int64")


def clean_teams(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns=column_maps.TEAMS_RENAME)[list(column_maps.TEAMS_RENAME.values())]
    # Not present anywhere in the source dataset -- left NULL (nullable
    # in the schema) rather than guessed.
    df["conference"] = None
    df["division"] = None
    return dedupe_by_key(df, "nba_team_id")


def clean_players(raw_players: pd.DataFrame, raw_bio: pd.DataFrame) -> pd.DataFrame:
    """player.csv has full identity for every player (4831 rows);
    common_player_info.csv only has bio data for a subset (4171 rows).
    Left-join so players without bio data still get a row with NULL bio
    fields, instead of silently dropping ~660 players."""
    players = raw_players.rename(columns=column_maps.PLAYERS_RENAME)
    players = players[list(column_maps.PLAYERS_RENAME.values())]
    players = dedupe_by_key(players, "nba_player_id")

    bio = raw_bio.rename(columns=column_maps.PLAYERS_BIO_RENAME)
    bio = bio[list(column_maps.PLAYERS_BIO_RENAME.values())]
    bio = dedupe_by_key(bio, "nba_player_id")
    bio["height_in"] = _as_nullable_int(bio["height_in"].map(parse_height))
    bio["weight_lb"] = _as_nullable_int(bio["weight_lb"])
    bio["draft_year"] = _as_nullable_int(bio["draft_year"])
    bio["birthdate"] = bio["birthdate"].map(parse_date)

    merged = players.merge(bio, on="nba_player_id", how="left")
    return merged


def _valid_franchise_games(raw_games: pd.DataFrame, valid_team_ids: set[int]) -> pd.DataFrame:
    """Filters out rows referencing a non-franchise team id (All-Star Game
    constructs like "Team Durant", international exhibition clubs) and any
    row where home/away are the same team (shouldn't occur, cheap to guard).
    Shared by clean_games and clean_team_game_stats so both stay consistent
    about which rows count as a "real" game."""
    mask = (
        raw_games["team_id_home"].isin(valid_team_ids)
        & raw_games["team_id_away"].isin(valid_team_ids)
        & (raw_games["team_id_home"] != raw_games["team_id_away"])
    )
    return raw_games[mask].copy()


def _season_label(season_id: pd.Series) -> pd.Series:
    """season_id's leading digit encodes game type (1=Pre Season,
    2=Regular Season, 4=Playoffs); the 4-digit year suffix identifies the
    season itself and is consistent across game types for the same season."""
    start_year = season_id.str[1:].astype(int)
    end_year_suffix = (start_year + 1).astype(str).str[-2:]
    return start_year.astype(str) + "-" + end_year_suffix


def clean_games(raw_games: pd.DataFrame, valid_team_ids: set[int]) -> pd.DataFrame:
    df = _valid_franchise_games(raw_games, valid_team_ids)
    df["season_label"] = _season_label(df["season_id"])
    df["game_date"] = df["game_date"].map(parse_date)
    df = df.rename(columns=column_maps.GAMES_RENAME)
    df["home_score"] = _as_nullable_int(df["home_score"])
    df["away_score"] = _as_nullable_int(df["away_score"])
    target_columns = list(column_maps.GAMES_RENAME.values()) + ["season_label"]
    df = df[target_columns]
    return dedupe_by_key(df, "nba_game_id")


def clean_seasons(clean_games_df: pd.DataFrame) -> pd.DataFrame:
    """Derived entirely from games (no dedicated season source in this
    dataset): a season's start/end date is the min/max game_date across
    all its games (any game type)."""
    grouped = clean_games_df.groupby("season_label")["game_date"].agg(["min", "max"]).reset_index()
    return grouped.rename(columns={"min": "start_date", "max": "end_date"})


def _round_minutes(value) -> Decimal | None:
    """Rounds an already-decimal minutes value (e.g. 39.166666666666664,
    from the box-score dataset's numMinutes column) to 1 decimal place,
    fitting player_game_stats.minutes' NUMERIC(4,1) column. Unlike
    parse_minutes(), there's no "MM:SS" string to split -- this source
    already reports minutes as a plain float.

    A handful of rows (12 out of 1.67M, confirmed, all in two preseason
    games) have a genuinely negative numMinutes -- a source data-quality
    glitch, not a real value. Nulled out rather than propagated (the
    minutes_nonneg CHECK constraint would reject them anyway), while the
    rest of that row's stats (points/rebounds/etc.) are kept since they
    look legitimate."""
    if _is_missing(value):
        return None
    try:
        rounded = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    return rounded if rounded >= 0 else None


_PLAYER_GAME_STATS_INT_COLUMNS = (
    "nba_player_id", "nba_team_id",
    "points", "rebounds", "assists", "steals", "blocks", "turnovers",
    "fg_made", "fg_attempted", "fg3_made", "fg3_attempted", "ft_made", "ft_attempted",
)


def build_team_name_lookup(raw_history: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Builds a (teamCity, teamName) -> nba_team_id lookup from
    box_scores/TeamHistories.csv, covering every historical city/name a
    franchise has used (e.g. Seattle SuperSonics and OKC Thunder both map
    to the same persistent id). Used as a fallback in
    clean_player_game_stats() for rows where playerteamId itself is blank
    in the source but the city/name still identify a real team."""
    deduped = raw_history.drop_duplicates(subset=["teamCity", "teamName"], keep="last")
    return {
        (row.teamCity, row.teamName): row.teamId
        for row in deduped.itertuples()
        if pd.notna(row.teamId)
    }


def clean_players_backfill(raw: pd.DataFrame) -> pd.DataFrame:
    """Source: box_scores/Players.csv -- backfills players missing from the
    wyattowalsh-sourced `players` table. Confirmed cause: that table was
    frozen before recent draft classes existed (~87% of unresolved
    PlayerStatistics.csv rows are 2023-24-debut players) plus a smaller set
    of older/obscure players missing outright (e.g. Loy Vaught, 1990-96)."""
    df = raw.rename(columns=column_maps.PLAYERS_BACKFILL_RENAME)
    df["full_name"] = df["firstName"].fillna("") + " " + df["lastName"].fillna("")
    df["full_name"] = df["full_name"].str.strip()
    df["birthdate"] = df["birthdate"].map(parse_date)
    for column in ("height_in", "weight_lb", "draft_year"):
        df[column] = _as_nullable_int(df[column])
    target_columns = ["nba_player_id", "full_name", "birthdate", "height_in", "weight_lb", "draft_year"]
    df = df[target_columns]
    return dedupe_by_key(df, "nba_player_id")


def clean_player_game_stats(raw: pd.DataFrame, team_name_lookup: dict[tuple[str, str], int]) -> pd.DataFrame:
    """Source: box_scores/PlayerStatistics.csv (eoinamoore dataset), a
    genuine per-player-per-game box score table spanning all of NBA
    history -- unlike the wyattowalsh dataset used elsewhere in this
    bootstrap, no play-by-play parsing or 1996-97 scope cut is needed.

    gameId is zero-padded back to the standard 10-char nba.com game id
    ("00" + season-type digit + 2-digit season year + 5-digit sequence),
    since this export drops the leading zeros the source id actually has.

    Rows with a blank numMinutes are DNPs (did not play -- verified: every
    such row has 0 for points/rebounds/assists/fg_attempted with no
    exception), not real appearances with unrecorded minutes. These are
    dropped rather than loaded as a zero-stat game line, since a DNP isn't
    a game the player actually played -- keeping them would silently
    inflate games-played counts and drag season averages down (caught via
    a spot-check: LeBron James' 2012-13 season initially came back as 81
    games at 25.1 ppg instead of the real 76 games at 26.8 ppg, the
    difference being 5 rest-game DNPs during Miami's win-streak stretch).

    A large share of rows (confirmed: ~91k) have a blank playerteamId even
    though playerteamCity/playerteamName clearly identify a real, current
    franchise -- team_name_lookup (from build_team_name_lookup) fills these
    in by city/name instead of leaving them to fail the team_id FK join.
    """
    df = raw.rename(columns=column_maps.PLAYER_GAME_STATS_RENAME)
    df = df[list(column_maps.PLAYER_GAME_STATS_RENAME.values()) + ["gameId", "playerteamCity", "playerteamName"]]
    df["nba_game_id"] = df["gameId"].str.zfill(10)
    df = df.drop(columns=["gameId"])

    df = df[df["minutes"].notna()].copy()

    missing_team = df["nba_team_id"].isna()
    if missing_team.any():
        keys = list(zip(df.loc[missing_team, "playerteamCity"], df.loc[missing_team, "playerteamName"]))
        df.loc[missing_team, "nba_team_id"] = [team_name_lookup.get(key) for key in keys]
    df = df.drop(columns=["playerteamCity", "playerteamName"])

    for column in _PLAYER_GAME_STATS_INT_COLUMNS:
        df[column] = _as_nullable_int(df[column])
    df["minutes"] = df["minutes"].map(_round_minutes)

    return df.drop_duplicates(subset=["nba_game_id", "nba_player_id"], keep="last")


def _derive_season_label_from_date(game_date: pd.Series) -> pd.Series:
    """NBA seasons run October-June, so no real game falls in July/August --
    a safe cutoff for inferring a season's start year from a game date.
    Used for the box-score dataset's Games.csv, which (unlike the
    wyattowalsh dataset's game.csv) has no season_id column to parse."""
    dt = pd.to_datetime(game_date)
    start_year = dt.dt.year.where(dt.dt.month >= 8, dt.dt.year - 1)
    end_year_suffix = (start_year + 1).astype(str).str[-2:]
    return start_year.astype(str) + "-" + end_year_suffix


def clean_games_backfill(raw: pd.DataFrame, valid_team_ids: set[int]) -> pd.DataFrame:
    """Source: box_scores/Games.csv -- used only to backfill real gaps
    discovered in the already-loaded `games` table (e.g. the entire
    1960-61 season and nearly all of 1961-62 missing), not to replace it.
    Shaped to match the existing staging.games columns exactly, so the
    existing load_games() is reused unchanged; ON CONFLICT DO NOTHING
    there makes this purely additive."""
    mask = (
        raw["hometeamId"].isin(valid_team_ids)
        & raw["awayteamId"].isin(valid_team_ids)
        & (raw["hometeamId"] != raw["awayteamId"])
    )
    df = raw[mask].copy()
    df["nba_game_id"] = df["gameId"].str.zfill(10)
    df["season_label"] = _derive_season_label_from_date(df["gameDate"])
    df["game_date"] = df["gameDate"].map(parse_date)
    df = df.rename(columns=column_maps.GAMES_BACKFILL_RENAME)
    df["home_score"] = _as_nullable_int(df["home_score"])
    df["away_score"] = _as_nullable_int(df["away_score"])
    target_columns = [
        "nba_game_id", "game_date", "game_type", "home_nba_team_id",
        "away_nba_team_id", "home_score", "away_score", "season_label",
    ]
    df = df[target_columns]
    return dedupe_by_key(df, "nba_game_id")


def clean_team_game_stats_backfill(raw: pd.DataFrame) -> pd.DataFrame:
    """Source: box_scores/TeamStatistics.csv -- already one row per team
    per game (unlike game.csv in the wyattowalsh dataset, which is wide
    and needs a wide-to-long reshape), so no reshape step is needed here."""
    df = raw.copy()
    df["nba_game_id"] = df["gameId"].str.zfill(10)
    df = df.rename(columns=column_maps.TEAM_GAME_STATS_BACKFILL_RENAME)
    target_columns = ["nba_game_id", "nba_team_id", "rebounds", "assists", "turnovers", "points"]
    df = df[target_columns]
    for column in ("rebounds", "assists", "turnovers", "points"):
        df[column] = _as_nullable_int(df[column])
    return df.drop_duplicates(subset=["nba_game_id", "nba_team_id"], keep="last")


def clean_team_game_stats(raw_games: pd.DataFrame, valid_team_ids: set[int]) -> pd.DataFrame:
    """game.csv is wide (one row per game, home_*/away_* columns) -- this
    reshapes it into the long format team_game_stats needs (one row per
    team per game): each game contributes a home row and an away row."""
    df = _valid_franchise_games(raw_games, valid_team_ids)
    df["nba_game_id"] = df["game_id"]

    home = df[["nba_game_id", "team_id_home", "reb_home", "ast_home", "tov_home"]].rename(
        columns={
            "team_id_home": "nba_team_id",
            "reb_home": "rebounds",
            "ast_home": "assists",
            "tov_home": "turnovers",
        }
    )
    home["points"] = df["pts_home"]

    away = df[["nba_game_id", "team_id_away", "reb_away", "ast_away", "tov_away"]].rename(
        columns={
            "team_id_away": "nba_team_id",
            "reb_away": "rebounds",
            "ast_away": "assists",
            "tov_away": "turnovers",
        }
    )
    away["points"] = df["pts_away"]

    long_df = pd.concat([home, away], ignore_index=True)
    for column in ("points", "rebounds", "assists", "turnovers"):
        long_df[column] = _as_nullable_int(long_df[column])
    return long_df.drop_duplicates(subset=["nba_game_id", "nba_team_id"], keep="last")


def _zero_as_null(series: pd.Series) -> pd.Series:
    """nba.com's convention for "no player"/"no team" on an event row is
    id 0, not a blank cell -- confirmed in both play-by-play sources
    (e.g. period-start/timeout rows). Masks 0 to <NA> after nullable-int
    coercion so these don't get treated as a real player/team id 0."""
    coerced = _as_nullable_int(series)
    return coerced.mask(coerced == 0)


def clean_play_by_play_old(raw: pd.DataFrame) -> pd.DataFrame:
    """Source: csv/play_by_play.csv (wyattowalsh dataset), 1996-11-01 to
    2023-06-09. event_type is EVENTMSGTYPE_LABELS applied to the numeric
    eventmsgtype code (verified against real description text during this
    project's earlier research). description coalesces home/visitor/
    neutral description -- only one is ever populated per row. score is
    "AWAY - HOME" (confirmed against a real game's known final score)."""
    df = raw.copy()
    df["nba_game_id"] = df["game_id"].str.zfill(10)
    df["sequence"] = df["eventnum"]
    df["event_type"] = df["eventmsgtype"].map(
        lambda code: column_maps.EVENTMSGTYPE_LABELS.get(code, f"Unknown ({code})")
    )
    df["clock"] = df["pctimestring"]
    df["description"] = (
        df["homedescription"].fillna(df["visitordescription"]).fillna(df["neutraldescription"])
    )

    score_parts = df["score"].str.split(" - ", expand=True)
    df["score_away"] = _as_nullable_int(score_parts[0]) if 0 in score_parts else pd.array([pd.NA] * len(df), dtype="Int64")
    df["score_home"] = _as_nullable_int(score_parts[1]) if 1 in score_parts else pd.array([pd.NA] * len(df), dtype="Int64")

    df["nba_player_id"] = _zero_as_null(df["player1_id"])
    df["nba_player2_id"] = _zero_as_null(df["player2_id"])
    df["nba_player3_id"] = _zero_as_null(df["player3_id"])
    df["nba_team_id"] = _zero_as_null(df["player1_team_id"])

    df["sub_type"] = None
    df["shot_x"] = None
    df["shot_y"] = None
    df["shot_distance"] = None
    df["shot_made"] = None

    target_columns = [
        "nba_game_id", "sequence", "period", "clock", "event_type", "sub_type", "description",
        "nba_player_id", "nba_player2_id", "nba_player3_id", "nba_team_id",
        "score_home", "score_away", "shot_x", "shot_y", "shot_distance", "shot_made",
    ]
    df = df[target_columns]
    return df.drop_duplicates(subset=["nba_game_id", "sequence"], keep="last")


def clean_play_by_play_new(raw: pd.DataFrame) -> pd.DataFrame:
    """Source: box_scores/PlayByPlay.parquet (eoinamoore dataset), filtered
    to 2023-06-10 onward at extract time (see extract.py). event_type/
    sub_type are the source's own actionType/subType passed through mostly
    as-is (see column_maps.py for why a unified taxonomy across both
    sources was deliberately not attempted). nba_player2_id/nba_player3_id
    are COALESCE'd from whichever role field is populated -- at most one
    of each pair is ever non-null per row.

    sequence prefers orderNumber but falls back to actionNumber: confirmed
    (via the 2012-13 backfill) that orderNumber is a live-API-only field,
    entirely null for older retroactively-added games, while actionNumber
    is populated and unique-per-game across every era checked so far.

    event_type is NOT NULL in the schema, but a handful of rows (2 out of
    586,028 checked in the 2012-13 backfill) have a blank actionType --
    a rare source data artifact, not a real category. Falls back to
    "Unknown" rather than failing the whole batch."""
    df = raw.rename(columns=column_maps.PLAY_BY_PLAY_NEW_RENAME)
    df["nba_game_id"] = df["gameId"].str.zfill(10)
    event_type = df["event_type"].fillna("").str.strip()
    df["event_type"] = event_type.where(event_type != "", "Unknown")
    df["sequence"] = _as_nullable_int(df["orderNumber"].fillna(df["actionNumber"]))

    df["nba_player_id"] = _zero_as_null(df["nba_player_id"])
    df["nba_team_id"] = _zero_as_null(df["nba_team_id"])
    df["nba_player2_id"] = _zero_as_null(df["assistPersonId"].fillna(df["stealPersonId"]))
    df["nba_player3_id"] = _zero_as_null(df["blockPersonId"].fillna(df["foulDrawnPersonId"]))

    df["score_home"] = _as_nullable_int(df["score_home"])
    df["score_away"] = _as_nullable_int(df["score_away"])
    df["shot_distance"] = _as_nullable_int(df["shot_distance"])

    result_lower = df["shotResult"].str.lower()
    df["shot_made"] = result_lower.map(
        lambda v: True if isinstance(v, str) and "made" in v else (False if isinstance(v, str) and "missed" in v else None)
    )

    target_columns = [
        "nba_game_id", "sequence", "period", "clock", "event_type", "sub_type", "description",
        "nba_player_id", "nba_player2_id", "nba_player3_id", "nba_team_id",
        "score_home", "score_away", "shot_x", "shot_y", "shot_distance", "shot_made",
    ]
    df = df[target_columns]
    return df.drop_duplicates(subset=["nba_game_id", "sequence"], keep="last")
