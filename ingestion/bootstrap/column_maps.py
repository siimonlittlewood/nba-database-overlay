"""Source-to-target column mappings for the Kaggle "wyattowalsh/basketball"
bootstrap, confirmed against the actual csv/ export (2026-07-20).

Findings that shape these mappings (see the load-order docstring in
run_bootstrap.py for the full story):
- csv/game.csv is a wide table (one row per game, home_*/away_* columns) --
  it covers `games` directly and needs a wide-to-long reshape for
  `team_game_stats` (two rows per game).
- csv/team.csv only lists the 30 current franchises. game.csv references 82
  team ids in total; the other 52 are All-Star Game constructs (e.g. "Team
  Durant") and international exhibition clubs (e.g. "Barcelona"), which
  aren't real franchises and don't belong in our `teams` dimension. Rows
  referencing a non-franchise team id are filtered out during cleaning.
- There is no per-player-per-game box score source anywhere in this
  dataset (checked both the csv/ export and the bundled nba.sqlite --
  identical 16 tables, none of them a player box score). `player_game_stats`
  is intentionally left empty by this bootstrap; Phase 3's nba_api sync
  (boxscoretraditionalv2) is the real source for it going forward.
- csv/player.csv has full identity for 4831 players; csv/common_player_info
  only has bio data (birthdate/height/weight/draft_year) for 4171 of them.
  Players are sourced from player.csv with bio fields left-joined in from
  common_player_info, so the ~660 players without bio data still get a row.
- IDs in these CSVs (game_id, season_id) have leading zeros and must be
  read as strings, not inferred as integers, or they get silently corrupted.
"""

from __future__ import annotations

TEAMS_SOURCE = "team.csv"
TEAMS_RENAME = {
    "id": "nba_team_id",
    "abbreviation": "abbreviation",
    "city": "city",
    "nickname": "name",
}

PLAYERS_SOURCE = "player.csv"
PLAYERS_RENAME = {
    "id": "nba_player_id",
    "full_name": "full_name",
}

PLAYERS_BIO_SOURCE = "common_player_info.csv"
PLAYERS_BIO_RENAME = {
    "person_id": "nba_player_id",
    "birthdate": "birthdate",
    "height": "height_in",  # "F-I" string, parsed via clean.parse_height
    "weight": "weight_lb",
    "draft_year": "draft_year",
}

GAMES_SOURCE = "game.csv"
GAMES_RENAME = {
    "game_id": "nba_game_id",
    "game_date": "game_date",
    "season_type": "game_type",
    "team_id_home": "home_nba_team_id",
    "team_id_away": "away_nba_team_id",
    "pts_home": "home_score",
    "pts_away": "away_score",
}
# season_label isn't a rename -- it's derived from season_id's 4-digit year
# suffix (season_id's leading digit encodes game type: 1=Pre Season,
# 2=Regular Season, 4=Playoffs; the year suffix is what identifies the
# season itself, consistent across all three for the same season).

# team_game_stats has no single rename dict -- it's a wide-to-long reshape
# of the same game.csv rows into two long-format rows per game (home/away),
# built directly in clean.clean_team_game_stats().

# player_game_stats comes from a SECOND Kaggle dataset --
# eoinamoore/historical-nba-data-and-player-box-scores, extracted to
# data/kaggle/box_scores/ (a sibling of csv/, not inside it). Unlike the
# wyattowalsh dataset, this one has a genuine per-player-per-game box score
# table spanning all of NBA history (1946-47 onward), so no play-by-play
# parsing or 1996-97 scope cut is needed. Its gameId column is exported as
# a bare integer with leading zeros stripped (e.g. 42500405 rather than
# 0042500405) -- reconstructed via zero-padding in clean.py, since the
# source text itself (unlike game_id in the other dataset) never had the
# zeros to begin with. Its personId/playerteamId already match this
# project's nba_player_id/nba_team_id schemes directly.
PLAYER_GAME_STATS_SOURCE = "PlayerStatistics.csv"
PLAYER_GAME_STATS_RENAME = {
    "personId": "nba_player_id",
    "playerteamId": "nba_team_id",
    "numMinutes": "minutes",
    "points": "points",
    "reboundsTotal": "rebounds",
    "assists": "assists",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "fieldGoalsMade": "fg_made",
    "fieldGoalsAttempted": "fg_attempted",
    "threePointersMade": "fg3_made",
    "threePointersAttempted": "fg3_attempted",
    "freeThrowsMade": "ft_made",
    "freeThrowsAttempted": "ft_attempted",
}
# gameId isn't a rename -- it's zero-padded into nba_game_id in
# clean.clean_player_game_stats(), since it needs reconstruction rather
# than a straight column copy.

# games/team_game_stats BACKFILL from the same box_scores/ dataset -- not a
# replacement for the wyattowalsh-sourced games/team_game_stats (those stay
# the primary source), just a gap-filler. The original bootstrap's `games`
# table turned out to have real historical holes (e.g. the entire 1960-61
# season and nearly all of 1961-62 missing) that surfaced only once this
# richer, more complete dataset's player box scores failed to join against
# them. Shaped to match the *existing* staging.games/staging.team_game_stats
# DDL exactly, so load_games()/load_team_game_stats() are reused unchanged
# -- ON CONFLICT DO NOTHING makes this purely additive against real data.
GAMES_BACKFILL_SOURCE = "Games.csv"
GAMES_BACKFILL_RENAME = {
    "gameType": "game_type",
    "hometeamId": "home_nba_team_id",
    "awayteamId": "away_nba_team_id",
    "homeScore": "home_score",
    "awayScore": "away_score",
}
# gameId -> zero-padded nba_game_id, gameDate -> game_date + a derived
# season_label (this dataset has no season_id column) -- both handled in
# clean.py rather than as straight renames.

