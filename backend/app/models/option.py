from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Option(Base):
    __tablename__ = "options"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    label = Column(String(255), nullable=False)
    is_typical = Column(Boolean, default=False)
    display_order = Column(Integer, nullable=False, default=0)

    # Relationships
    category = relationship("Category", back_populates="options")
    selections = relationship("AnnotationSelection", back_populates="option")
