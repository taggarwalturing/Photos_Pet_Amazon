from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default="annotator")  # admin / annotator
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    assigned_categories = relationship(
        "AnnotatorCategory", back_populates="user", cascade="all, delete-orphan"
    )
    annotations = relationship(
        "Annotation", back_populates="annotator", foreign_keys="[Annotation.annotator_id]"
    )
    edit_requests = relationship(
        "EditRequest", back_populates="user", foreign_keys="[EditRequest.user_id]"
    )
    notifications = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )