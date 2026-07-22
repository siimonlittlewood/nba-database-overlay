from datetime import date
from decimal import Decimal

import pandas as pd

from ingestion.bootstrap.clean import (
    build_team_name_lookup,
    clean_games_backfill,
    clean_play_by_play_new,
    clean_play_by_play_old,
    clean_player_game_stats,
    clean_players_backfill,
    clean_team_game_stats_backfill,
    dedupe_by_key,
    parse_date,
    parse_height,
    parse_minutes,
)


def test_parse_height_feet_inches():
    assert parse_height("6-9") == 81
    assert parse_height("7-0") == 84


def test_parse_height_missing():
    assert parse_height(None) is None
    assert parse_height(float("nan")) is None
    assert parse_height("") is None


def test_parse_height_malformed_returns_none():
    assert parse_height("not-a-height") is None


def test_parse_minutes_mm_ss():
    assert parse_minutes("34:12") == Decimal("34.2")
    assert parse_minutes("0:00") == Decimal("0.0")


def test_parse_minutes_plain_decimal():
    assert parse_minutes("34.5") == Decimal("34.5")


def test_parse_minutes_missing():
    assert parse_minutes(None) is None
    assert parse_minutes(float("nan")) is None
    assert parse_minutes("") is None


def test_parse_date_string():
    assert parse_date("2025-10-21") == date(2025, 10, 21)


def test_parse_date_timestamp():
    assert parse_date(pd.Timestamp("2025-10-21")) == date(2025, 10, 21)


def test_parse_date_missing():
    assert parse_date(None) is None
    assert parse_date(float("nan")) is None


def test_dedupe_by_key_keeps_last_occurrence():
    df = pd.DataFrame({"id": [1, 2, 1], "value": ["first", "only", "second"]})
    deduped = dedupe_by_key(df, "id")
    assert sorted(deduped["id"]) == [1, 2]
    assert deduped.loc[deduped["id"] == 1, "value"].iloc[0] == "second"


def _raw_player_game_stats_row(**overrides) -> dict:
    row = {
        "personId": 1628404,
        "playerteamId": 1610612752,
        "playerteamCity": "New York",
        "playerteamName": "Knicks",
        "gameId": "42500405",
        "numMinutes": 39.166666666666664,
        "points": 13,
        "reboundsTotal": 11,
        "assists": 2,
        "steals": 0,
        "blocks": 0,
        "turnovers": 1,
        "fieldGoalsMade": 4,
        "fieldGoalsAttempted": 11,
        "threePointersMade": 3,
        "threePointersAttempted": 6,
        "freeThrowsMade": 2,
        "freeThrowsAttempted": 3,
    }
    row.update(overrides)
    return row


def test_clean_player_game_stats_zero_pads_game_id():
    raw = pd.DataFrame([_raw_player_game_stats_row()])
    cleaned = clean_player_game_stats(raw, {})
    assert cleaned["nba_game_id"].iloc[0] == "0042500405"


def test_clean_player_game_stats_rounds_minutes():
    raw = pd.DataFrame([_raw_player_game_stats_row()])
    cleaned = clean_player_game_stats(raw, {})
    assert cleaned["minutes"].iloc[0] == Decimal("39.2")


def test_clean_player_game_stats_nulls_negative_minutes_but_keeps_row():
    raw = pd.DataFrame([_raw_player_game_stats_row(numMinutes=-5.0, points=8)])
    cleaned = clean_player_game_stats(raw, {})
    assert len(cleaned) == 1
    assert cleaned["minutes"].iloc[0] is None
    assert cleaned["points"].iloc[0] == 8


def test_clean_player_game_stats_drops_dnp_rows():
    raw = pd.DataFrame([_raw_player_game_stats_row(numMinutes=float("nan"), points=0)])
    cleaned = clean_player_game_stats(raw, {})
    assert len(cleaned) == 0


def test_clean_player_game_stats_coerces_nullable_ints():
    raw = pd.DataFrame([_raw_player_game_stats_row()])
    cleaned = clean_player_game_stats(raw, {})
    assert cleaned["points"].iloc[0] == 13
    assert str(cleaned["points"].dtype) == "Int64"


def test_clean_player_game_stats_dedupes_on_game_and_player():
    raw = pd.DataFrame(
        [
            _raw_player_game_stats_row(points=13),
            _raw_player_game_stats_row(points=99),
        ]
    )
    cleaned = clean_player_game_stats(raw, {})
    assert len(cleaned) == 1
    assert cleaned["points"].iloc[0] == 99


