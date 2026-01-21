import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .db import Base


class Task(Base):
    __tablename__ = "tasks"

    # === 1. 基础身份信息 ===
    id = Column(String(64), primary_key=True, index=True)
    # [PR-0A 新增] 租户与项目隔离
    tenant_id = Column(String(64), default="default", nullable=False, index=True)
    project_id = Column(String(64), default="default", nullable=False, index=True)
    
    title = Column(String(255), nullable=True)
    source_url = Column(Text, nullable=False)
    platform = Column(String(32), nullable=True)
    account_id = Column(String(64), nullable=True)
    account_name = Column(String(255), nullable=True)

    # === 2. 配置与语言 ===
    video_type = Column(String(64), nullable=True)
    template = Column(String(64), nullable=True)
    category_key = Column(String(50), nullable=False, default="beauty")
    
    # [PR-0C 语言策略] 
    # 保留 content_lang 兼容旧数据，新增 target_lang 明确目标
    content_lang = Column(String(10), nullable=False, default="my") 
    target_lang = Column(String(10), default="my", nullable=False) 
    ui_lang = Column(String(10), nullable=False, default="en")
    
    style_preset = Column(String(50), nullable=True)
    face_swap_enabled = Column(Boolean, nullable=False, default=False)

    # === 3. 状态与产物路径 (PR-0A & v1.65) ===
    status = Column(String(32), nullable=False, default="pending")
    duration_sec = Column(Integer, nullable=True)
    thumb_url = Column(Text, nullable=True)
    
    # 核心产物 (兼容旧字段 + 补全缺失字段)
    raw_path = Column(Text, nullable=True)
    origin_srt_path = Column(Text, nullable=True)      # [新增]
    mm_srt_path = Column(Text, nullable=True)          # [新增]
    mm_audio_path = Column(Text, nullable=True)
    mm_audio_key = Column(Text, nullable=True)
    pack_path = Column(Text, nullable=True)
    pack_key = Column(Text, nullable=True)
    pack_type = Column(String(32), nullable=True)
    pack_status = Column(String(32), nullable=True)
    scenes_key = Column(Text, nullable=True)
    scenes_status = Column(String(32), nullable=True)
    scenes_count = Column(Integer, nullable=True)
    scenes_error = Column(Text, nullable=True)
    
    # v1.65 中间产物 (为下一步做准备)
    brief_path = Column(Text, nullable=True)           # [新增] brief.json
    subtitle_structure_path = Column(Text, nullable=True) # [新增] subtitles.json
    subtitles_status = Column(String(32), nullable=True)
    subtitles_key = Column(Text, nullable=True)
    subtitles_error = Column(Text, nullable=True)
    pack_manifest_path = Column(Text, nullable=True)   # [新增] pack/manifest.json

    # === 4. 发布闭环 (PR-02) ===
    publish_status = Column(String(32), nullable=True)
    publish_provider = Column(String(32), nullable=True)
    publish_key = Column(Text, nullable=True)
    publish_url = Column(Text, nullable=True)
    published_at = Column(Text, nullable=True) # 建议后续迁移为 DateTime，暂时保持 Text 兼容
    published_by = Column(String(64), nullable=True)   # [新增] 操作人

    # === 5. 运维与 Provider ===
    priority = Column(Integer, nullable=True)
    assignee = Column(String(64), nullable=True)
    ops_notes = Column(Text, nullable=True)
    selected_tool_ids = Column(Text, nullable=True)
    pipeline_config = Column(Text, nullable=True)
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