TEAM_GAME_STATS_BACKFILL_SOURCE = "TeamStatistics.csv"
TEAM_GAME_STATS_BACKFILL_RENAME = {
    "teamId": "nba_team_id",
    "reboundsTotal": "rebounds",
    "assists": "assists",
    "turnovers": "turnovers",
    "teamScore": "points",
}
# gameId -> zero-padded into nba_game_id in clean.py. Already one row per
# team per game in this source -- unlike game.csv in the wyattowalsh
# dataset, no wide-to-long reshape is needed.

# players BACKFILL, same rationale as the games/team_game_stats backfill
# above: PlayerStatistics.csv's personId frequently doesn't resolve against
# the wyattowalsh-sourced `players` table, because that dataset was frozen
# before recent draft classes existed (confirmed: ~87% of unresolved-player
# rows are 2023-24-debut players like Victor Wembanyama) and is missing a
# smaller number of older/obscure players outright (e.g. Loy Vaught, active
# 1990-96). box_scores/Players.csv has bio data for every personId that
# appears in PlayerStatistics.csv, so it closes both gaps.
PLAYERS_BACKFILL_SOURCE = "Players.csv"
PLAYERS_BACKFILL_RENAME = {
    "personId": "nba_player_id",
    "birthDate": "birthdate",
    "heightInches": "height_in",  # already total inches here, unlike the
    "bodyWeightLbs": "weight_lb",  # wyattowalsh dataset's "F-I" height string
    "draftYear": "draft_year",
}
# firstName + lastName -> full_name isn't a rename -- it's concatenated in
# clean.py, since the target schema has a single full_name column.

# TeamHistories.csv isn't staged/loaded into any table -- it's read purely
# to build an in-memory (teamCity, teamName) -> nba_team_id lookup, used as
# a fallback in clean_player_game_stats() for the ~91k PlayerStatistics.csv
# rows where playerteamId itself is blank in the source even though
# playerteamCity/playerteamName clearly identify a real, current franchise
# (confirmed: e.g. "Milwaukee"/"Bucks" with no numeric id attached).
TEAM_HISTORY_SOURCE = "TeamHistories.csv"

# play_by_play comes from TWO non-overlapping sources, confirmed against
# the real games table:
# - wyattowalsh's csv/play_by_play.csv: covers 1996-11-01 to 2023-06-09
#   (29,818 distinct games, confirmed by resolving its game_ids against
#   `games`).
# - eoinamoore's box_scores/PlayByPlay.parquet: covers 1996-11-01 to
#   2026-04-19, but only the 2023-06-10 onward portion is loaded, to avoid
#   double-loading the ~27 already-covered seasons (user's explicit call:
#   "we already have pbp for pre-2023... don't load redundant data").
# The two sources use genuinely different vocabularies for classifying
# events (wyattowalsh: numeric eventmsgtype codes; eoinamoore: text
# actionType/subType, and its actionType values mix two historical
# conventions within the same file -- e.g. both "Made Shot" and "2pt" occur
# as distinct values for different eras). event_type is therefore NOT a
# single controlled vocabulary across sources/eras -- it's the wyattowalsh
# numeric code translated to a readable label for that source, and the
# eoinamoore actionType passed through close to as-is for the other.
# Rather than invent a unified taxonomy across inconsistent real-world
# conventions (a real risk of getting subtly wrong), description/sub_type
# preserve full source fidelity for downstream disambiguation.
PLAY_BY_PLAY_OLD_SOURCE = "play_by_play.csv"
PLAY_BY_PLAY_OLD_CUTOVER_DATE = "2023-06-10"  # eoinamoore source picks up from here

EVENTMSGTYPE_LABELS = {
    1: "Made Shot",
    2: "Missed Shot",
    3: "Free Throw",
    4: "Rebound",
    5: "Turnover",
    6: "Foul",
    7: "Violation",
    8: "Substitution",
    9: "Timeout",
    10: "Jump Ball",
    11: "Ejection",
    12: "Start of Period",
    13: "End of Period",
    18: "Instant Replay",
}
# score column is "AWAY - HOME" (confirmed: game 0029600012, LAL home/PHX
# away -- LAL's first basket changed the score to "0 - 2", so the second
# number tracks the home side). Not a rename -- split in clean.py.

PLAY_BY_PLAY_NEW_SOURCE = "PlayByPlay.parquet"
PLAY_BY_PLAY_NEW_RENAME = {
    "actionType": "event_type",
    "subType": "sub_type",
    "description": "description",
    "teamId": "nba_team_id",
    "personId": "nba_player_id",
    "period": "period",
    "clock": "clock",
    "scoreHome": "score_home",
    "scoreAway": "score_away",
    "x": "shot_x",
    "y": "shot_y",
    "shotDistance": "shot_distance",
}
# gameId -> zero-padded nba_game_id; orderNumber -> sequence; personId="0"
# and its team-id/assist-id/steal-id/block-id/foul-drawn-id siblings all
# use the same nba.com "0 means none" convention already seen in the
# wyattowalsh dataset -- all handled in clean.py, not straight renames.
# player2_id is COALESCE(assistPersonId, stealPersonId) and player3_id is
# COALESCE(blockPersonId, foulDrawnPersonId) -- at most one of each pair is
# ever populated per row (a row is either a shot or a turnover or a foul,
# not several at once), so this doesn't silently drop information.
