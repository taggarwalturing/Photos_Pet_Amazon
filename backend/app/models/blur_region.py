from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BlurRegion(Base):
    __tablename__ = "blur_regions"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)

    blur_strength = Column(Integer, default=51)
    sigma = Column(Float, default=40.0)
    method = Column(String(50), default="roi-blur")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    image = relationship("Image", back_populates="blur_regions")
    creator = relationship("User", foreign_keys=[created_by])