def test_clean_player_game_stats_fills_missing_team_id_via_name_lookup():
    raw = pd.DataFrame([_raw_player_game_stats_row(playerteamId=None)])
    lookup = {("New York", "Knicks"): 1610612752}
    cleaned = clean_player_game_stats(raw, lookup)
    assert cleaned["nba_team_id"].iloc[0] == 1610612752


def test_clean_player_game_stats_unmatched_team_name_stays_null():
    raw = pd.DataFrame([_raw_player_game_stats_row(playerteamId=None)])
    cleaned = clean_player_game_stats(raw, {})
    assert pd.isna(cleaned["nba_team_id"].iloc[0])


def test_build_team_name_lookup():
    raw_history = pd.DataFrame(
        [
            {"teamId": 1610612760, "teamCity": "Seattle", "teamName": "SuperSonics"},
            {"teamId": 1610612760, "teamCity": "Oklahoma City", "teamName": "Thunder"},
        ]
    )
    lookup = build_team_name_lookup(raw_history)
    assert lookup[("Seattle", "SuperSonics")] == 1610612760
    assert lookup[("Oklahoma City", "Thunder")] == 1610612760


def test_clean_players_backfill_combines_name_and_coerces_types():
    raw = pd.DataFrame(
        [
            {
                "personId": 78412,
                "firstName": "Loy",
                "lastName": "Vaught",
                "birthDate": "1968-02-27",
                "heightInches": 81,
                "bodyWeightLbs": 235,
                "draftYear": 1990,
            }
        ]
    )
    cleaned = clean_players_backfill(raw)
    assert cleaned["full_name"].iloc[0] == "Loy Vaught"
    assert cleaned["birthdate"].iloc[0] == date(1968, 2, 27)
    assert cleaned["height_in"].iloc[0] == 81


def test_clean_games_backfill_derives_season_label_and_zero_pads_id():
    raw = pd.DataFrame(
        [
            {
                "gameId": "26000001",
                "gameDate": "1960-10-19",
                "gameType": "Regular Season",
                "hometeamId": 1610612737,
                "awayteamId": 1610612738,
                "homeScore": 100,
                "awayScore": 95,
            }
        ]
    )
    cleaned = clean_games_backfill(raw, valid_team_ids={1610612737, 1610612738})
    assert cleaned["nba_game_id"].iloc[0] == "0026000001"
    assert cleaned["season_label"].iloc[0] == "1960-61"


def test_clean_games_backfill_filters_non_franchise_teams():
    raw = pd.DataFrame(
        [
            {
                "gameId": "26000001",
                "gameDate": "1960-10-19",
                "gameType": "All-Star Game",
                "hometeamId": 1610612737,
                "awayteamId": 999999999,
                "homeScore": 100,
                "awayScore": 95,
            }
        ]
    )
    cleaned = clean_games_backfill(raw, valid_team_ids={1610612737, 1610612738})
    assert len(cleaned) == 0


def test_clean_team_game_stats_backfill_zero_pads_and_renames():
    raw = pd.DataFrame(
        [
            {
                "gameId": "26000001",
                "teamId": 1610612737,
                "reboundsTotal": 45,
                "assists": 20,
                "turnovers": 15,
                "teamScore": 100,
            }
        ]
    )
    cleaned = clean_team_game_stats_backfill(raw)
    assert cleaned["nba_game_id"].iloc[0] == "0026000001"
    assert cleaned["nba_team_id"].iloc[0] == 1610612737
    assert cleaned["points"].iloc[0] == 100


def _raw_pbp_old_row(**overrides) -> dict:
    row = {
        "game_id": "29600012",
        "eventnum": 13,
        "eventmsgtype": 1,
        "period": 1,
        "pctimestring": "10:40",
        "homedescription": "O'Neal Slam Dunk (2 PTS)",
        "visitordescription": None,
        "neutraldescription": None,
        "score": "0 - 2",
        "player1_id": 406,
        "player1_team_id": 1610612747,
        "player2_id": 0,
        "player3_id": 0,
    }
    row.update(overrides)
    return row


def test_clean_play_by_play_old_maps_event_type_and_score():
    raw = pd.DataFrame([_raw_pbp_old_row()])
    cleaned = clean_play_by_play_old(raw)
    row = cleaned.iloc[0]
    assert row["nba_game_id"] == "0029600012"
    assert row["event_type"] == "Made Shot"
    assert row["description"] == "O'Neal Slam Dunk (2 PTS)"
    assert row["score_away"] == 0
    assert row["score_home"] == 2
    assert row["nba_player_id"] == 406
    assert row["nba_team_id"] == 1610612747


