import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .db import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(64), primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    source_url = Column(Text, nullable=False)
    platform = Column(String(32), nullable=True)

    account_id = Column(String(64), nullable=True)
    account_name = Column(String(255), nullable=True)

    video_type = Column(String(64), nullable=True)
    template = Column(String(64), nullable=True)

    category_key = Column(String(50), nullable=False, default="beauty")
    content_lang = Column(String(10), nullable=False, default="my")
    ui_lang = Column(String(10), nullable=False, default="en")
    style_preset = Column(String(50), nullable=True)
    face_swap_enabled = Column(Boolean, nullable=False, default=False)

    status = Column(String(32), nullable=False, default="pending")
    duration_sec = Column(Integer, nullable=True)
    thumb_url = Column(Text, nullable=True)
    raw_path = Column(Text, nullable=True)
    mm_audio_path = Column(Text, nullable=True)
    pack_path = Column(Text, nullable=True)
    last_step = Column(String(32), nullable=True)
    error_message = Column(Text, nullable=True)
    error_reason = Column(Text, nullable=True)
    parse_provider = Column(String(64), nullable=True)
    subtitles_provider = Column(String(64), nullable=True)
    dub_provider = Column(String(64), nullable=True)
    pack_provider = Column(String(64), nullable=True)
    face_swap_provider = Column(String(64), nullable=True)

    created_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )
