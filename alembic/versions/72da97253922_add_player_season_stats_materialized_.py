"""add player_season_stats materialized view

Revision ID: 72da97253922
Revises: c84aa018ff7e
Create Date: 2026-07-21 12:29:50.560237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72da97253922'
down_revision: Union[str, Sequence[str], None] = 'c84aa018ff7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Grouped by game_type (not just "Regular Season" by default) since
    # games.game_type now includes more than the original three values
    # (Play-In Tournament, NBA Cup, All-Star Game, etc. -- see
    # ingestion/bootstrap/column_maps.py) -- callers filter to whichever
    # game_type they want rather than the view baking in an assumption.
    # Shooting percentages are SUM(made)/SUM(attempted) across the season,
    # not AVG(per-game percentage) -- averaging per-game percentages would
    # weight a 1-for-1 game the same as a 10-for-20 game, which is wrong.
    op.execute(
        """
        CREATE MATERIALIZED VIEW player_season_stats AS
        SELECT
            p.id AS player_id,
            p.full_name,
            s.id AS season_id,
            s.season_label,
            g.game_type,
            COUNT(*) AS games_played,
            ROUND(AVG(pgs.minutes), 1) AS avg_minutes,
            ROUND(AVG(pgs.points), 1) AS avg_points,
            ROUND(AVG(pgs.rebounds), 1) AS avg_rebounds,
            ROUND(AVG(pgs.assists), 1) AS avg_assists,
            ROUND(AVG(pgs.steals), 1) AS avg_steals,
            ROUND(AVG(pgs.blocks), 1) AS avg_blocks,
            ROUND(AVG(pgs.turnovers), 1) AS avg_turnovers,
            SUM(pgs.fg_made) AS total_fg_made,
            SUM(pgs.fg_attempted) AS total_fg_attempted,
            ROUND(SUM(pgs.fg_made)::numeric / NULLIF(SUM(pgs.fg_attempted), 0), 3) AS fg_pct,
            SUM(pgs.fg3_made) AS total_fg3_made,
            SUM(pgs.fg3_attempted) AS total_fg3_attempted,
            ROUND(SUM(pgs.fg3_made)::numeric / NULLIF(SUM(pgs.fg3_attempted), 0), 3) AS fg3_pct,
            SUM(pgs.ft_made) AS total_ft_made,
            SUM(pgs.ft_attempted) AS total_ft_attempted,
            ROUND(SUM(pgs.ft_made)::numeric / NULLIF(SUM(pgs.ft_attempted), 0), 3) AS ft_pct
        FROM player_game_stats pgs
        JOIN players p ON p.id = pgs.player_id
        JOIN games g ON g.id = pgs.game_id
        JOIN seasons s ON s.id = g.season_id
        GROUP BY p.id, p.full_name, s.id, s.season_label, g.game_type
        """
    )
    # Required for REFRESH MATERIALIZED VIEW CONCURRENTLY (see
    # db/refresh_views.py), which needs a unique index to compare old vs
    # new rows without locking readers out during refresh.
    op.execute(
        "CREATE UNIQUE INDEX ix_player_season_stats_unique "
        "ON player_season_stats (player_id, season_id, game_type)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS player_season_stats")
