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
    is_improper = Column(Boolean, default=False, nullable=False, index=True)
    improper_reason = Column(Text, nullable=True)
    marked_improper_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_improper_at = Column(DateTime(timezone=True), nullable=True)
    
    # Biometric compliance tracking
    compliance_processed = Column(Boolean, default=False, nullable=False, index=True)
    compliance_status = Column(String(50), nullable=True, index=True)
    human_faces_detected = Column(Integer, default=0, nullable=False)
    processing_log = Column(Text, nullable=True)
    
    # AI-generated image detection
    is_ai_generated = Column(Boolean, nullable=True, default=False)
    ai_detection_confidence = Column(Integer, nullable=True)
    marked_ai_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_ai_at = Column(DateTime(timezone=True), nullable=True)
    
    # Human visibility tracking
    human_visible = Column(Boolean, nullable=True)
    human_visible_marked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    human_visible_marked_at = Column(DateTime(timezone=True), nullable=True)
    
    # Dual URL storage for version control
    original_url = Column(Text, nullable=True)
    processed_url = Column(Text, nullable=True)
    is_using_processed = Column(Boolean, default=True, nullable=False)
    processing_method = Column(String(50), nullable=True)
    
    # Manual blur tracking by annotators
    manually_blurred = Column(Boolean, default=False, nullable=False)
    blur_regions = Column(JSON, nullable=True)
    manually_blurred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    manually_blurred_at = Column(DateTime(timezone=True), nullable=True)
    annotated_blur_url = Column(Text, nullable=True)

    # Google Drive source tracking
    source_drive_folder_id = Column(String(255), nullable=True, index=True)
    image_drive_id = Column(String(255), nullable=True, index=True)  # Unique Google Drive hex ID — primary display identifier

    # Key status flags (user-requested clean columns)
    is_manually_modified = Column(Boolean, default=False, nullable=False)  # True if modified by reviewer or annotator (blur/restore)
    is_programmatically_blurred = Column(Boolean, default=False, nullable=False)  # True if blurred by pipeline (biometric compliance)
    is_duplicate = Column(Boolean, default=False, nullable=False)  # True if image is a content duplicate
    parent_image = Column(String(255), nullable=True)  # Filename of parent image if this is a duplicate
    image_path = Column(Text, nullable=True)  # Current image file path on disk

    # Annotator blur/restore tracking
    is_blurred_annotator = Column(Boolean, default=False, nullable=False)
    is_restore_annotator = Column(Boolean, default=False, nullable=False)
    restored_by_annotator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    restored_at_annotator = Column(DateTime(timezone=True), nullable=True)

    # Deliverable image tracking (populated after reviewer approves all annotations)
    deliverable_image_path = Column(Text, nullable=True)

    # Arbiter classifier AI-predicted labels (pre-filled for annotators)
    arbiter_labels = Column(JSON, nullable=True)
    arbiter_classified_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    annotations = relationship("Annotation", back_populates="image")
    final_labels = relationship("FinalLabel", back_populates="image", uselist=False)
    improper_marker = relationship("User", foreign_keys=[marked_improper_by])
    ai_marker = relationship("User", foreign_keys=[marked_ai_by])
    human_visible_marker = relationship("User", foreign_keys=[human_visible_marked_by])
    edit_requests = relationship("EditRequest", back_populates="image")
    manual_blur_user = relationship("User", foreign_keys=[manually_blurred_by])
    restore_user = relationship("User", foreign_keys=[restored_by_annotator_id])
    
    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_compliance_status', 'compliance_processed', 'compliance_status'),
        Index('idx_improper_created', 'is_improper', 'created_at'),
    )
