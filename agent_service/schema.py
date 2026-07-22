"""The get_schema tool's return value: a hand-curated description of the
database, not a raw information_schema dump. Curated on purpose -- this
is the one place to bake in the domain knowledge this project accumulated
during ETL (coverage caveats, which table to prefer for which question,
what's a computed expression vs. a stored column) so the agent's queries
and answers reflect it directly, instead of it living only in project
memory/docs the model never sees.
"""

from __future__ import annotations

from db.config import get_settings

BASE_SCHEMA_DESCRIPTION = """
All tables are Postgres, accessed read-only. Season labels look like '2025-26'.
game_type is one of: 'Regular Season', 'Playoffs', 'Pre Season'/'Preseason',
'Play-In Tournament', 'NBA Cup'/'NBA Emirates Cup', 'All-Star Game'.

teams(id, nba_team_id, abbreviation, city, name, conference, division)
  One row per current franchise (30 rows). Relocated/renamed franchises
  (e.g. Seattle SuperSonics -> OKC Thunder) share one persistent id.

players(id, nba_player_id, full_name, birthdate, height_in, weight_lb, draft_year)
  Bio/identity only -- no stats live here.

seasons(id, season_label, start_date, end_date)

games(id, nba_game_id, season_id, game_date, game_type, home_team_id,
      away_team_id, home_score, away_score)

team_game_stats(id, game_id, team_id, points, rebounds, assists, turnovers)
  One row per team per game.

player_game_stats(id, game_id, player_id, team_id, minutes, points, rebounds,
                   assists, steals, blocks, turnovers, fg_made, fg_attempted,
                   fg3_made, fg3_attempted, ft_made, ft_attempted)
  One row per player per game -- only for games the player actually played
  (DNPs are not rows here at all, not zero-stat rows). This table
  deliberately has NO stored derived stats (no PRA column, no per-game
  shooting percentage column) -- compute them as SELECT expressions, e.g.
  (points + rebounds + assists) AS pra, or
  fg_made::numeric / NULLIF(fg_attempted, 0) AS fg_pct.

player_season_stats (MATERIALIZED VIEW -- prefer this over aggregating
  player_game_stats yourself for season-level questions; it already
  exists and is kept current)
  Columns: player_id, full_name, season_id, season_label, game_type,
  games_played, avg_minutes, avg_points, avg_rebounds, avg_assists,
  avg_steals, avg_blocks, avg_turnovers, total_fg_made, total_fg_attempted,
  fg_pct, total_fg3_made, total_fg3_attempted, fg3_pct, total_ft_made,
  total_ft_attempted, ft_pct.
  fg_pct/fg3_pct/ft_pct are season-long SUM(made)/SUM(attempted), the
  correct way to compute a season shooting percentage -- never average
  per-game percentages together, that over-weights low-volume games.
  Grouped by game_type, so Regular Season and Playoffs are separate rows
  for the same player-season -- filter to game_type = 'Regular Season'
  unless the question is specifically about playoffs.

"""

PLAY_BY_PLAY_SCHEMA = """
play_by_play(id, game_id, sequence, period, clock, event_type, sub_type,
             description, player_id, player2_id, player3_id, team_id,
             score_home, score_away, shot_x, shot_y, shot_distance, shot_made)
  Raw event log. IMPORTANT LIMITATIONS:
  - Does not exist for any game before the 1996-97 season -- the NBA
    itself didn't track play-by-play before then. If a question needs
    event-level detail (shot charts, assist sequencing, clutch-time plays)
    for an earlier season, say so explicitly rather than returning nothing
    silently -- box-score-level stats (player_game_stats/team_game_stats)
    have no such restriction and cover all of NBA history.
  - Even from 1996-97 onward, coverage is per-game (not per-play): a game
    either has its complete event log or none of it at all. Missing games
    still have complete box scores.
  - event_type/sub_type vocabulary is NOT a single controlled taxonomy --
    it comes from two different source eras and mixes conventions (e.g.
    both "Made Shot" and "2pt" occur as distinct values for made shots,
    depending on when the game was played). Use ILIKE or an OR of known
    variants when filtering on event_type, don't assume one exact string
    covers all eras.
  - player_id/player2_id/player3_id are generic role slots whose meaning
    depends on event_type (e.g. player2 is the assister on a made shot but
    the stealer on a turnover) -- check the description/sub_type to
    disambiguate when it matters.
  - shot_x/shot_y/shot_distance are only populated for games from
    2023-06-10 onward (and the 2012-13 season, one specifically backfilled
    gap) -- NULL elsewhere, not zero.
"""

PLAY_BY_PLAY_UNAVAILABLE_NOTE = """
play_by_play: NOT AVAILABLE in this deployment (the hosted database omits
  it -- 3GB, doesn't fit a free-tier host). There is no play_by_play table
  to query here. If a question needs event-level detail (shot charts,
  assist sequencing, clutch-time plays, exact shot location), say plainly
  that this deployment doesn't have play-by-play data and only has
  box-score-level stats (player_game_stats/team_game_stats) -- which do
  cover all of NBA history for points/rebounds/assists/etc, just not
  possession-by-possession detail. Don't attempt to query a play_by_play
  table; it doesn't exist here.
"""


def get_schema() -> str:
    if get_settings().play_by_play_available:
        return BASE_SCHEMA_DESCRIPTION + PLAY_BY_PLAY_SCHEMA
    return BASE_SCHEMA_DESCRIPTION + PLAY_BY_PLAY_UNAVAILABLE_NOTE
