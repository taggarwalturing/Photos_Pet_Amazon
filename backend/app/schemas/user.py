from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re


class UserCreate(BaseModel):
    username: str  # Must be a Turing ID (e.g. xyz@turing.com)
    password: str
    full_name: Optional[str] = None
    role: str = "annotator"

    @field_validator("username")
    @classmethod
    def validate_turing_id(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Turing ID is required")
        if not re.match(r"^[a-z0-9._+-]+@turing\.com$", v):
            raise ValueError("Username must be a valid Turing ID (e.g. xyz@turing.com)")
        return v


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
    today_image_count: int = 0  # distinct images annotated today

    class Config:
        from_attributes = True


class AssignCategoriesRequest(BaseModel):
    category_ids: list[int]
