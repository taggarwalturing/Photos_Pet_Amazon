from pydantic import BaseModel
from datetime import datetime


class ImageResponse(BaseModel):
    id: int
    filename: str
    url: str
    created_at: datetime

    class Config:
        from_attributes = True
