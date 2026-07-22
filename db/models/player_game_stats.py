from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"
    __table_args__ = (
        # Business rule: one stat line per player per game.
        UniqueConstraint("game_id", "player_id", name="uq_player_game_stats_game_id_player_id"),
        # Spec-mandated composite index for rolling-average window queries
        # ordered by game date (player_id leading, since queries filter to
        # one player first, then order/join on game_id -> games.game_date).
        Index("ix_player_game_stats_player_id_game_id", "player_id", "game_id"),
        CheckConstraint("points >= 0", name="points_nonneg"),
        CheckConstraint("minutes >= 0", name="minutes_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)

    minutes: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    points: Mapped[int | None] = mapped_column(SmallInteger)
    rebounds: Mapped[int | None] = mapped_column(SmallInteger)
    assists: Mapped[int | None] = mapped_column(SmallInteger)
    steals: Mapped[int | None] = mapped_column(SmallInteger)
    blocks: Mapped[int | None] = mapped_column(SmallInteger)
    turnovers: Mapped[int | None] = mapped_column(SmallInteger)
    fg_made: Mapped[int | None] = mapped_column(SmallInteger)
    fg_attempted: Mapped[int | None] = mapped_column(SmallInteger)
    fg3_made: Mapped[int | None] = mapped_column(SmallInteger)
    fg3_attempted: Mapped[int | None] = mapped_column(SmallInteger)
    ft_made: Mapped[int | None] = mapped_column(SmallInteger)
    ft_attempted: Mapped[int | None] = mapped_column(SmallInteger)

    game: Mapped["Game"] = relationship()
    player: Mapped["Player"] = relationship()
    team: Mapped["Team"] = relationship()

    # No stored derived columns (e.g. PRA). The Phase-4 agent computes
    # points+rebounds+assists etc. as SELECT expressions at query time;
    # keep this table normalized.
