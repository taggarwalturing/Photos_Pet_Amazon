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

router = APIRouter(prefix="/annotator/blur", tags=["Annotator Blur"])

# Cache directory (same as main.py proxy)
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "image_cache")

# Output folder for manually blurred images
BLUR_OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "master_pipeline", "pipeline_workspace", "annotated_blur"
)


class BlurRegion(BaseModel):
    x: float       # normalized 0-1
    y: float        # normalized 0-1
    width: float    # normalized 0-1
    height: float   # normalized 0-1


class ApplyBlurRequest(BaseModel):
    regions: List[BlurRegion]


def _get_image_bytes(image: Image) -> bytes:
    """
    Get raw image bytes — try local cache first, then pipeline workspace,
    then download from Google Drive URL.
    """
    # 1. Try image cache (fastest)
    cache_path = os.path.join(CACHE_DIR, f"{image.id}.jpg")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "rb") as f:
            return f.read()

    # 2. Try pipeline workspace (original or processed) — per-folder + legacy
    workspace = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "master_pipeline", "pipeline_workspace"
    )
    search_roots = []
    folders_dir = os.path.join(workspace, "folders")
    if os.path.isdir(folders_dir):
        for fd in sorted(os.listdir(folders_dir)):
            fd_path = os.path.join(folders_dir, fd)
            if os.path.isdir(fd_path):
                search_roots.append(fd_path)
    search_roots.append(workspace)  # legacy flat workspace as fallback
    
    for search_root in search_roots:
        for sub in ["04_final_output", "03_biometric_processed", "02_unique_images", "02_deduplicated", "01_downloaded_from_drive", "01_downloaded"]:
            folder = os.path.join(search_root, sub)
            if os.path.isdir(folder):
                for fname in os.listdir(folder):
                    if fname == image.filename:
                        fpath = os.path.join(folder, fname)
                        if os.path.getsize(fpath) > 0:
                            with open(fpath, "rb") as f:
                                return f.read()

    # 3. Download from URL
    import httpx
    url = image.original_url or image.url
    if not url:
        raise ValueError("No URL available for image")

    # Handle Google Drive URLs
    if "drive.google.com" in url:
        import re
        file_id = None
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
        if match:
            file_id = match.group(1)
        if not file_id:
            match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
            if match:
                file_id = match.group(1)
        if file_id:
            url = f"https://drive.google.com/uc?export=download&id={file_id}"

    resp = httpx.get(url, follow_redirects=True, timeout=30)
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
        # 1. Get original image bytes
        image_bytes = _get_image_bytes(image)

        # 2. Convert regions to dict list
        regions_list = [r.dict() for r in request.regions]

        # 3. Apply blur (server-side, using OpenCV + roi_blur)
        blurred_bytes = blur_image_regions(image_bytes, regions_list)

        # 4. Save blurred image
        blurred_filename = f"blur_{image.id}_{image.filename}"
        # Ensure .jpg extension
        if not blurred_filename.lower().endswith(('.jpg', '.jpeg')):
            blurred_filename = os.path.splitext(blurred_filename)[0] + '.jpg'

        blurred_path = os.path.join(BLUR_OUTPUT_DIR, blurred_filename)
        with open(blurred_path, "wb") as f:
            f.write(blurred_bytes)

        # 5. Also update the image cache so the proxy serves the blurred version
        cache_path = os.path.join(CACHE_DIR, f"{image.id}.jpg")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(blurred_bytes)

        # 6. Update database
        image.manually_blurred = True
        image.blur_regions = regions_list
        image.manually_blurred_by = current_user.id
        image.manually_blurred_at = datetime.utcnow()
        image.annotated_blur_url = f"annotated_blur/{blurred_filename}"

        db.commit()
        db.refresh(image)

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
    Searches pipeline workspace folders in order: downloaded > deduplicated > clean subfolder.
    Skips post-processing folders (04_final_output, 03_biometric_processed/blurred)
    because those contain pipeline-blurred images, not originals.
    """
    workspace = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "master_pipeline", "pipeline_workspace"
    )

    # Check original_url field — but ONLY if it points to a pre-blur location.
    # If original_url points to 04_final_output or 03_biometric_processed,
    # those are post-blur folders and NOT the actual original.
    if image.original_url:
        orig_path = image.original_url.replace("file://", "")
        is_post_blur_path = any(seg in orig_path for seg in [
            "04_final_output",
            "03_biometric_processed",
        ])
        if not is_post_blur_path:
            backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
            full_path = os.path.join(backend_dir, orig_path)
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                with open(full_path, "rb") as f:
                    return f.read()

    # Search pipeline folders (earlier stages have the original unblurred version)
    # Check per-folder workspaces + legacy workspace
    search_roots = []
    folders_dir = os.path.join(workspace, "folders")
    if os.path.isdir(folders_dir):
        for fd in sorted(os.listdir(folders_dir)):
            fd_path = os.path.join(folders_dir, fd)
            if os.path.isdir(fd_path):
                search_roots.append(fd_path)
    search_roots.append(workspace)  # legacy flat workspace as fallback
    
    for search_root in search_roots:
        search_folders = [
            os.path.join(search_root, "01_downloaded_from_drive"),
            os.path.join(search_root, "01_downloaded"),
            os.path.join(search_root, "02_unique_images"),
            os.path.join(search_root, "02_deduplicated"),
            os.path.join(search_root, "03_biometric_processed", "clean"),
        ]
        for folder in search_folders:
            if os.path.isdir(folder):
                fpath = os.path.join(folder, image.filename)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                    with open(fpath, "rb") as f:
                        return f.read()

    # Last resort: re-download from Google Drive
    gdrive_bytes = _download_from_google_drive(image.filename)
    if gdrive_bytes:
        # Save to download folder so it's available next time
        dl_folder = os.path.join(workspace, "01_downloaded_from_drive")
        os.makedirs(dl_folder, exist_ok=True)
        dl_path = os.path.join(dl_folder, image.filename)
        with open(dl_path, "wb") as f:
            f.write(gdrive_bytes)
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

    # 2. Delete manual blur file if it exists
    if image.annotated_blur_url:
        try:
            blur_path = os.path.join(
                os.path.dirname(__file__), "..", "..",
                "master_pipeline", "pipeline_workspace",
                image.annotated_blur_url,
            )
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
        # Fallback — write raw bytes
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(original_bytes)

    # 4. Update database — clear manual blur fields
    image.manually_blurred = False
    image.blur_regions = None
    image.manually_blurred_by = None
    image.manually_blurred_at = None
    image.annotated_blur_url = None
    image.is_using_processed = False  # Switch to showing original

    db.commit()

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
      1. Local pipeline blurred version (03_biometric_processed/blurred, 04_final_output)
      2. Local pipeline original (01_downloaded_from_drive, 02_unique_images)
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
    workspace = os.path.join(backend_dir, "master_pipeline", "pipeline_workspace")

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
            "03_biometric_processed/blurred",
            "04_final_output",
            "02_unique_images",
            "02_deduplicated",
            "01_downloaded_from_drive",
            "01_downloaded",
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
    db.commit()

    return {
        "success": True,
        "message": f"Image restored from {source}",
        "source": source,
    }
