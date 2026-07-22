from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import Game, PlayerGameStats, Season, Team, TeamGameStats, Player


def _make_team(session, nba_team_id: int, abbreviation: str) -> Team:
    team = Team(
        nba_team_id=nba_team_id,
        abbreviation=abbreviation,
        city="City",
        name=f"{abbreviation} Team",
    )
    session.add(team)
    session.flush()
    return team


def _make_season(session) -> Season:
    season = Season(season_label="TEST9999", start_date=date(2025, 10, 1), end_date=date(2026, 6, 1))
    session.add(season)
    session.flush()
    return season


def _make_game(session, season: Season, home: Team, away: Team, nba_game_id: str = "TEST0000001") -> Game:
    game = Game(
        nba_game_id=nba_game_id,
        season_id=season.id,
        game_date=date(2025, 10, 21),
        game_type="Regular Season",
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=110,
        away_score=105,
    )
    session.add(game)
    session.flush()
    return game


def test_create_full_row_round_trip(db_session):
    home = _make_team(db_session, nba_team_id=900000001, abbreviation="ATL")
    away = _make_team(db_session, nba_team_id=900000002, abbreviation="BOS")
    season = _make_season(db_session)
    game = _make_game(db_session, season, home, away)

    player = Player(nba_player_id=900000001, full_name="Test Player")
    db_session.add(player)
    db_session.flush()

    stats = PlayerGameStats(
        game_id=game.id,
        player_id=player.id,
        team_id=home.id,
        minutes=34.5,
        points=28,
        rebounds=7,
        assists=9,
    )
    team_stats = TeamGameStats(game_id=game.id, team_id=home.id, points=110, rebounds=45, assists=25, turnovers=12)
    db_session.add_all([stats, team_stats])
    db_session.flush()

    fetched = db_session.get(PlayerGameStats, stats.id)
    assert fetched.points == 28
    assert fetched.game.nba_game_id == "TEST0000001"
    assert fetched.player.full_name == "Test Player"


def test_player_game_stats_rejects_duplicate_player_per_game(db_session):
    home = _make_team(db_session, nba_team_id=900000001, abbreviation="ATL")
    away = _make_team(db_session, nba_team_id=900000002, abbreviation="BOS")
    season = _make_season(db_session)
    game = _make_game(db_session, season, home, away)
    player = Player(nba_player_id=900000001, full_name="Test Player")
    db_session.add(player)
    db_session.flush()

    db_session.add(PlayerGameStats(game_id=game.id, player_id=player.id, team_id=home.id, points=10))
    db_session.flush()

    db_session.add(PlayerGameStats(game_id=game.id, player_id=player.id, team_id=home.id, points=20))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_games_rejects_same_home_and_away_team(db_session):
    team = _make_team(db_session, nba_team_id=900000001, abbreviation="ATL")
    season = _make_season(db_session)

    db_session.add(
        Game(
            nba_game_id="TEST0000002",
            season_id=season.id,
            game_date=date(2025, 10, 21),
            game_type="Regular Season",
            home_team_id=team.id,
            away_team_id=team.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_teams_reject_duplicate_nba_team_id(db_session):
    _make_team(db_session, nba_team_id=900000001, abbreviation="ATL")
    db_session.add(Team(nba_team_id=900000001, abbreviation="DUP", city="City", name="Dup Team"))
    with pytest.raises(IntegrityError):
        db_session.flush()
