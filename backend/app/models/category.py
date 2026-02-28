from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    display_order = Column(Integer, nullable=False, default=0)

    # Relationships
    options = relationship(
        "Option", back_populates="category", order_by="Option.display_order"
    )
    assigned_annotators = relationship(
        "AnnotatorCategory", back_populates="category", cascade="all, delete-orphan"
    )
    annotations = relationship("Annotation", back_populates="category")
