"""Image schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ImageResponse(BaseModel):
    id: int
    filename: str
    url: Optional[str] = None
    source_folder_id: Optional[str] = None
    annotation_status: str = "pending"
    review_status: Optional[str] = None
    is_duplicate: bool = False
    gcs_folder: str = "input"
    created_at: datetime

    class Config:
        from_attributes = True
