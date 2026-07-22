from __future__ import annotations

from sqlalchemy import ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


class TeamGameStats(Base):
    __tablename__ = "team_game_stats"
    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_team_game_stats_game_id_team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)

    points: Mapped[int | None] = mapped_column(SmallInteger)
    rebounds: Mapped[int | None] = mapped_column(SmallInteger)
    assists: Mapped[int | None] = mapped_column(SmallInteger)
    turnovers: Mapped[int | None] = mapped_column(SmallInteger)

    game: Mapped["Game"] = relationship()
    team: Mapped["Team"] = relationship()
