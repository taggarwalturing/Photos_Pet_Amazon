"""User schemas — simplified for 3-table design."""
from pydantic import BaseModel, field_validator
from typing import Optional, List
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
    assigned_image_count: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    # Computed stats (filled by the endpoint, not the ORM)
    total_images: int = 0             # total images in system
    assigned_image_count: int = 0     # how many images to assign to this annotator
    completed_annotations: int = 0    # images this user has annotated
    today_image_count: int = 0        # distinct images annotated today
    actual_assigned: int = 0          # how many images are actually assigned in DB
    assigned_folder_ids: List[str] = []  # folder_ids assigned to this annotator

    class Config:
        from_attributes = True
