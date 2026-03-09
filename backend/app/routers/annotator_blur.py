from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime
from pathlib import Path
import os
import json

from app.database import get_db
from app.models.user import User
from app.models.image import Image
from app.dependencies import get_current_user
from app.utils.blur import blur_image_regions
from app.utils.deliverable import update_biometric_if_delivered
from app.utils.gcs import upload_bytes as gcs_upload_bytes, gcs_path as build_gcs_path, download_to_bytes as gcs_download, parse_gs_uri, delete_blob as gcs_delete

router = APIRouter(prefix="/annotator/blur", tags=["Annotator Blur"])

# Cache directory (same as main.py proxy)
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "image_cache")

# Output folder for manually blurred images
from app.utils import get_pipeline_workspace as _get_pw

def _blur_output_dir():
    return os.path.join(str(_get_pw()), "annotated_blur")

BLUR_OUTPUT_DIR = _blur_output_dir()


class BlurRegion(BaseModel):
    x: float       # normalized 0-1
    y: float        # normalized 0-1
    width: float    # normalized 0-1
    height: float   # normalized 0-1


class ApplyBlurRequest(BaseModel):
    regions: List[BlurRegion]


def _get_image_bytes(image: Image) -> bytes:
    """
    Get raw image bytes — try GCS first, then local cache, then pipeline workspace,
    then download from Google Drive URL.
    """
    # 1. Try GCS (primary storage for new images)
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

    # 3. Try pipeline workspace (original or processed) — per-folder + legacy
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
    dl_url = image.original_url or image.url
    if not dl_url:
        raise ValueError("No URL available for image")

    if "drive.google.com" in dl_url:
        import re
        file_id = None
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', dl_url)
        if match:
            file_id = match.group(1)
        if not file_id:
            match = re.search(r'id=([a-zA-Z0-9_-]+)', dl_url)
            if match:
                file_id = match.group(1)
        if file_id:
            dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"

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
    saves to annotated_blur folder, updates DB.
    """
    if current_user.role not in ("annotator", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if not request.regions:
        raise HTTPException(status_code=400, detail="No regions provided")

    # Create output folder
    os.makedirs(BLUR_OUTPUT_DIR, exist_ok=True)

    try:
        # 1. Get original image bytes (from GCS input/ or local)
        image_bytes = _get_image_bytes(image)

        # 2. Convert regions to dict list
        regions_list = [r.dict() for r in request.regions]

        # 3. Apply blur (server-side, using OpenCV + roi_blur)
        blurred_bytes = blur_image_regions(image_bytes, regions_list)

        # 4. Upload blurred image to GCS annotated/ folder (or save locally as fallback)
        blurred_filename = f"blur_{image.id}_{image.filename}"
        if not blurred_filename.lower().endswith(('.jpg', '.jpeg')):
            blurred_filename = os.path.splitext(blurred_filename)[0] + '.jpg'

        if (image.url or "").startswith("gs://") and image.source_drive_folder_id:
            blur_gcs_path = build_gcs_path(image.source_drive_folder_id, image.filename, "blur")
            gcs_upload_bytes(blurred_bytes, blur_gcs_path, content_type="image/jpeg")
            # Remove old copy from clean/ (image is now in blur/)
            try:
                clean_gcs = build_gcs_path(image.source_drive_folder_id, image.filename, "clean")
                gcs_delete(clean_gcs)
            except Exception:
                pass
            image.gcs_folder = "blur"
            image.annotated_blur_url = f"gs://{blur_gcs_path}"
        else:
            os.makedirs(BLUR_OUTPUT_DIR, exist_ok=True)
            blurred_path = os.path.join(BLUR_OUTPUT_DIR, blurred_filename)
            with open(blurred_path, "wb") as f:
                f.write(blurred_bytes)
            image.annotated_blur_url = f"annotated_blur/{blurred_filename}"

        # 5. Update the image cache so the proxy serves the blurred version
        cache_path = os.path.join(CACHE_DIR, f"{image.id}.jpg")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(blurred_bytes)

        # 6. Update database
        image.manually_blurred = True
        image.blur_regions = regions_list
        image.manually_blurred_by = current_user.id
        image.manually_blurred_at = datetime.utcnow()

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


def _download_from_google_drive(filename: str) -> bytes | None:
    """
    Re-download an image from Google Drive by searching for it by filename.
    Uses the Google Drive folder configured in .env.
    """
    try:
        from app.main import get_drive_service
        from app.config import settings
        import io as _io
        from googleapiclient.http import MediaIoBaseDownload

        service = get_drive_service()
        folder_id = getattr(settings, 'GOOGLE_DRIVE_FOLDER_ID', None)
        if not folder_id:
            return None

        # Search by filename
        query = f"name = '{filename}' and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            spaces='drive',
        ).execute()
        files = results.get('files', [])

        if not files:
            print(f"[Restore] '{filename}' not found in Google Drive")
            return None

        file_id = files[0]['id']
        print(f"[Restore] Downloading '{filename}' (id={file_id}) from Google Drive…")

        request = service.files().get_media(fileId=file_id)
        buf = _io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)
        data = buf.read()
        if len(data) > 0:
            return data
        return None
    except Exception as e:
        print(f"[Restore] Google Drive download failed: {e}")
        return None


def _find_original_image_bytes(image: Image) -> bytes | None:
    """
    Find the original (unblurred) image bytes.
    For GCS images, always fetches from the input/ folder.
    For local images, searches pipeline workspace.
    """
    # 1. Try GCS input/ folder (always has the original)
    if image.source_drive_folder_id and image.filename:
        try:
            input_gcs_path = build_gcs_path(image.source_drive_folder_id, image.filename, "input")
            return gcs_download(input_gcs_path)
        except Exception as e:
            print(f"[Restore] GCS input/ download failed: {e}")

    workspace = str(_get_pw())

    if image.original_url:
        orig_path = image.original_url.replace("file://", "").replace("gs://", "")
        is_post_blur_path = "deliverable" in orig_path or "annotated" in orig_path
        if not is_post_blur_path and not orig_path.startswith("gs://"):
            backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
            full_path = os.path.join(backend_dir, orig_path)
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                with open(full_path, "rb") as f:
                    return f.read()

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

    gdrive_bytes = _download_from_google_drive(image.filename)
    if gdrive_bytes:
        return gdrive_bytes

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
        # SAFETY: Don't destroy the cache if we can't find the original.
        # The image would become unloadable otherwise.
        return {
            "success": False,
            "message": "Original unblurred image not found on disk. Cannot undo blur.",
            "had_original": False,
        }

    # 2. Delete blurred copy from GCS annotated/blur/ (if it exists)
    if image.source_drive_folder_id and image.filename:
        try:
            gcs_blob = build_gcs_path(image.source_drive_folder_id, image.filename, "blur")
            gcs_delete(gcs_blob)
        except Exception as e:
            print(f"Warning: Could not delete GCS annotated/blur/ blob: {e}")

    # Also delete local blur file if it exists
    if image.annotated_blur_url and not image.annotated_blur_url.startswith("gs://"):
        try:
            blur_path = os.path.join(str(_get_pw()), image.annotated_blur_url)
            if os.path.exists(blur_path):
                os.remove(blur_path)
        except Exception as e:
            print(f"Warning: Could not delete blurred file: {e}")

    # 3. Replace cache with the original image
    cache_path = os.path.join(CACHE_DIR, f"{image.id}.jpg")
    import cv2
    import numpy as np
    arr = np.frombuffer(original_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is not None:
        _, buf = cv2.imencode(".jpg", img_cv, [cv2.IMWRITE_JPEG_QUALITY, 90])
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(buf.tobytes())
    else:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(original_bytes)

    # 4. Upload restored (clean) version to GCS annotated/clean/
    if image.source_drive_folder_id and image.filename:
        try:
            clean_gcs_dest = build_gcs_path(image.source_drive_folder_id, image.filename, "clean")
            gcs_upload_bytes(original_bytes, clean_gcs_dest, content_type="image/jpeg")
        except Exception as e:
            print(f"Warning: Could not upload restored image to GCS annotated/clean/: {e}")

    # 5. Update database — reset to clean stage
    image.manually_blurred = False
    image.blur_regions = None
    image.annotated_blur_url = None
    image.is_using_processed = False
    image.gcs_folder = "clean"

    if current_user.role == "annotator":
        image.is_restore_annotator = True
    image.restored_by_annotator_id = current_user.id
    image.restored_at_annotator = datetime.utcnow()
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
    Priority:
      1. Local pipeline blurred version (deliverable/)
      2. Local pipeline original (01_downloaded_from_drive/)
      3. Re-download from Google Drive (main download source)
    """
    if current_user.role not in ("annotator", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    restored_bytes = None
    source = None
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    workspace = str(_get_pw())

    # 1. Try processed_url field
    if image.processed_url:
        proc_path = image.processed_url.replace("file://", "")
        full_path = os.path.join(backend_dir, proc_path)
        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
            with open(full_path, "rb") as f:
                restored_bytes = f.read()
            source = "processed_url"

    # 2. Try local pipeline folders (per-folder workspaces + legacy)
    if not restored_bytes:
        search_order = [
            "deliverable",
            "01_downloaded_from_drive",
        ]
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

    # 3. Fallback: re-download from Google Drive (main download source)
    if not restored_bytes:
        restored_bytes = _download_from_google_drive(image.filename)
        if restored_bytes:
            source = "google_drive"
            # Also save to the download folder for future use
            dl_folder = os.path.join(workspace, "01_downloaded_from_drive")
            os.makedirs(dl_folder, exist_ok=True)
            dl_path = os.path.join(dl_folder, image.filename)
            with open(dl_path, "wb") as f:
                f.write(restored_bytes)

    if not restored_bytes:
        raise HTTPException(
            status_code=404,
            detail="Image not found locally or on Google Drive. Cannot restore."
        )

    # Write restored version to cache
    cache_path = os.path.join(CACHE_DIR, f"{image.id}.jpg")
    import cv2
    import numpy as np
    arr = np.frombuffer(restored_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is not None:
        _, buf = cv2.imencode(".jpg", img_cv, [cv2.IMWRITE_JPEG_QUALITY, 90])
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(buf.tobytes())
    else:
        # Fallback: write raw bytes
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(restored_bytes)

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
