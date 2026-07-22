from __future__ import annotations

from datetime import date

from sqlalchemy import Date, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    nba_player_id: Mapped[int] = mapped_column(unique=True, index=True, nullable=False)

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    birthdate: Mapped[date | None] = mapped_column(Date)
    height_in: Mapped[int | None] = mapped_column(SmallInteger)
    weight_lb: Mapped[int | None] = mapped_column(SmallInteger)
    draft_year: Mapped[int | None] = mapped_column(SmallInteger)
