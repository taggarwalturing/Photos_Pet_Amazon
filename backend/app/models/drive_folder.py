from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base


class DriveFolder(Base):
    __tablename__ = "drive_folders"

    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(String(255), unique=True, nullable=False, index=True)  # Google Drive folder ID
    folder_name = Column(String(500), nullable=True)  # Human-readable name (from Excel or auto-detected)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Pipeline processing status
    status = Column(String(50), default="pending", nullable=False)  # pending, downloading, processing, completed, failed
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    
    # Stats (populated after pipeline runs)
    total_in_drive = Column(Integer, default=0)
    downloaded_count = Column(Integer, default=0)
    unique_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    blurred_count = Column(Integer, default=0)
    clean_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    
    # Batch tracking
    batch_number = Column(Integer, nullable=True, index=True)

    # Metadata
    notes = Column(Text, nullable=True)
    error_log = Column(Text, nullable=True)
