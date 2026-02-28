from sqlalchemy import Column, Integer, Boolean, String, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    annotator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    is_duplicate = Column(Boolean, nullable=True)  # NULL = not answered
    status = Column(String(20), nullable=False, default="in_progress")  # in_progress, completed, skipped
    time_spent_seconds = Column(Integer, nullable=False, default=0)  # cumulative time spent annotating
    human_validated = Column(Boolean, nullable=False, default=False)  # True after human validates/submits (model predictions start as False)
    is_rework = Column(Boolean, nullable=False, default=False)  # True if this is a rework submission
    rework_time_seconds = Column(Integer, nullable=False, default=0)  # time spent on rework
    review_status = Column(String(20), nullable=True)  # NULL=not reviewed, approved, rejected
    review_note = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "image_id", "annotator_id", "category_id",
            name="uq_image_annotator_category"
        ),
    )

    # Relationships
    image = relationship("Image", back_populates="annotations")
    annotator = relationship("User", back_populates="annotations", foreign_keys=[annotator_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    category = relationship("Category", back_populates="annotations")
    selections = relationship(
        "AnnotationSelection", back_populates="annotation", cascade="all, delete-orphan"
    )


class AnnotationSelection(Base):
    __tablename__ = "annotation_selections"

    id = Column(Integer, primary_key=True, index=True)
    annotation_id = Column(
        Integer, ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False
    )
    option_id = Column(Integer, ForeignKey("options.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("annotation_id", "option_id", name="uq_annotation_option"),
    )

    # Relationships
    annotation = relationship("Annotation", back_populates="selections")
    option = relationship("Option", back_populates="selections")
