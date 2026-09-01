from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(20))  # meta | google | tiktok
    platform_page_id: Mapped[str] = mapped_column(String(100))

    __table_args__ = (UniqueConstraint("platform", "platform_page_id"),)

    raw_ads: Mapped[list["RawAd"]] = relationship(back_populates="competitor")


class RawAd(Base):
    __tablename__ = "raw_ads"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    ad_id: Mapped[str] = mapped_column(String(100))
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))

    creative_type: Mapped[str] = mapped_column(String(20), default="unknown")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    media_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("platform", "ad_id"),)

    competitor: Mapped["Competitor"] = relationship(back_populates="raw_ads")
    classification: Mapped[Optional["Classification"]] = relationship(
        back_populates="ad", uselist=False
    )

    @property
    def lifespan_days(self) -> int:
        return (self.last_seen - self.first_seen).days


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_ad_id: Mapped[int] = mapped_column(ForeignKey("raw_ads.id"), unique=True)
    angle: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ad: Mapped["RawAd"] = relationship(back_populates="classification")


class SavedAd(Base):
    __tablename__ = "saved_ads"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_ad_id: Mapped[int] = mapped_column(ForeignKey("raw_ads.id"), unique=True)
    storage_path: Mapped[str] = mapped_column(String(1000))
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ad: Mapped["RawAd"] = relationship()


class FailedAd(Base):
    __tablename__ = "failed_ads"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_ad_id: Mapped[int] = mapped_column(ForeignKey("raw_ads.id"), unique=True)
    lifespan_days: Mapped[int] = mapped_column()
    disappeared_at: Mapped[date] = mapped_column(Date)
    flagged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)

    ad: Mapped["RawAd"] = relationship()


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    type: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read: Mapped[bool] = mapped_column(Boolean, default=False)

    competitor: Mapped["Competitor"] = relationship()
