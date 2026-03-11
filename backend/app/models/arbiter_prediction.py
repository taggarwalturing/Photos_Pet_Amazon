"""Arbiter prediction model — stores per-image classification results."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from app.database import Base


class ArbiterPrediction(Base):
    __tablename__ = "arbiter_predictions"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(String(500), nullable=False, index=True, unique=True)
    # image_id = filename without extension, e.g. "1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2"
    predictions = Column(JSON)          # {"lighting": "well_lit", "viewpoint": "front_eye_level", ...}
    reasoning = Column(JSON)            # {"lighting": {"gemini": "...", "openai": "...", ...}, ...}
    model_used = Column(String(100))    # e.g. "gemini+openai+o3"
    status = Column(String(50), default="pending")   # pending / completed / failed
    error_message = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
