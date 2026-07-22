"""nba_api wrappers for the sync (Phase 3): retry/backoff + rate limiting.

IMPORTANT: this sandbox's outbound access to stats.nba.com is blocked by an
Akamai WAF (confirmed: TCP/TLS connects fine, but the HTTP response never
arrives, or comes back as an explicit 403 "Access Denied" from
errors.edgesuite.net on cdn.nba.com) -- these functions were written
against nba_api's own installed source (endpoint signatures, response
parser field lists) since a live call can't be made from here. Run this
from a network where stats.nba.com isn't blocked (e.g. a home/residential
connection) -- see run_sync.py for the full story.
"""

from __future__ import annotations

import time

import pandas as pd
from nba_api.stats.endpoints import boxscoretraditionalv3, leaguegamefinder
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_RETRYABLE = retry_if_exception_type((ConnectionError, TimeoutError, OSError))


@retry(retry=_RETRYABLE, stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=2, max=60))
def fetch_games_since(date_from: str, date_to: str) -> pd.DataFrame:
    """One call, not per-game -- LeagueGameFinder returns every team's row
    for every game in the date range directly, no pagination needed for a
    range this small (a few weeks to a season)."""
    finder = leaguegamefinder.LeagueGameFinder(
        player_or_team_abbreviation="T",
        league_id_nullable="00",
        date_from_nullable=date_from,
        date_to_nullable=date_to,
    )
    return finder.league_game_finder_results.get_data_frame()


@retry(retry=_RETRYABLE, stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=2, max=60))
def _fetch_one_box_score(game_id: str) -> pd.DataFrame:
    box = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
    df = box.player_stats.get_data_frame()
    df["gameId"] = game_id
    return df


def fetch_player_box_scores(game_ids: list[str], request_delay_seconds: float = 1.2) -> pd.DataFrame:
    """One request per game -- this is the slow, rate-limit-sensitive part.
    request_delay_seconds paces requests to avoid tripping nba_api's own
    documented rate limits; tenacity above handles transient failures on
    top of that pacing, not instead of it."""
    frames = []
    for i, game_id in enumerate(game_ids):
        if i > 0:
            time.sleep(request_delay_seconds)
        frames.append(_fetch_one_box_score(game_id))
    if not frames:
        return pd.DataFrame(columns=["gameId"])
    return pd.concat(frames, ignore_index=True)
