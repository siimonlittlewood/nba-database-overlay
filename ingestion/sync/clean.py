"""Cleaning functions for the nba_api sync (Phase 3).

Mirrors ingestion/bootstrap/clean.py's conventions (nullable-int coercion,
dedupe-by-key, DNP filtering) so staged data matches the exact same target
shape and can reuse the existing load_games/load_team_game_stats/
load_player_game_stats loaders unchanged.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pandas as pd

from ingestion.bootstrap.clean import _as_nullable_int, _is_missing, dedupe_by_key
from ingestion.sync import column_maps

_ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)M)?(?:([\d.]+)S)?$")


def parse_box_v3_minutes(value) -> Decimal | None:
    """Parses BoxScoreTraditionalV3's "minutes" field. VERIFY ON FIRST RUN:
    handles both a "MM:SS" string (V2's format, possibly still used by V3)
    and an ISO-8601 duration like "PT34M12.00S" (seen on other V3 NBA Stats
    endpoints) since this couldn't be confirmed against a live response
    from this sandbox (see run_sync.py's module docstring). If the real
    format is neither, this returns None and the row is dropped like a DNP
    -- if that happens for every row on first run, the format needs a new
    case added here, not silent zeros."""
    if _is_missing(value):
        return None
    text = str(value).strip()
    if not text:
        return None

    iso_match = _ISO_DURATION_RE.match(text)
    if iso_match:
        minutes_part, seconds_part = iso_match.groups()
        minutes = Decimal(minutes_part) if minutes_part else Decimal(0)
        seconds = Decimal(seconds_part) if seconds_part else Decimal(0)
        total = minutes + (seconds / Decimal(60))
    elif ":" in text:
        minutes_str, _, seconds_str = text.partition(":")
        try:
            total = Decimal(minutes_str) + (Decimal(seconds_str) / Decimal(60))
        except InvalidOperation:
            return None
    else:
        try:
            total = Decimal(text)
        except InvalidOperation:
            return None

    rounded = total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return rounded if rounded >= 0 else None


def season_label_and_type_from_season_id(season_id: str) -> tuple[str, str]:
    """SEASON_ID is 5 chars: 1-digit season-type code + 4-digit start year
    (e.g. "22025" -> Regular Season, 2025-26). Same scheme as the
    wyattowalsh dataset's season_id, just with a 4-digit (not split) year
    -- see column_maps.py's module docstring."""
    type_code = season_id[0]
    start_year = int(season_id[1:])
    game_type = column_maps.SEASON_TYPE_BY_CODE.get(type_code, f"Unknown ({type_code})")
    season_label = f"{start_year}-{str(start_year + 1)[-2:]}"
    return season_label, game_type


def clean_games_from_gamefinder(raw: pd.DataFrame) -> pd.DataFrame:
    """LeagueGameFinder returns one row per team per game -- pairs the two
    rows for each GAME_ID into a single games row, using MATCHUP's "vs."
    (home) / "@" (away) convention to tell them apart."""
    df = raw.rename(columns=column_maps.GAME_FINDER_RENAME)
    df["nba_game_id"] = df["nba_game_id"].astype(str).str.zfill(10)
    df["is_home"] = ~df["matchup"].str.contains("@", na=False)

    labels_types = df["season_id"].astype(str).map(season_label_and_type_from_season_id)
    df["season_label"] = labels_types.map(lambda x: x[0])
    df["game_type"] = labels_types.map(lambda x: x[1])

    home = df[df["is_home"]][["nba_game_id", "game_date", "game_type", "season_label", "nba_team_id", "points"]]
    home = home.rename(columns={"nba_team_id": "home_nba_team_id", "points": "home_score"})
    away = df[~df["is_home"]][["nba_game_id", "nba_team_id", "points"]]
    away = away.rename(columns={"nba_team_id": "away_nba_team_id", "points": "away_score"})

    merged = home.merge(away, on="nba_game_id", how="inner")
    merged["game_date"] = pd.to_datetime(merged["game_date"]).dt.date
    merged["home_score"] = _as_nullable_int(merged["home_score"])
    merged["away_score"] = _as_nullable_int(merged["away_score"])
    return dedupe_by_key(merged, "nba_game_id")


def clean_team_game_stats_from_gamefinder(raw: pd.DataFrame) -> pd.DataFrame:
    """Each LeagueGameFinder row is already one team's box score line for
    one game -- no reshape needed, unlike the wyattowalsh dataset's wide
    game.csv."""
    df = raw.rename(columns=column_maps.GAME_FINDER_RENAME)
    df["nba_game_id"] = df["nba_game_id"].astype(str).str.zfill(10)
    target_columns = ["nba_game_id", "nba_team_id", "rebounds", "assists", "turnovers", "points"]
    df = df[target_columns].copy()
    for column in ("rebounds", "assists", "turnovers", "points"):
        df[column] = _as_nullable_int(df[column])
    return df.drop_duplicates(subset=["nba_game_id", "nba_team_id"], keep="last")


_PLAYER_BOX_INT_COLUMNS = (
    "nba_player_id", "nba_team_id",
    "points", "rebounds", "assists", "steals", "blocks", "turnovers",
    "fg_made", "fg_attempted", "fg3_made", "fg3_attempted", "ft_made", "ft_attempted",
)


def clean_player_game_stats_from_boxscore(raw: pd.DataFrame) -> pd.DataFrame:
    """raw is the concatenation of BoxScoreTraditionalV3's PlayerStats
    dataframe across however many games were fetched this run (each row
    already has a gameId column attached -- see column_maps.py). Rows with
    an unparseable/blank minutes value are dropped, same DNP-filtering
    rationale as ingestion/bootstrap/clean.py's clean_player_game_stats
    (verified there: a blank minutes value always means zero real stats)."""
    df = raw.rename(columns=column_maps.PLAYER_BOX_RENAME)
    df = df[list(column_maps.PLAYER_BOX_RENAME.values()) + ["gameId"]]
    df["nba_game_id"] = df["gameId"].astype(str).str.zfill(10)
    df = df.drop(columns=["gameId"])

    df["minutes"] = df["minutes"].map(parse_box_v3_minutes)
    df = df[df["minutes"].notna()].copy()

    for column in _PLAYER_BOX_INT_COLUMNS:
        df[column] = _as_nullable_int(df[column])

    return df.drop_duplicates(subset=["nba_game_id", "nba_player_id"], keep="last")
