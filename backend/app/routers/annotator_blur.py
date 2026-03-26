"""
Annotator blur/restore router — updated for 3-table schema.

Handles blur application, blur removal, and image restoration.
Uses GCS for image storage and Image model for all metadata.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone
from pathlib import Path
import os

from app.database import get_db
from app.models.user import User
from app.models.image import Image
from app.dependencies import get_current_user
from app.utils.blur import blur_image_regions
from app.utils.deliverable import update_biometric_if_delivered
from app.utils.gcs import (
    upload_bytes as gcs_upload_bytes,
    gcs_path as build_gcs_path,
    download_to_bytes as gcs_download,
    parse_gs_uri,
    delete_blob as gcs_delete,
)

router = APIRouter(prefix="/annotator/blur", tags=["Annotator Blur"])

# Cache directories (same as main.py proxy)
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "image_cache")
VIEW_DIR = os.path.join(CACHE_DIR, "view")
THUMB_DIR = os.path.join(CACHE_DIR, "thumbnails")

# Output folder for manually blurred images
from app.utils import get_pipeline_workspace as _get_pw


def _blur_output_dir():
    return os.path.join(str(_get_pw()), "annotated_blur")


BLUR_OUTPUT_DIR = _blur_output_dir()


def _invalidate_all_caches(image_id: int, new_bytes: bytes = None):
    """
    Invalidate (or replace) all cached versions of an image: full, view, thumb.
    If new_bytes is provided, regenerate all tiers with the new image data.
    If None, just delete all cached files.
    """
    from PIL import Image as PILImage
    import io as _io

    for d in (CACHE_DIR, VIEW_DIR, THUMB_DIR):
        os.makedirs(d, exist_ok=True)

    if new_bytes is None:
        # Just delete all cached files
        for d in (CACHE_DIR, VIEW_DIR, THUMB_DIR):
            p = os.path.join(d, f"{image_id}.jpg")
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return

    # Write full-res
    with open(os.path.join(CACHE_DIR, f"{image_id}.jpg"), "wb") as f:
        f.write(new_bytes)

    # Generate and write view (1200px)
    try:
        pil = PILImage.open(_io.BytesIO(new_bytes))
        if pil.mode in ('RGBA', 'P'):
            pil = pil.convert('RGB')
        pil.thumbnail((1200, 1200), PILImage.LANCZOS)
        buf = _io.BytesIO()
        pil.save(buf, format='JPEG', quality=85)
        with open(os.path.join(VIEW_DIR, f"{image_id}.jpg"), "wb") as f:
            f.write(buf.getvalue())
    except Exception:
        # If view generation fails, at least delete stale cache
        p = os.path.join(VIEW_DIR, f"{image_id}.jpg")
        if os.path.exists(p):
            os.remove(p)

    # Generate and write thumbnail (400px)
    try:
        pil = PILImage.open(_io.BytesIO(new_bytes))
        if pil.mode in ('RGBA', 'P'):
            pil = pil.convert('RGB')
        pil.thumbnail((400, 400), PILImage.LANCZOS)
        buf = _io.BytesIO()
        pil.save(buf, format='JPEG', quality=70)
        with open(os.path.join(THUMB_DIR, f"{image_id}.jpg"), "wb") as f:
            f.write(buf.getvalue())
    except Exception:
        p = os.path.join(THUMB_DIR, f"{image_id}.jpg")
        if os.path.exists(p):
            os.remove(p)


class BlurRegion(BaseModel):
    x: float       # normalized 0-1
    y: float       # normalized 0-1
    width: float   # normalized 0-1
    height: float  # normalized 0-1


class ApplyBlurRequest(BaseModel):
    regions: List[BlurRegion]


def _get_image_bytes(image: Image) -> bytes:
    """
    Get raw image bytes — try GCS first, then local cache, then pipeline workspace.
    """
    # 1. Try GCS (primary storage)
    url = image.url or ""
    if url.startswith("gs://"):
        try:
            _, blob_path = parse_gs_uri(url)
            return gcs_download(blob_path)
        except Exception as e:
            print(f"[Blur] GCS download failed for {image.filename}: {e}")

    # 2. Try image cache
    cache_path = os.path.join(CACHE_DIR, f"{image.id}.jpg")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "rb") as f:
            return f.read()

    # 3. Try pipeline workspace (per-folder + legacy)
    workspace = str(_get_pw())
    search_roots = []
    folders_dir = os.path.join(workspace, "folders")
    if os.path.isdir(folders_dir):
        for fd in sorted(os.listdir(folders_dir)):
            fd_path = os.path.join(folders_dir, fd)
            if os.path.isdir(fd_path):
                search_roots.append(fd_path)
    search_roots.append(workspace)

    for search_root in search_roots:
        for sub in ["deliverable", "01_downloaded_from_drive"]:
            folder = os.path.join(search_root, sub)
            if os.path.isdir(folder):
                for fname in os.listdir(folder):
                    if fname == image.filename:
                        fpath = os.path.join(folder, fname)
                        if os.path.getsize(fpath) > 0:
                            with open(fpath, "rb") as f:
                                return f.read()

    # 4. Download from URL
    import httpx
    dl_url = image.url
    if not dl_url:
        raise ValueError("No URL available for image")

    resp = httpx.get(dl_url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.content


@router.post("/apply/{image_id}")
def apply_manual_blur(
    image_id: int,
    request: ApplyBlurRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Apply manual blur regions to an image.
    Reads image from cache/workspace, applies blur server-side,
    saves to GCS annotated/blur/ and local cache, updates DB.
    """
    if current_user.role not in ("annotator", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if not request.regions:
        raise HTTPException(status_code=400, detail="No regions provided")

    os.makedirs(BLUR_OUTPUT_DIR, exist_ok=True)

    try:
        # 1. Get original image bytes (from GCS input/ or local)
        image_bytes = _get_image_bytes(image)

        # 2. Convert regions to dict list
        regions_list = [r.dict() for r in request.regions]

        # 3. Apply blur (server-side, using OpenCV + roi_blur)
        blurred_bytes = blur_image_regions(image_bytes, regions_list)

        # 4. Upload blurred image to GCS annotated/blur/ (or save locally)
        blurred_filename = f"blur_{image.id}_{image.filename}"
        if not blurred_filename.lower().endswith((".jpg", ".jpeg")):
            blurred_filename = os.path.splitext(blurred_filename)[0] + ".jpg"

        folder_id = image.source_folder_id or "unknown"
        if (image.url or "").startswith("gs://") and folder_id != "unknown":
            blur_gcs_path = build_gcs_path(folder_id, image.filename, "blur")
            gcs_upload_bytes(blurred_bytes, blur_gcs_path, content_type="image/jpeg")
            # Remove old copy from clean/
            try:
                clean_gcs = build_gcs_path(folder_id, image.filename, "clean")
                gcs_delete(clean_gcs)
            except Exception:
                pass
            image.gcs_folder = "blur"
            image.gcs_annotated_path = f"gs://{blur_gcs_path}"
            bucket_name = os.getenv("GCS_BUCKET_NAME", "amazon-photo-pets")
            image.url = f"gs://{bucket_name}/{blur_gcs_path}"
        else:
            os.makedirs(BLUR_OUTPUT_DIR, exist_ok=True)
            blurred_path = os.path.join(BLUR_OUTPUT_DIR, blurred_filename)
            with open(blurred_path, "wb") as f:
                f.write(blurred_bytes)
            image.gcs_annotated_path = f"annotated_blur/{blurred_filename}"

        # 5. Update ALL image caches (full, view, thumb) so proxy serves blurred version
        _invalidate_all_caches(image.id, blurred_bytes)

        # 6. Update database
        image.manually_blurred = True
        image.blur_regions = regions_list
        image.manually_blurred_by = current_user.id
        image.manually_blurred_at = datetime.now(timezone.utc)

        if current_user.role == "annotator":
            image.is_blurred_annotator = True
        image.is_manually_modified = True

        db.commit()
        db.refresh(image)

        # If image was already delivered, re-copy with latest version
        update_biometric_if_delivered(image.id, db)

        return {
            "success": True,
            "message": f"Blur applied to {len(regions_list)} region(s)",
            "image_id": image.id,
            "regions_count": len(regions_list),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to apply blur: {str(e)}")


@router.get("/{image_id}/regions")
def get_blur_regions(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get existing blur regions for an image."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    return {
        "image_id": image.id,
        "manually_blurred": image.manually_blurred or False,
        "regions": image.blur_regions or [],
        "blurred_by": image.manually_blurred_by,
        "blurred_at": image.manually_blurred_at,
    }


def _find_original_image_bytes(image: Image) -> bytes | None:
    """
    Find the original (unblurred) image bytes.
    For GCS images, always fetches from the input/ folder.
    Handles HEIC→JPG conversions by also checking original_filename.
    For local images, searches pipeline workspace.
    """
    folder_id = image.source_folder_id

    # 1. Try GCS input/ folder — check converted name first, then original
    if folder_id and image.filename:
        candidates = [image.filename]
        if image.original_filename and image.original_filename != image.filename:
            candidates.append(image.original_filename)

        for candidate in candidates:
            try:
                input_gcs_path = build_gcs_path(folder_id, candidate, "input")
                data = gcs_download(input_gcs_path)
                if data:
                    # HEIC/HEIF — convert to JPEG bytes so callers get a usable image
                    lower = candidate.lower()
                    if lower.endswith(('.heic', '.heif')):
                        try:
                            from PIL import Image as PILImage
                            from io import BytesIO
                            pil_img = PILImage.open(BytesIO(data))
                            if pil_img.mode != "RGB":
                                pil_img = pil_img.convert("RGB")
                            buf = BytesIO()
                            pil_img.save(buf, format="JPEG", quality=95)
                            data = buf.getvalue()
                        except Exception as conv_err:
                            print(f"[Restore] HEIC→JPEG conversion failed: {conv_err}")
                    return data
            except Exception as e:
                print(f"[Restore] GCS input/ download failed for {candidate}: {e}")

    workspace = str(_get_pw())

    # 2. Search pipeline workspace folders
    search_roots = []
    folders_dir = os.path.join(workspace, "folders")
    if os.path.isdir(folders_dir):
        for fd in sorted(os.listdir(folders_dir)):
            fd_path = os.path.join(folders_dir, fd)
            if os.path.isdir(fd_path):
                search_roots.append(fd_path)
    search_roots.append(workspace)

    for search_root in search_roots:
        search_folders = [
            os.path.join(search_root, "01_downloaded_from_drive"),
        ]
        for folder in search_folders:
            if os.path.isdir(folder):
                fpath = os.path.join(folder, image.filename)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                    with open(fpath, "rb") as f:
                        return f.read()

    return None


@router.delete("/{image_id}/blur")
def remove_blur(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Undo blur on an image — works for both manual and pipeline blurs.
    Restores the original unblurred image in the cache.
    """
    if current_user.role not in ("annotator", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # 1. Try to find the original (unblurred) image
    original_bytes = _find_original_image_bytes(image)

    if not original_bytes:
        return {
            "success": False,
            "message": "Original unblurred image not found. Cannot undo blur.",
            "had_original": False,
        }

    folder_id = image.source_folder_id or "unknown"

    # 2. Delete blurred copy from GCS annotated/blur/
    if folder_id != "unknown" and image.filename:
        try:
            gcs_blob = build_gcs_path(folder_id, image.filename, "blur")
            gcs_delete(gcs_blob)
        except Exception as e:
            print(f"Warning: Could not delete GCS annotated/blur/ blob: {e}")

    # Also delete local blur file if it exists
    if image.gcs_annotated_path and not image.gcs_annotated_path.startswith("gs://"):
        try:
            blur_path = os.path.join(str(_get_pw()), image.gcs_annotated_path)
            if os.path.exists(blur_path):
                os.remove(blur_path)
        except Exception as e:
            print(f"Warning: Could not delete blurred file: {e}")

    # 3. Replace ALL caches (full, view, thumb) with the original image
    import cv2
    import numpy as np
    arr = np.frombuffer(original_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is not None:
        _, buf = cv2.imencode(".jpg", img_cv, [cv2.IMWRITE_JPEG_QUALITY, 90])
        _invalidate_all_caches(image.id, buf.tobytes())
    else:
        _invalidate_all_caches(image.id, original_bytes)

    # 4. Upload restored (clean) version to GCS annotated/clean/
    if folder_id != "unknown" and image.filename:
        try:
            clean_gcs_dest = build_gcs_path(folder_id, image.filename, "clean")
            gcs_upload_bytes(original_bytes, clean_gcs_dest, content_type="image/jpeg")
        except Exception as e:
            print(f"Warning: Could not upload restored image to GCS annotated/clean/: {e}")

    # 5. Update database — reset to clean stage and fix URL to point to current blob
    image.manually_blurred = False
    image.blur_regions = None
    image.gcs_annotated_path = None
    image.is_using_processed = False
    image.gcs_folder = "clean"
    if folder_id != "unknown" and image.filename:
        bucket_name = os.getenv("GCS_BUCKET_NAME", "amazon-photo-pets")
        image.url = f"gs://{bucket_name}/{build_gcs_path(folder_id, image.filename, 'clean')}"

    if current_user.role == "annotator":
        image.is_restore_annotator = True
    image.is_manually_modified = True

    db.commit()

    # If image was already delivered, re-copy with latest version
    update_biometric_if_delivered(image.id, db)

    return {
        "success": True,
        "message": "Blur removed — original image restored",
        "had_original": True,
    }


@router.post("/{image_id}/restore-blur")
def restore_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Restore an image by finding the best available version.
    Priority: GCS input/ → local pipeline workspace.
    """
    if current_user.role not in ("annotator", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    restored_bytes = None
    source = None

    # 1. Try GCS input/ folder
    folder_id = image.source_folder_id
    if folder_id and image.filename:
        try:
            input_gcs = build_gcs_path(folder_id, image.filename, "input")
            restored_bytes = gcs_download(input_gcs)
            source = "gcs_input"
        except Exception:
            pass

    # 2. Try processed_url field
    if not restored_bytes and image.processed_url:
        backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        proc_path = image.processed_url.replace("file://", "")
        full_path = os.path.join(backend_dir, proc_path)
        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
            with open(full_path, "rb") as f:
                restored_bytes = f.read()
            source = "processed_url"

    # 3. Try local pipeline folders
    if not restored_bytes:
        workspace = str(_get_pw())
        search_order = ["deliverable", "01_downloaded_from_drive"]
        restore_search_roots = []
        restore_folders_dir = os.path.join(workspace, "folders")
        if os.path.isdir(restore_folders_dir):
            for fd in sorted(os.listdir(restore_folders_dir)):
                fd_path = os.path.join(restore_folders_dir, fd)
                if os.path.isdir(fd_path):
                    restore_search_roots.append(fd_path)
        restore_search_roots.append(workspace)

        for sr in restore_search_roots:
            if restored_bytes:
                break
            for sub in search_order:
                fpath = os.path.join(sr, sub, image.filename)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                    with open(fpath, "rb") as f:
                        restored_bytes = f.read()
                    source = sub
                    break

    if not restored_bytes:
        raise HTTPException(
            status_code=404,
            detail="Image not found locally or on GCS. Cannot restore.",
        )

    # Write restored version to ALL caches (full, view, thumb)
    import cv2
    import numpy as np
    arr = np.frombuffer(restored_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is not None:
        _, buf = cv2.imencode(".jpg", img_cv, [cv2.IMWRITE_JPEG_QUALITY, 90])
        _invalidate_all_caches(image.id, buf.tobytes())
    else:
        _invalidate_all_caches(image.id, restored_bytes)

    image.is_using_processed = True
    image.is_manually_modified = True
    db.commit()

    # If image was already delivered, re-copy with latest version
    update_biometric_if_delivered(image.id, db)

    return {
        "success": True,
        "message": f"Image restored from {source}",
        "source": source,
    }
