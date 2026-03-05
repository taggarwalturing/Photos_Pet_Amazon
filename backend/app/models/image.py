from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=True)  # Original filename before conversion (e.g. IMG.HEIC → IMG.jpg)
    original_format = Column(String(20), nullable=True)     # Original file format (e.g. "HEIC", "PNG") if converted
    url = Column(String(1024), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Improper image tracking
    is_improper = Column(Boolean, default=False, nullable=False, index=True)  # Added index
    improper_reason = Column(Text, nullable=True)
    marked_improper_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_improper_at = Column(DateTime(timezone=True), nullable=True)
    
    # Biometric compliance tracking
    compliance_processed = Column(Boolean, default=False, nullable=False, index=True)  # Added index
    compliance_status = Column(String(50), nullable=True, index=True)  # Added index
    human_faces_detected = Column(Integer, default=0, nullable=False)
    processing_log = Column(Text, nullable=True)
    
    # AI-generated image detection
    is_ai_generated = Column(Boolean, nullable=True, default=False)  # True=AI, False=Real, None=Unknown; default Real
    ai_detection_confidence = Column(Integer, nullable=True)  # 0-100
    marked_ai_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_ai_at = Column(DateTime(timezone=True), nullable=True)
    
    # Human visibility tracking
    human_visible = Column(Boolean, nullable=True)  # True=Human visible, False=No human, None=Unknown
    human_visible_marked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    human_visible_marked_at = Column(DateTime(timezone=True), nullable=True)
    
    # Dual URL storage for version control
    original_url = Column(Text, nullable=True)  # Original unprocessed image
    processed_url = Column(Text, nullable=True)  # Processed (blurred) version
    is_using_processed = Column(Boolean, default=True, nullable=False)  # Which version is currently shown
    processing_method = Column(String(50), nullable=True)  # 'opencv', 'openai', 'manual'
    
    # Manual blur tracking by annotators
    manually_blurred = Column(Boolean, default=False, nullable=False)  # Track if annotator manually blurred
    blur_regions = Column(JSON, nullable=True)  # Store blur region coordinates as JSON array
    manually_blurred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    manually_blurred_at = Column(DateTime(timezone=True), nullable=True)
    annotated_blur_url = Column(Text, nullable=True)  # URL to manually blurred version

    # Arbiter classifier AI-predicted labels (pre-filled for annotators)
    arbiter_labels = Column(JSON, nullable=True)  # {"lighting": "dusk_dawn", "viewpoint": "ground_level", ...}
    arbiter_classified_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    annotations = relationship("Annotation", back_populates="image")
    improper_marker = relationship("User", foreign_keys=[marked_improper_by])
    ai_marker = relationship("User", foreign_keys=[marked_ai_by])
    human_visible_marker = relationship("User", foreign_keys=[human_visible_marked_by])
    edit_requests = relationship("EditRequest", back_populates="image")
    manual_blur_user = relationship("User", foreign_keys=[manually_blurred_by])
    
    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_compliance_status', 'compliance_processed', 'compliance_status'),
        Index('idx_improper_created', 'is_improper', 'created_at'),
    )
