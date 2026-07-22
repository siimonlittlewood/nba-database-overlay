from decimal import Decimal

import pandas as pd

from ingestion.sync.clean import (
    clean_games_from_gamefinder,
    clean_player_game_stats_from_boxscore,
    clean_team_game_stats_from_gamefinder,
    parse_box_v3_minutes,
    season_label_and_type_from_season_id,
)


def test_parse_box_v3_minutes_iso_duration():
    assert parse_box_v3_minutes("PT34M12.00S") == Decimal("34.2")


def test_parse_box_v3_minutes_mm_ss():
    assert parse_box_v3_minutes("34:12") == Decimal("34.2")


def test_parse_box_v3_minutes_missing():
    assert parse_box_v3_minutes(None) is None
    assert parse_box_v3_minutes("") is None


def test_parse_box_v3_minutes_iso_duration_zero_seconds():
    assert parse_box_v3_minutes("PT5M00.00S") == Decimal("5.0")


def test_season_label_and_type_regular_season():
    label, game_type = season_label_and_type_from_season_id("22025")
    assert label == "2025-26"
    assert game_type == "Regular Season"


def test_season_label_and_type_playoffs():
    label, game_type = season_label_and_type_from_season_id("42025")
    assert label == "2025-26"
    assert game_type == "Playoffs"


def _raw_gamefinder_row(**overrides) -> dict:
    row = {
        "SEASON_ID": "22025",
        "TEAM_ID": 1610612752,
        "GAME_ID": "22500405",
        "GAME_DATE": "2025-11-01",
        "MATCHUP": "NYK vs. BOS",
        "PTS": 110,
        "REB": 45,
        "AST": 25,
        "TOV": 12,
    }
    row.update(overrides)
    return row


def test_clean_games_from_gamefinder_pairs_home_and_away():
    raw = pd.DataFrame(
        [
            _raw_gamefinder_row(TEAM_ID=1610612752, MATCHUP="NYK vs. BOS", PTS=110),
            _raw_gamefinder_row(TEAM_ID=1610612738, MATCHUP="BOS @ NYK", PTS=105),
        ]
    )
    cleaned = clean_games_from_gamefinder(raw)
    assert len(cleaned) == 1
    row = cleaned.iloc[0]
    assert row["nba_game_id"] == "0022500405"
    assert row["home_nba_team_id"] == 1610612752
    assert row["away_nba_team_id"] == 1610612738
    assert row["home_score"] == 110
    assert row["away_score"] == 105
    assert row["game_type"] == "Regular Season"
    assert row["season_label"] == "2025-26"


def test_clean_team_game_stats_from_gamefinder():
    raw = pd.DataFrame([_raw_gamefinder_row()])
    cleaned = clean_team_game_stats_from_gamefinder(raw)
    assert cleaned["nba_game_id"].iloc[0] == "0022500405"
    assert cleaned["points"].iloc[0] == 110
    assert cleaned["rebounds"].iloc[0] == 45


def _raw_box_row(**overrides) -> dict:
    row = {
        "personId": 1628404,
        "teamId": 1610612752,
        "gameId": "22500405",
        "minutes": "PT34M12.00S",
        "points": 20,
        "reboundsTotal": 8,
        "assists": 5,
        "steals": 1,
        "blocks": 0,
        "turnovers": 2,
        "fieldGoalsMade": 8,
        "fieldGoalsAttempted": 15,
        "threePointersMade": 2,
        "threePointersAttempted": 5,
        "freeThrowsMade": 2,
        "freeThrowsAttempted": 3,
    }
    row.update(overrides)
    return row


def test_clean_player_game_stats_from_boxscore():
    raw = pd.DataFrame([_raw_box_row()])
    cleaned = clean_player_game_stats_from_boxscore(raw)
    assert len(cleaned) == 1
    row = cleaned.iloc[0]
    assert row["nba_game_id"] == "0022500405"
    assert row["nba_player_id"] == 1628404
    assert row["minutes"] == Decimal("34.2")
    assert row["points"] == 20


def test_clean_player_game_stats_from_boxscore_drops_dnp():
    raw = pd.DataFrame([_raw_box_row(minutes=None, points=0)])
    cleaned = clean_player_game_stats_from_boxscore(raw)
    assert len(cleaned) == 0
