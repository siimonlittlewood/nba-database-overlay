from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    nba_team_id: Mapped[int] = mapped_column(unique=True, index=True, nullable=False)

    abbreviation: Mapped[str] = mapped_column(String(10), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    conference: Mapped[str | None] = mapped_column(String(10))
    division: Mapped[str | None] = mapped_column(String(20))

    home_games: Mapped[list["Game"]] = relationship(
        foreign_keys="Game.home_team_id", back_populates="home_team"
    )
    away_games: Mapped[list["Game"]] = relationship(
        foreign_keys="Game.away_team_id", back_populates="away_team"
    )
