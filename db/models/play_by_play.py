from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


class PlayByPlay(Base):
    """Raw event log, sourced from two non-overlapping datasets (see
    ingestion/bootstrap/column_maps.py): the wyattowalsh CSV (1996-97 to
    2023-06-09) and the eoinamoore parquet (2023-06-10 onward). The two
    sources have different native vocabularies for event classification
    (numeric eventmsgtype codes vs text actionType/subType), so event_type/
    sub_type are stored close to whatever the source actually said rather
    than forced into one invented unified taxonomy -- description carries
    full-fidelity detail regardless of source era.

    player_id/player2_id/player3_id are generic role slots (not fixed
    "shooter"/"assister"/"blocker" columns) because the role a given slot
    plays varies by event_type -- e.g. player2 is the assister on a made
    shot but the stealer on a turnover. Consumers need to branch on
    event_type to interpret them, same as the raw source data requires.
    """

    __tablename__ = "play_by_play"
    __table_args__ = (
        UniqueConstraint("game_id", "sequence", name="uq_play_by_play_game_id_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(nullable=False)
    period: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    clock: Mapped[str | None] = mapped_column(String(20))

    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    sub_type: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(String(255))

    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), index=True)
    player2_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    player3_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)

    score_home: Mapped[int | None] = mapped_column(SmallInteger)
    score_away: Mapped[int | None] = mapped_column(SmallInteger)

    # Shot detail -- only ever populated by the eoinamoore source; the
    # wyattowalsh CSV has no shot-location data.
    shot_x: Mapped[float | None] = mapped_column(Numeric(6, 2))
    shot_y: Mapped[float | None] = mapped_column(Numeric(6, 2))
    shot_distance: Mapped[int | None] = mapped_column(SmallInteger)
    shot_made: Mapped[bool | None] = mapped_column()

    game: Mapped["Game"] = relationship()
