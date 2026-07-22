"""Source-to-target column mappings for the nba_api sync (Phase 3).

Built by reading nba_api's own installed source directly (this sandbox's
outbound access to stats.nba.com is blocked by an Akamai WAF -- see
run_sync.py's module docstring -- so these were confirmed against
nba_api/stats/endpoints/_parsers/boxscoretraditionalv3.py's field lists,
not a live response). Verify against a real response on first local run;
see the "VERIFY ON FIRST RUN" notes below for the specific things that
couldn't be confirmed from here.

Game/season id scheme: nba.com ids are already correctly zero-padded
strings when returned directly by the live API (unlike the Kaggle export
in ingestion/bootstrap, which stripped leading zeros on CSV export) --
zfill(10) is applied anyway as a cheap defensive no-op, not because it's
expected to be needed.

SEASON_ID (from LeagueGameFinder) is 5 chars: 1-digit season-type code +
4-digit season start year (e.g. "22025" = Regular Season, 2025-26) -- the
exact same scheme already parsed for the wyattowalsh dataset in
ingestion/bootstrap/clean.py's _season_label(), just with a 4-digit year
instead of that dataset's split encoding. Season-type codes 1/2/4 (Pre
Season/Regular Season/Playoffs) are well-established and match the
existing games.game_type values already in the table. Codes 3 (All-Star)
and 5 (Play-In) are documented by the nba_api community but VERIFY ON
FIRST RUN since they were never seen in a live response from here.
"""

from __future__ import annotations

SEASON_TYPE_BY_CODE = {
    "1": "Pre Season",
    "2": "Regular Season",
    "3": "All-Star",  # VERIFY ON FIRST RUN
    "4": "Playoffs",
    "5": "Play-In Tournament",  # VERIFY ON FIRST RUN
}

# LeagueGameFinder(player_or_team_abbreviation="T") returns one row per
# team per game -- covers both `games` (paired home/away rows) and
# `team_game_stats` (each row is already one team's box score line).
GAME_FINDER_RENAME = {
    "GAME_ID": "nba_game_id",
    "GAME_DATE": "game_date",
    "TEAM_ID": "nba_team_id",
    "SEASON_ID": "season_id",
    "MATCHUP": "matchup",  # "vs." = home, "@" = away -- parsed, not renamed as-is
    "PTS": "points",
    "REB": "rebounds",
    "AST": "assists",
    "TOV": "turnovers",
}

# BoxScoreTraditionalV3 PlayerStats -- headers confirmed directly from
# nba_api/stats/endpoints/_parsers/boxscoretraditionalv3.py's
# PLAYER_METADATA_FIELDS + TRADITIONAL_STATS_FIELDS tuples.
# "minutes" format VERIFY ON FIRST RUN -- V3 endpoints have been known to
# return ISO-8601 durations (e.g. "PT34M12.00S") rather than V2's "MM:SS";
# clean.py's parse_box_v3_minutes() handles both, but confirm which one
# actually comes back and simplify if only one format is ever seen.
PLAYER_BOX_RENAME = {
    "personId": "nba_player_id",
    "teamId": "nba_team_id",
    "minutes": "minutes",
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
# gameId isn't a rename -- it's a top-level field on the boxscore response,
# attached to every player row identically, zero-padded like nba_game_id
# elsewhere in this project.
