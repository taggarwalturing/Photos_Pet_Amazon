from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AnnotationSave(BaseModel):
    selected_option_ids: list[int] = []
    is_duplicate: Optional[bool] = None
    status: str = "completed"  # completed / skipped
    time_spent_seconds: int = 0  # cumulative time spent on this annotation


class AnnotationResponse(BaseModel):
    id: int
    image_id: int
    annotator_id: int
    category_id: int
    is_duplicate: Optional[bool]
    status: str
    review_status: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    selected_option_ids: list[int] = []
    time_spent_seconds: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnnotationTask(BaseModel):
    """What the annotator sees: image + category + options + existing annotation"""
    image_id: int
    image_url: str
    image_filename: str
    category_id: int
    category_name: str
    options: list[dict]  # [{id, label, is_typical}]
    current_annotation: Optional[AnnotationResponse] = None
    image_index: int  # 0-based position in the queue
    total_images: int


class ProgressResponse(BaseModel):
    category_id: int
    category_name: str
    annotator_id: int
    annotator_username: str
    total_images: int
    completed: int
    skipped: int
    in_progress: int
    pending: int


class ImageCompletionResponse(BaseModel):
    image_id: int
    image_filename: str
    image_url: str
    total_categories: int
    completed_categories: int
    category_details: list[dict]  # [{category_id, category_name, status, annotator_username}]
    is_fully_complete: bool


class ReviewApproveRequest(BaseModel):
    review_note: Optional[str] = None


class ReviewUpdateRequest(BaseModel):
    """Admin edits the selections and approves."""
    selected_option_ids: list[int]
    is_duplicate: Optional[bool] = None
    review_note: Optional[str] = None


class ReviewAnnotationDetail(BaseModel):
    id: int
    image_id: int
    image_url: str
    image_filename: str
    annotator_id: int
    annotator_username: str
    category_id: int
    category_name: str
    is_duplicate: Optional[bool]
    status: str
    review_status: Optional[str]
    review_note: Optional[str]
    reviewed_by_username: Optional[str]
    reviewed_at: Optional[datetime]
    selected_options: list[dict]  # [{id, label}]
    all_options: list[dict]  # [{id, label, is_typical}] — all options in category for editing
    time_spent_seconds: int = 0
    rework_time_seconds: int = 0
    is_rework: bool = False
    created_at: datetime
    updated_at: datetime


# ── Review Table View schemas ─────────────────────────────────────

class ReviewTableCell(BaseModel):
    """One cell in the table = one annotation for (image, category)."""
    annotation_id: int
    selected_options: list[dict]  # [{id, label}]
    all_options: list[dict]  # [{id, label, is_typical}]
    annotator_username: str
    is_duplicate: Optional[bool]
    review_status: Optional[str]
    time_spent_seconds: int = 0
    rework_time_seconds: int = 0
    is_rework: bool = False


class ReviewTableRow(BaseModel):
    """One row = one image with annotations keyed by category_id."""
    image_id: int
    image_url: str
    image_filename: str
    annotations: dict[str, ReviewTableCell]  # key = str(category_id)


class ReviewTableCategory(BaseModel):
    id: int
    name: str


class ReviewTableResponse(BaseModel):
    images: list[ReviewTableRow]
    categories: list[ReviewTableCategory]
    total_images: int
    page: int
    page_size: int
