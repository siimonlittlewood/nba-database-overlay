from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("home_team_id <> away_team_id", name="distinct_teams"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nba_game_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False, index=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # 'Regular Season' / 'Playoffs' / 'Pre Season' -- needed so rolling
    # averages and dashboard filters don't silently mix game types.
    game_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)

    season: Mapped["Season"] = relationship()
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id], back_populates="home_games")
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id], back_populates="away_games")
