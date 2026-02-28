from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    url = Column(String(1024), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Improper image tracking
    is_improper = Column(Boolean, default=False, nullable=False)
    improper_reason = Column(Text, nullable=True)
    marked_improper_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_improper_at = Column(DateTime(timezone=True), nullable=True)
    
    # Biometric compliance tracking
    compliance_processed = Column(Boolean, default=False, nullable=False)
    compliance_status = Column(String(50), nullable=True)  # 'clean', 'processed', 'needs_reprocess', 'flagged'
    human_faces_detected = Column(Integer, default=0, nullable=False)
    processing_log = Column(Text, nullable=True)
    
    # AI-generated image detection
    is_ai_generated = Column(Boolean, nullable=True)  # True=AI, False=Real, None=Unknown
    ai_detection_confidence = Column(Integer, nullable=True)  # 0-100
    marked_ai_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_ai_at = Column(DateTime(timezone=True), nullable=True)
    
    # Dual URL storage for version control
    original_url = Column(Text, nullable=True)  # Original unprocessed image
    processed_url = Column(Text, nullable=True)  # Processed (blurred) version
    is_using_processed = Column(Boolean, default=True, nullable=False)  # Which version is currently shown
    processing_method = Column(String(50), nullable=True)  # 'opencv', 'openai', 'manual'

    # Relationships
    annotations = relationship("Annotation", back_populates="image")
    improper_marker = relationship("User", foreign_keys=[marked_improper_by])
    ai_marker = relationship("User", foreign_keys=[marked_ai_by])
    edit_requests = relationship("EditRequest", back_populates="image")
