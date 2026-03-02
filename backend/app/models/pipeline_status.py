"""
Pipeline Status Tracking Model
===============================

Tracks master pipeline execution progress for real-time UI updates.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, Text
from app.database import Base
from datetime import datetime


class PipelineRun(Base):
    """Track pipeline execution progress and statistics"""
    __tablename__ = "pipeline_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="pending", index=True)  # pending, running, completed, failed
    stage = Column(String, default="idle")  # idle, download, deduplicate, biometric, consolidate
    
    # Overall progress
    total_images = Column(Integer, default=0)
    processed_images = Column(Integer, default=0)
    failed_images = Column(Integer, default=0)
    pending_images = Column(Integer, default=0)
    
    # Deduplication stats
    unique_images = Column(Integer, default=0)
    duplicate_images = Column(Integer, default=0)
    duplicate_clusters = Column(Integer, default=0)
    
    # Biometric stats
    images_with_faces = Column(Integer, default=0)
    images_without_faces = Column(Integer, default=0)
    screenshots_skipped = Column(Integer, default=0)
    
    # Progress tracking
    current_stage_progress = Column(Float, default=0.0)  # 0.0 to 100.0
    overall_progress = Column(Float, default=0.0)
    
    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_completion = Column(DateTime, nullable=True)
    
    # Errors
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Metadata
    config = Column(JSON, nullable=True)  # Pipeline configuration used
    logs = Column(JSON, nullable=True)  # Stage-by-stage logs
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
