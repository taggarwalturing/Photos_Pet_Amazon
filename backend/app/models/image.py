"""Consolidated Image model — single table for images, annotations, and review."""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON,
    ForeignKey, Index, func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(String(500), index=True)              # filename stem without extension
    filename = Column(String(500), nullable=False)          # hex_id.jpeg
    url = Column(String(1000))
    source_folder_id = Column(String(200), index=True)      # GCS folder ID

    # ── GCS paths ──
    gcs_input_path = Column(String(500))
    gcs_annotated_path = Column(String(500))
    gcs_folder = Column(String(50), default="input")        # input / clean / blur

    # ── Deduplication ──
    is_duplicate = Column(Boolean, default=False, index=True)
    parent_image_id = Column(Integer, ForeignKey("images.id"), nullable=True)

    # ── Pipeline ──
    pipeline_status = Column(String(50), default="pending")
    compliance_status = Column(String(50))
    human_faces_detected = Column(Integer, default=0)

    # ── AI detection ──
    is_ai_generated = Column(Boolean, default=False)
    ai_detection_confidence = Column(Integer)
    marked_ai_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_ai_at = Column(DateTime)

    # ── Human visibility ──
    human_visible = Column(Boolean, nullable=True)
    human_visible_marked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    human_visible_marked_at = Column(DateTime)

    # ── Blur / modification tracking ──
    is_programmatically_blurred = Column(Boolean, default=False)
    is_manually_modified = Column(Boolean, default=False)
    is_using_processed = Column(Boolean, default=True)
    manually_blurred = Column(Boolean, default=False)
    manually_blurred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    manually_blurred_at = Column(DateTime)
    is_blurred_annotator = Column(Boolean, default=False)
    is_restore_annotator = Column(Boolean, default=False)
    blur_regions = Column(JSON)                              # [{x,y,width,height}, ...]
    processed_url = Column(String(1000))
    processing_method = Column(String(50))

    # ── Annotation (consolidated — replaces Annotation + AnnotationSelection tables) ──
    annotation_status = Column(String(50), default="pending")  # pending / in_progress / completed
    annotations = Column(JSON)                               # {"cat_key": {"selected_option_ids": [...]}, ...}
    annotated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    annotated_at = Column(DateTime)

    # ── Annotation history (append-only audit log) ──
    # Each entry: {"ts": ISO timestamp, "by": user_id, "role": "annotator"|"reviewer"|"ai",
    #              "action": "annotate"|"edit"|"rework", "annotations": {...snapshot...}}
    annotation_history = Column(JSON, default=list)

    # ── Review (image-level — replaces per-annotation review) ──
    review_status = Column(String(50))                       # null / pending / approved / rework_requested / rework_completed
    review_note = Column(Text)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime)

    # ── Improper ──
    is_improper = Column(Boolean, default=False)
    improper_reason = Column(Text)
    marked_improper_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_improper_at = Column(DateTime)

    # ── Assignment ──
    assigned_annotator = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # ── Locking ──
    locked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    locked_at = Column(DateTime)

    # ── Deliverable ──
    deliverable_image_path = Column(String(500))

    # ── Arbiter labels (pre-filled from classifier) ──
    arbiter_labels = Column(JSON)                            # {"lighting": {"final": "well_lit", ...}, ...}

    # ── VLM Validation ──
    vlm_validation = Column(JSON)                            # {"aligned": bool, "contradictions": [...], "category_details": {...}}
    vlm_validated_at = Column(DateTime)

    # ── Legacy / mapping columns (kept for pipeline import) ──
    original_filename = Column(String(500))
    image_drive_id = Column(String(200))

    # ── Timestamps ──
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # ── Relationships ──
    parent_image = relationship("Image", remote_side=[id], foreign_keys=[parent_image_id])
    annotator = relationship("User", foreign_keys=[annotated_by], lazy="joined")
    reviewer_user = relationship("User", foreign_keys=[reviewed_by], lazy="select")
    assigned_user = relationship("User", foreign_keys=[assigned_annotator], lazy="select")

    # ── Indexes ──
    __table_args__ = (
        Index("ix_images_annotation_status", "annotation_status"),
        Index("ix_images_review_status", "review_status"),
        Index("ix_images_annotated_by", "annotated_by"),
        Index("ix_images_source_folder", "source_folder_id"),
        Index("ix_images_gcs_folder", "gcs_folder"),
        Index("ix_images_assigned_annotator", "assigned_annotator"),
    )
