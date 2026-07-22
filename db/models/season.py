from __future__ import annotations

from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class Season(Base):
    """Surrogate PK applied here too, even though there's no nba.com integer
    ID for a season -- for FK-join consistency/performance with `games`.
    `season_label` retains the natural business key (e.g. '2025-26') used
    when calling nba_api endpoints in Phase 3.
    """

    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_label: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
