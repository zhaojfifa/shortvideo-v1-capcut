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
    if "publish_status" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN publish_status VARCHAR(32)"
        )
    if "publish_provider" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN publish_provider VARCHAR(32)"
        )
    if "publish_key" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN publish_key TEXT")
    if "publish_url" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN publish_url TEXT")
    if "published_at" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN published_at TEXT")
    if "priority" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN priority INTEGER")
    if "assignee" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN assignee VARCHAR(64)")
    if "ops_notes" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN ops_notes TEXT")
    if "pack_key" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN pack_key TEXT")
    if "pack_type" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN pack_type VARCHAR(32)")
    if "pack_status" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN pack_status VARCHAR(32)")
    if "mm_audio_key" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN mm_audio_key TEXT")
    if "subtitle_structure_path" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN subtitle_structure_path TEXT")
    if "subtitles_status" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN subtitles_status VARCHAR(32)")
    if "subtitles_key" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN subtitles_key TEXT")
    if "subtitles_error" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN subtitles_error TEXT")
    if "scenes_key" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN scenes_key TEXT")
    if "scenes_status" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN scenes_status VARCHAR(32)")
    if "scenes_count" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN scenes_count INTEGER")
    if "scenes_error" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN scenes_error TEXT")
    if "selected_tool_ids" not in columns:
        alter_statements.append(
            "ALTER TABLE tasks ADD COLUMN selected_tool_ids TEXT"
        )
    if "pipeline_config" not in columns:
        alter_statements.append("ALTER TABLE tasks ADD COLUMN pipeline_config TEXT")

    if not alter_statements:
        return

    with engine.begin() as conn:
        for stmt in alter_statements:
            conn.execute(text(stmt))


def ensure_provider_config_table(engine) -> None:
    """Ensure provider_config table exists (idempotent)."""

    inspector = inspect(engine)
    if "provider_config" in inspector.get_table_names():
        return

    create_sql = """
    CREATE TABLE provider_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT
    )
    """
    with engine.begin() as conn:
        conn.execute(text(create_sql))


def get_provider_config_map(engine) -> dict[str, str]:
    inspector = inspect(engine)
    if "provider_config" not in inspector.get_table_names():
        return {}

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT key, value FROM provider_config")).fetchall()
    return {row[0]: row[1] for row in rows}


def set_provider_config_map(engine, updates: dict[str, str]) -> dict[str, str]:
    inspector = inspect(engine)
    if "provider_config" not in inspector.get_table_names():
        ensure_provider_config_table(engine)

    with engine.begin() as conn:
        for key, value in updates.items():
            conn.execute(
                text(
                    """
                    INSERT INTO provider_config (key, value, updated_at)
                    VALUES (:key, :value, datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET value = :value, updated_at = datetime('now')
                    """
                ),
                {"key": key, "value": value},
            )
    return get_provider_config_map(engine)


def get_db():
    from sqlalchemy.orm import Session

    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# ============================================================
# Repository Dependency Factory (PR-0B Fix)
# ============================================================
from fastapi import Depends
from sqlalchemy.orm import Session
# 确保导入了刚才写的适配器和接口
from gateway.app.adapters.repo_sql import SQLAlchemyTaskRepository
from gateway.ports.repository import ITaskRepository

# 假设 get_db 已经在这个文件里定义了，如果没定义，请确保从 session 模块导入
# from .session import get_db 

def get_task_repository(db: Session = Depends(get_db)) -> ITaskRepository:
    """
    FastAPI Dependency: 获取 Task Repository 实例
    """
    return SQLAlchemyTaskRepository(db)
