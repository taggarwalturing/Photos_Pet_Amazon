from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class AnnotatorImageAssignment(Base):
    """
    Tracks which images are assigned to which annotators.
    Each image can only be assigned to ONE annotator (no duplicates).
    """
    __tablename__ = "annotator_image_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    # Each image can only be assigned to ONE user (global, not per-category)
    __table_args__ = (
        UniqueConstraint("image_id", name="uq_image_assignment"),
    )

    # Relationships
    user = relationship("User", backref="image_assignments")
    image = relationship("Image", backref="assignments")
