from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class SystemSettings(Base):
    """
    Key-value store for system-wide settings.
    Used for configurable limits like max annotation time.
    """
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Default settings keys:
    # - max_annotation_time_seconds: Max time allowed for initial annotation (default: 120)
    # - max_rework_time_seconds: Max time allowed for rework annotation (default: 120)
