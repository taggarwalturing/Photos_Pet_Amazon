"""
Utility functions for managing image delivery to deliverable/ folder
and populating the final_labels table when all annotations are approved.

Simplified folder structure:
  pipeline_workspace/folders/{folder_id}/
    ├── 01_downloaded_from_drive/   ← raw downloads
    └── deliverable/                ← final images served to UI
"""
import shutil
from pathlib import Path
from sqlalchemy.orm import Session, joinedload

from app.models.image import Image
from app.models.annotation import Annotation, AnnotationSelection
from app.models.final_label import FinalLabel
from app.models.option import Option
from app.models.category import Category
from app.models.user import User

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
PIPELINE_WORKSPACE = BACKEND_DIR / "master_pipeline" / "pipeline_workspace"
IMAGE_CACHE_DIR = BACKEND_DIR / "image_cache"


def _get_image_source_path(image: Image) -> Path | None:
    """Find the current image file on disk (cache → blur file → deliverable → raw download)."""
    source_path = None
    folder_id = image.source_drive_folder_id or "unknown"

    # Priority 1: Image cache (has the latest version - blurred or restored)
    cache_path = IMAGE_CACHE_DIR / f"{image.id}.jpg"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        source_path = cache_path

    # Priority 2: Annotated blur file
    if not source_path and image.annotated_blur_url:
        blur_path = PIPELINE_WORKSPACE / image.annotated_blur_url
        if blur_path.exists() and blur_path.stat().st_size > 0:
            source_path = blur_path

    # Priority 3: Deliverable (per-folder)
    if not source_path:
        folder_final = PIPELINE_WORKSPACE / "folders" / folder_id / "deliverable" / image.filename
        if folder_final.exists() and folder_final.stat().st_size > 0:
            source_path = folder_final

    # Priority 4: Raw download (per-folder)
    if not source_path:
        raw_path = PIPELINE_WORKSPACE / "folders" / folder_id / "01_downloaded_from_drive" / image.filename
        if raw_path.exists() and raw_path.stat().st_size > 0:
            source_path = raw_path

    # Priority 5: Search all per-folder workspaces
    if not source_path:
        folders_dir = PIPELINE_WORKSPACE / "folders"
        if folders_dir.is_dir():
            for fd in sorted(folders_dir.iterdir()):
                if fd.is_dir():
                    for sub in ["deliverable", "01_downloaded_from_drive"]:
                        candidate = fd / sub / image.filename
                        if candidate.exists() and candidate.stat().st_size > 0:
                            source_path = candidate
                            break
                if source_path:
                    break

    return source_path


def move_image_to_deliverable(image: Image, db: Session):
    """
    Copy the current image version to deliverable/.
    
    Called when:
      1. Reviewer approves all annotations for the image.
      2. Reviewer/Admin modifies (blur/restore) the image from the dashboard.
    """
    folder_id = image.source_drive_folder_id or "unknown"
    final_dir = PIPELINE_WORKSPACE / "folders" / folder_id / "deliverable"
    final_dir.mkdir(parents=True, exist_ok=True)

    # Find the current image bytes
    source_path = _get_image_source_path(image)
    if not source_path:
        print(f"[Deliverable] WARNING: Could not find source image for image_id={image.id} ({image.filename})")
        return

    dest_path = final_dir / image.filename

    try:
        # Copy current version to deliverable/
        shutil.copy2(str(source_path), str(dest_path))
    except Exception as e:
        print(f"[Deliverable] ERROR moving image {image.id}: {e}")
        return

    # Determine if the image was modified by the annotator/admin
    is_modified = bool(image.is_blurred_annotator or image.is_restore_annotator or image.manually_blurred)

    # Store relative path from pipeline_workspace root
    relative_path = str(dest_path.relative_to(PIPELINE_WORKSPACE))

    # Update image record
    image.deliverable_image_path = relative_path
    image.is_manually_modified = is_modified
    db.commit()

    print(f"[Deliverable] ✅ Image {image.id} ({image.filename}) → deliverable/ (modified={is_modified})")


