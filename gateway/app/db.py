import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shortvideo.db")

# SQLite requires check_same_thread=False for usage across threads
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_task_extra_columns(engine) -> None:
    """Ensure newly added task columns exist (idempotent, SQLite-friendly)."""

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("tasks")}

    alter_statements = []

    if "category_key" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN category_key VARCHAR(50) DEFAULT 'beauty'"
        )
    if "content_lang" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN content_lang VARCHAR(10) DEFAULT 'my'"
        )
    if "ui_lang" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN ui_lang VARCHAR(10) DEFAULT 'en'"
        )
    if "style_preset" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN style_preset VARCHAR(50)"
        )
    if "face_swap_enabled" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN face_swap_enabled BOOLEAN DEFAULT 0"
        )
    if "last_step" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN last_step VARCHAR(32)"
        )
    if "error_message" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN error_message TEXT")
    if "error_reason" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN error_reason TEXT"
        )
    if "parse_provider" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN parse_provider VARCHAR(64)"
        )
    if "subtitles_provider" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN subtitles_provider VARCHAR(64)"
        )
    if "dub_provider" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN dub_provider VARCHAR(64)"
        )
    if "pack_provider" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN pack_provider VARCHAR(64)"
        )
    if "face_swap_provider" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN face_swap_provider VARCHAR(64)"
        )

    if not alter_statements:
        return

    with engine.begin() as conn:
        for stmt in alter_statements:
            conn.execute(text(stmt))


def get_db():
    from sqlalchemy.orm import Session

    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
