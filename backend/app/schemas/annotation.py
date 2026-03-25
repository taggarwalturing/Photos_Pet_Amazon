"""Annotation & review schemas — image-level (no separate Annotation table)."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── Annotation Save ──────────────────────────────────────────────
class AnnotationSavePayload(BaseModel):
    """
    Payload for PUT /annotator/images/{image_id}/annotations
    annotations: {cat_id_str: {selected_option_ids: [int, ...], is_duplicate: bool|null}}
    """
    annotations: dict[str, dict]  # cat_id → {selected_option_ids, is_duplicate}
    is_rework: bool = False


# ── Review ───────────────────────────────────────────────────────
class ReviewApproveRequest(BaseModel):
    review_note: Optional[str] = None


class ReviewUpdateRequest(BaseModel):
    """Admin edits the label selections and approves the image."""
    annotations: dict[str, dict]  # cat_id → {selected_option_ids: [...]}
    review_note: Optional[str] = None


class ReworkRequest(BaseModel):
    reason: str


class ImageReworkRequest(BaseModel):
    reason: str


# ── Review Table View schemas ────────────────────────────────────
class ReviewTableCategoryCell(BaseModel):
    """One cell in the review table: labels for a single category on an image."""
    selected_options: list[dict]       # [{id, label}]
    all_options: list[dict]            # [{id, label, is_typical}]
    label_source: str = "pending"      # "human" | "ai" | "approved" | "pending"


class ReviewTableRow(BaseModel):
    """One row = one image with annotation data per category."""
    image_id: int
    image_url: str
    image_filename: str
    annotation_status: str = "pending"
    annotations: dict[str, ReviewTableCategoryCell]  # key = str(category_id)
    # Annotator info
    annotated_by_username: Optional[str] = None
    # Review info
    review_status: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_by_username: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    # Blur-related
    is_blurred: bool = False
    compliance_status: Optional[str] = None
    manually_blurred: bool = False
    is_blurred_annotator: bool = False
    is_restore_annotator: bool = False
    # Deliverable
    deliverable_image_path: Optional[str] = None
    is_manually_modified: Optional[bool] = None
    gcs_folder: str = "input"
    # Folder
    source_folder_id: Optional[str] = None


class ReviewTableCategory(BaseModel):
    id: int
    name: str


class ReviewTableResponse(BaseModel):
    images: list[ReviewTableRow]
    categories: list[ReviewTableCategory]
    total_images: int
    page: int
    page_size: int
