from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "annotator"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    assigned_category_ids: list[int] = []
    # Progress stats
    assigned_image_count: int = 0
    completed_annotations: int = 0
    total_annotations_needed: int = 0  # assigned_images * assigned_categories
    improper_marked_count: int = 0

    class Config:
        from_attributes = True


class AssignCategoriesRequest(BaseModel):
    category_ids: list[int]
