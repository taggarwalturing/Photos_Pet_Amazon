"""
Utility functions for managing image delivery to GCS.

GCS bucket structure:
  gs://amazon-photo-pets/
    input/{folder_id}/{filename}                 — raw originals (added manually)
    annotated/{folder_id}/clean/{filename}       — clean images (no blur)
    annotated/{folder_id}/blur/{filename}        — blurred images (pipeline or manual)

With the 3-table schema, "approved" is determined by Image.review_status == "approved".
Annotation data lives in Image.annotations (JSON) rather than separate tables.
"""
import shutil
from pathlib import Path
from sqlalchemy.orm import Session

from app.models.image import Image
from app.models.user import User
from app.utils.gcs import (
    copy_blob,
    gcs_path as build_gcs_path,
    blob_exists,
    delete_blob as gcs_delete,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
IMAGE_CACHE_DIR = BACKEND_DIR / "image_cache"


def _get_ws() -> Path:
    from app.utils import get_pipeline_workspace
    return get_pipeline_workspace()


# Kept for backwards compat
PIPELINE_WORKSPACE = _get_ws()


def _get_image_source_path(image: Image) -> Path | None:
    """Find the current image file on disk (cache → deliverable → raw download)."""
    source_path = None
    folder_id = image.source_folder_id or "unknown"

    # Priority 1: Image cache (has the latest version — blurred or restored)
    cache_path = IMAGE_CACHE_DIR / f"{image.id}.jpg"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        source_path = cache_path

    # Priority 2: Annotated GCS path (local fallback)
    if not source_path and image.gcs_annotated_path:
        blur_path = PIPELINE_WORKSPACE / image.gcs_annotated_path
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
    Copy the current image version to GCS annotated/clean/ or annotated/blur/.

    For GCS images:
      - Blurred → ``annotated/{folder_id}/blur/{filename}``
      - Clean   → ``annotated/{folder_id}/clean/{filename}``
    For legacy images: copies from local disk to deliverable/.

    Called when:
      1. Reviewer approves the image (review_status → approved).
      2. Reviewer/Admin modifies (blur/restore) an already-delivered image.
    """
    folder_id = image.source_folder_id or "unknown"
    is_blurred = bool(
        image.is_blurred_annotator
        or image.manually_blurred
        or image.is_programmatically_blurred
    )
    is_modified = bool(
        image.is_blurred_annotator
        or image.is_restore_annotator
        or image.manually_blurred
    )

    # Determine target stage: blur or clean
    dst_stage = "blur" if is_blurred else "clean"

    # GCS path: copy to annotated/{folder_id}/clean/ or blur/
    if (image.url or "").startswith("gs://") and folder_id != "unknown":
        src_stage = image.gcs_folder or "input"
        if src_stage == dst_stage:
            # Already in correct annotated sub-folder — just update DB
            image.gcs_folder = dst_stage
            image.deliverable_image_path = build_gcs_path(folder_id, image.filename, dst_stage)
            image.is_manually_modified = is_modified
            db.commit()
            print(f"[Deliverable] ✅ Image {image.id} ({image.filename}) already in GCS annotated/{dst_stage}/ (modified={is_modified})")
            return

        # Copy from current stage to target stage
        try:
            src_gcs = build_gcs_path(folder_id, image.filename, src_stage)
            dst_gcs = build_gcs_path(folder_id, image.filename, dst_stage)
            if blob_exists(src_gcs):
                copy_blob(src_gcs, dst_gcs)
            else:
                # Fall back to input/ as source
                input_gcs = build_gcs_path(folder_id, image.filename, "input")
                copy_blob(input_gcs, dst_gcs)

            # Delete old copy from the opposite stage (clean↔blur)
            old_stage = "clean" if dst_stage == "blur" else "blur"
            try:
                old_gcs = build_gcs_path(folder_id, image.filename, old_stage)
                gcs_delete(old_gcs)
            except Exception:
                pass

            image.gcs_folder = dst_stage
            image.deliverable_image_path = build_gcs_path(folder_id, image.filename, dst_stage)
            image.is_manually_modified = is_modified
            db.commit()
            print(f"[Deliverable] ✅ Image {image.id} ({image.filename}) → GCS annotated/{dst_stage}/ (modified={is_modified})")
            return
        except Exception as e:
            print(f"[Deliverable] GCS copy to annotated/{dst_stage}/ failed: {e}, falling back to local")

    # Local fallback
    final_dir = PIPELINE_WORKSPACE / "folders" / folder_id / "deliverable"
    final_dir.mkdir(parents=True, exist_ok=True)

    source_path = _get_image_source_path(image)
    if not source_path:
        print(f"[Deliverable] WARNING: Could not find source image for image_id={image.id} ({image.filename})")
        return

    dest_path = final_dir / image.filename
    try:
        shutil.copy2(str(source_path), str(dest_path))
    except Exception as e:
        print(f"[Deliverable] ERROR moving image {image.id}: {e}")
        return

    relative_path = str(dest_path.relative_to(PIPELINE_WORKSPACE))
    image.deliverable_image_path = relative_path
    image.is_manually_modified = is_modified
    db.commit()
    print(f"[Deliverable] ✅ Image {image.id} ({image.filename}) → deliverable/ (modified={is_modified})")


# Keep backward compatibility alias
move_image_to_biometric_folder = move_image_to_deliverable


def check_and_deliver_image(image_id: int, db: Session):
    """
    After an annotation is approved, check if the image review_status == "approved".
    If so, copy the current image version to deliverable/.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        return

    # Only deliver if image is fully approved
    if image.review_status != "approved":
        return

    # Only deliver if annotations exist
    if not image.annotations or image.annotation_status != "completed":
        return

    move_image_to_deliverable(image, db)


def update_deliverable_if_delivered(image_id: int, db: Session):
    """
    If an image has already been delivered (review approved),
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