def test_clean_play_by_play_old_zero_player_id_is_null():
    raw = pd.DataFrame([_raw_pbp_old_row(eventmsgtype=12, player1_id=0, player1_team_id=0, homedescription=None)])
    cleaned = clean_play_by_play_old(raw)
    assert pd.isna(cleaned["nba_player_id"].iloc[0])
    assert pd.isna(cleaned["nba_team_id"].iloc[0])
    assert cleaned["event_type"].iloc[0] == "Start of Period"


def test_clean_play_by_play_old_unknown_eventmsgtype():
    raw = pd.DataFrame([_raw_pbp_old_row(eventmsgtype=999)])
    cleaned = clean_play_by_play_old(raw)
    assert cleaned["event_type"].iloc[0] == "Unknown (999)"


def _raw_pbp_new_row(**overrides) -> dict:
    row = {
        "gameId": "22500405",
        "orderNumber": 42,
        "actionNumber": 99,
        "period": 2,
        "clock": "PT08M15.00S",
        "actionType": "Made Shot",
        "subType": "Jump Shot",
        "description": "J. Hart Jump Shot",
        "teamId": "1610612752",
        "personId": "1628404",
        "assistPersonId": "201950",
        "stealPersonId": None,
        "blockPersonId": None,
        "foulDrawnPersonId": None,
        "scoreHome": 20,
        "scoreAway": 18,
        "x": 10.5,
        "y": 20.3,
        "shotDistance": 15.0,
        "shotResult": "Made",
    }
    row.update(overrides)
    return row


def test_clean_play_by_play_new_basic_mapping():
    raw = pd.DataFrame([_raw_pbp_new_row()])
    cleaned = clean_play_by_play_new(raw)
    row = cleaned.iloc[0]
    assert row["nba_game_id"] == "0022500405"
    assert row["event_type"] == "Made Shot"
    assert row["sub_type"] == "Jump Shot"
    assert row["nba_player_id"] == 1628404
    assert row["nba_team_id"] == 1610612752
    assert row["nba_player2_id"] == 201950
    assert row["shot_made"] == True  # noqa: E712 -- may be numpy bool_, not python bool
    assert row["shot_distance"] == 15


def test_clean_play_by_play_new_zero_person_id_is_null():
    raw = pd.DataFrame([_raw_pbp_new_row(personId="0", teamId="0", actionType="period", subType="start")])
    cleaned = clean_play_by_play_new(raw)
    assert pd.isna(cleaned["nba_player_id"].iloc[0])
    assert pd.isna(cleaned["nba_team_id"].iloc[0])


def test_clean_play_by_play_new_handles_colon_prefixed_shot_result():
    raw = pd.DataFrame([_raw_pbp_new_row(shotResult=": Missed")])
    cleaned = clean_play_by_play_new(raw)
    assert cleaned["shot_made"].iloc[0] == False  # noqa: E712 -- may be numpy bool_, not python bool


def test_clean_play_by_play_new_steal_and_block_fallback():
    raw = pd.DataFrame(
        [_raw_pbp_new_row(actionType="turnover", assistPersonId=None, stealPersonId="201950", blockPersonId="203954")]
    )
    cleaned = clean_play_by_play_new(raw)
    assert cleaned["nba_player2_id"].iloc[0] == 201950
    assert cleaned["nba_player3_id"].iloc[0] == 203954


def test_clean_play_by_play_new_sequence_prefers_order_number():
    raw = pd.DataFrame([_raw_pbp_new_row(orderNumber=42, actionNumber=99)])
    cleaned = clean_play_by_play_new(raw)
    assert cleaned["sequence"].iloc[0] == 42


def test_clean_play_by_play_new_sequence_falls_back_to_action_number():
    raw = pd.DataFrame([_raw_pbp_new_row(orderNumber=None, actionNumber=99)])
    cleaned = clean_play_by_play_new(raw)
    assert cleaned["sequence"].iloc[0] == 99


def test_clean_play_by_play_new_blank_action_type_falls_back_to_unknown():
    raw = pd.DataFrame(
        [
            _raw_pbp_new_row(orderNumber=1, actionType=None),
            _raw_pbp_new_row(orderNumber=2, actionType=" "),
        ]
    )
    cleaned = clean_play_by_play_new(raw)
    assert (cleaned["event_type"] == "Unknown").all()
