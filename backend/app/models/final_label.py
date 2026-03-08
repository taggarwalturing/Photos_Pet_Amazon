"""
FinalLabel model — stores the reviewer-approved labels for each image.

One row per image, with a column for each annotation category containing
the final approved label(s). Also tracks reviewer and annotator names.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class FinalLabel(Base):
    __tablename__ = "final_labels"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Per-category approved labels (column per category)
    lighting_variation = Column(String(255), nullable=True)                # Category 1: Lighting Variation
    angle_perspective_variation = Column(String(255), nullable=True)       # Category 2: Angle & Perspective Variation
    environmental_context_variation = Column(String(255), nullable=True)   # Category 3: Environmental Context Variation
    occlusion_partial_visibility = Column(String(255), nullable=True)      # Category 4: Occlusion & Partial Visibility
    activity_motion = Column(String(255), nullable=True)                   # Category 5: Activity & Motion
    multi_pet_disambiguation = Column(String(255), nullable=True)          # Category 6: Multi-Pet Disambiguation

    # Who approved / annotated
    reviewer_name = Column(String(255), nullable=True)    # Username of the reviewer who approved
    annotator_name = Column(String(255), nullable=True)   # Username of the annotator who annotated

    # Timestamps
    approved_at = Column(DateTime(timezone=True), nullable=True)   # When the last annotation was approved
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    image = relationship("Image", back_populates="final_labels")
