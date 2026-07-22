from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ingestion.bootstrap.stage import STAGING_SCHEMA


def _staged_count(engine: Engine, table_name: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {STAGING_SCHEMA}.{table_name}")).scalar_one()


def load_teams(engine: Engine) -> tuple[int, int]:
    staged = _staged_count(engine, "teams")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO teams (nba_team_id, abbreviation, city, name, conference, division)
                SELECT nba_team_id, abbreviation, city, name, conference, division
                FROM {STAGING_SCHEMA}.teams
                ON CONFLICT (nba_team_id) DO NOTHING
                """
            )
        )
    return staged, result.rowcount


def load_players(engine: Engine) -> tuple[int, int]:
    staged = _staged_count(engine, "players")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO players (nba_player_id, full_name, birthdate, height_in, weight_lb, draft_year)
                SELECT nba_player_id, full_name, birthdate, height_in, weight_lb, draft_year
                FROM {STAGING_SCHEMA}.players
                ON CONFLICT (nba_player_id) DO NOTHING
                """
            )
        )
    return staged, result.rowcount


def load_seasons(engine: Engine) -> tuple[int, int]:
    staged = _staged_count(engine, "seasons")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO seasons (season_label, start_date, end_date)
                SELECT season_label, start_date, end_date
                FROM {STAGING_SCHEMA}.seasons
                ON CONFLICT (season_label) DO NOTHING
                """
            )
        )
    return staged, result.rowcount


def load_seasons_widen(engine: Engine) -> tuple[int, int]:
    """Like load_seasons, but widens an existing season's start/end dates
    via LEAST/GREATEST instead of leaving them untouched on conflict. Used
    by the box-score backfill: a season whose date range was originally
    computed from a dataset with a near-total gap for that season (e.g.
    1961-62 previously showed a start_date of March 1962, an artifact of
    the season being almost entirely missing) gets corrected once the
    real games are added, instead of keeping the artifact forever."""
    staged = _staged_count(engine, "seasons")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO seasons (season_label, start_date, end_date)
                SELECT season_label, start_date, end_date
                FROM {STAGING_SCHEMA}.seasons
                ON CONFLICT (season_label) DO UPDATE SET
                    start_date = LEAST(seasons.start_date, EXCLUDED.start_date),
                    end_date = GREATEST(seasons.end_date, EXCLUDED.end_date)
                """
            )
        )
    return staged, result.rowcount


def load_games(engine: Engine) -> tuple[int, int]:
    """Resolves surrogate FKs by joining staged nba.com ids against the
    already-loaded seasons/teams tables. Rows whose season/team can't be
    resolved are dropped by the inner joins rather than aborting the whole
    batch; staged - inserted (once teams/seasons are fully loaded) reports
    how many, if any, were rejected."""
    staged = _staged_count(engine, "games")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO games (
                    nba_game_id, season_id, game_date, game_type,
                    home_team_id, away_team_id, home_score, away_score
                )
                SELECT s.nba_game_id, se.id, s.game_date, s.game_type,
                       ht.id, at.id, s.home_score, s.away_score
                FROM {STAGING_SCHEMA}.games s
                JOIN seasons se ON se.season_label = s.season_label
                JOIN teams ht ON ht.nba_team_id = s.home_nba_team_id
                JOIN teams at ON at.nba_team_id = s.away_nba_team_id
                ON CONFLICT (nba_game_id) DO NOTHING
                """
            )
        )
    return staged, result.rowcount


def load_player_game_stats(engine: Engine) -> tuple[int, int]:
    """Resolves surrogate FKs the same way load_games/load_team_game_stats
    do. The inner join against `games` also does double duty as the
    exhibition/All-Star filter: `games` was already restricted to real
    franchise games during the original bootstrap, so any staged row whose
    (zero-padded) nba_game_id isn't a real game there is simply dropped
    rather than requiring separate gameType filtering here."""
    staged = _staged_count(engine, "player_game_stats")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO player_game_stats (
                    game_id, player_id, team_id, minutes, points, rebounds,
                    assists, steals, blocks, turnovers,
                    fg_made, fg_attempted, fg3_made, fg3_attempted, ft_made, ft_attempted
                )
                SELECT g.id, p.id, t.id, s.minutes, s.points, s.rebounds,
                       s.assists, s.steals, s.blocks, s.turnovers,
                       s.fg_made, s.fg_attempted, s.fg3_made, s.fg3_attempted, s.ft_made, s.ft_attempted
                FROM {STAGING_SCHEMA}.player_game_stats s
                JOIN games g ON g.nba_game_id = s.nba_game_id
                JOIN players p ON p.nba_player_id = s.nba_player_id
                JOIN teams t ON t.nba_team_id = s.nba_team_id
                ON CONFLICT (game_id, player_id) DO NOTHING
                """
            )
        )
    return staged, result.rowcount


def load_team_game_stats(engine: Engine) -> tuple[int, int]:
    staged = _staged_count(engine, "team_game_stats")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO team_game_stats (game_id, team_id, points, rebounds, assists, turnovers)
                SELECT g.id, t.id, s.points, s.rebounds, s.assists, s.turnovers
                FROM {STAGING_SCHEMA}.team_game_stats s
                JOIN games g ON g.nba_game_id = s.nba_game_id
                JOIN teams t ON t.nba_team_id = s.nba_team_id
                ON CONFLICT (game_id, team_id) DO NOTHING
                """
            )
        )
    return staged, result.rowcount


def load_play_by_play(engine: Engine) -> tuple[int, int]:
    """The game join is INNER (an event with no resolvable game is
    meaningless); the three player joins and the team join are LEFT, since
    many events genuinely have no player/team (period markers, timeouts)
    -- nba_player2_id/nba_player3_id/nba_team_id are already NULL for those
    rows (see clean.py's _zero_as_null), and an INNER join there would
    silently drop every such row instead of loading it with a NULL FK."""
    staged = _staged_count(engine, "play_by_play")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                INSERT INTO play_by_play (
                    game_id, sequence, period, clock, event_type, sub_type, description,
                    player_id, player2_id, player3_id, team_id,
                    score_home, score_away, shot_x, shot_y, shot_distance, shot_made
                )
                SELECT g.id, s.sequence, s.period, s.clock, s.event_type, s.sub_type, s.description,
                       p1.id, p2.id, p3.id, t.id,
                       s.score_home, s.score_away, s.shot_x, s.shot_y, s.shot_distance, s.shot_made
                FROM {STAGING_SCHEMA}.play_by_play s
                JOIN games g ON g.nba_game_id = s.nba_game_id
                LEFT JOIN players p1 ON p1.nba_player_id = s.nba_player_id
                LEFT JOIN players p2 ON p2.nba_player_id = s.nba_player2_id
                LEFT JOIN players p3 ON p3.nba_player_id = s.nba_player3_id
                LEFT JOIN teams t ON t.nba_team_id = s.nba_team_id
                ON CONFLICT (game_id, sequence) DO NOTHING
                """
            )
        )
    return staged, result.rowcount
