from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class AnnotatorCategory(Base):
    __tablename__ = "annotator_categories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "category_id", name="uq_annotator_category"),
    )

    # Relationships
    user = relationship("User", back_populates="assigned_categories")
    category = relationship("Category", back_populates="assigned_annotators")