# Keep backward compatibility alias
move_image_to_biometric_folder = move_image_to_deliverable


# ── Category name → column name mapping ──────────────────────────
CATEGORY_COLUMN_MAP = {
    "Lighting Variation": "lighting_variation",
    "Angle & Perspective Variation": "angle_perspective_variation",
    "Environmental Context Variation": "environmental_context_variation",
    "Occlusion & Partial Visibility": "occlusion_partial_visibility",
    "Activity & Motion": "activity_motion",
    "Multi-Pet Disambiguation": "multi_pet_disambiguation",
}


def populate_final_label(image_id: int, db: Session):
    """
    Populate or update the final_labels row for an image.
    Reads approved annotations, resolves selected option labels,
    and stores them in the per-category columns.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        return

    # Load all completed+approved annotations for this image
    approved_annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.status == "completed",
            Annotation.review_status == "approved",
        )
        .options(
            joinedload(Annotation.selections),
            joinedload(Annotation.category),
            joinedload(Annotation.annotator),
            joinedload(Annotation.reviewer),
        )
        .all()
    )

    if not approved_annotations:
        return

    # Build option id → label lookup
    option_ids = set()
    for ann in approved_annotations:
        for sel in ann.selections:
            option_ids.add(sel.option_id)

    option_label_map = {}
    if option_ids:
        options = db.query(Option).filter(Option.id.in_(option_ids)).all()
        option_label_map = {o.id: o.label for o in options}

    # Prepare final label data
    label_data = {}
    reviewer_name = None
    annotator_name = None
    latest_reviewed_at = None

    for ann in approved_annotations:
        cat_name = ann.category.name if ann.category else None
        col_name = CATEGORY_COLUMN_MAP.get(cat_name)
        if col_name:
            # Join selected option labels with "; " separator
            selected_labels = []
            for sel in ann.selections:
                lbl = option_label_map.get(sel.option_id, f"option_{sel.option_id}")
                selected_labels.append(lbl)
            label_data[col_name] = "; ".join(selected_labels) if selected_labels else None

        # Track reviewer and annotator names (use most recent)
        if ann.reviewer and (not latest_reviewed_at or (ann.reviewed_at and ann.reviewed_at > latest_reviewed_at)):
            reviewer_name = ann.reviewer.username
            latest_reviewed_at = ann.reviewed_at
        if ann.annotator:
            annotator_name = ann.annotator.username

    # Upsert the FinalLabel row
    final_label = db.query(FinalLabel).filter(FinalLabel.image_id == image_id).first()
    if not final_label:
        final_label = FinalLabel(image_id=image_id)
        db.add(final_label)

    # Set category columns
    for col_name, label_value in label_data.items():
        setattr(final_label, col_name, label_value)

    final_label.reviewer_name = reviewer_name
    final_label.annotator_name = annotator_name
    final_label.approved_at = latest_reviewed_at

    db.commit()
    print(f"[FinalLabel] ✅ Image {image_id} ({image.filename}) — labels saved")


def check_and_deliver_image(image_id: int, db: Session):
    """
    After an annotation is approved, check if ALL annotations for this image
    are now approved. If so:
    1. Copy the current image version to deliverable/
    2. Populate the final_labels table with approved labels
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        return

    # Check if ALL annotations for this image are approved
    all_annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.status == "completed",
        )
        .all()
    )

    if not all_annotations:
        return

    # Every completed annotation must be approved
    all_approved = all(a.review_status == "approved" for a in all_annotations)
    if not all_approved:
        return

    move_image_to_deliverable(image, db)
    populate_final_label(image_id, db)


def update_deliverable_if_delivered(image_id: int, db: Session):
    """
    If an image has already been delivered (all annotations approved),
    re-copy it to deliverable/ with the latest version.
    Called when admin/reviewer modifies an already-approved image.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        return

    # Only re-copy if the image was already delivered
    if not image.deliverable_image_path:
        return

    move_image_to_deliverable(image, db)


# Backward compatibility alias
update_biometric_if_delivered = update_deliverable_if_delivered
