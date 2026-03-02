from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime
from pathlib import Path
import shutil

from app.database import get_db
from app.models.user import User
from app.models.image import Image
from app.dependencies import get_current_user
from app.utils.blur import blur_image_regions
import requests

router = APIRouter(prefix="/annotator/blur", tags=["Annotator Blur"])


class BlurRegion(BaseModel):
    x: float  # normalized 0-1
    y: float  # normalized 0-1
    width: float  # normalized 0-1
    height: float  # normalized 0-1


class ApplyBlurRequest(BaseModel):
    image_id: int
    regions: List[BlurRegion]


@router.post("/apply")
def apply_manual_blur(
    request: ApplyBlurRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Apply manual blur regions to an image.
    Downloads the image, applies blur, saves to annotated_blur folder,
    and updates database with coordinates and status.
    """
    # Verify user is an annotator
    if current_user.role != "annotator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only annotators can manually blur images"
        )
    
    # Get the image
    image = db.query(Image).filter(Image.id == request.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Create annotated_blur folder if it doesn't exist
    blur_folder = Path("backend/master_pipeline/pipeline_workspace/annotated_blur")
    blur_folder.mkdir(parents=True, exist_ok=True)
    
    # Download the original image
    try:
        # Get image URL (use proxy endpoint)
        from app.config import settings
        image_url = f"{settings.backend_url}/api/images/proxy/{image.id}"
        
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        image_bytes = response.content
        
        # Convert regions to dict format
        regions_list = [region.dict() for region in request.regions]
        
        # Apply blur
        blurred_bytes = blur_image_regions(image_bytes, regions_list)
        
        # Save blurred image
        blurred_filename = f"blur_{image.id}_{image.filename}"
        blurred_path = blur_folder / blurred_filename
        
        with open(blurred_path, "wb") as f:
            f.write(blurred_bytes)
        
        # Update database
        image.manually_blurred = True
        image.blur_regions = regions_list
        image.manually_blurred_by = current_user.id
        image.manually_blurred_at = datetime.utcnow()
        image.annotated_blur_url = f"file://master_pipeline/pipeline_workspace/annotated_blur/{blurred_filename}"
        
        db.commit()
        db.refresh(image)
        
        return {
            "success": True,
            "message": "Blur applied successfully",
            "image_id": image.id,
            "blurred_url": image.annotated_blur_url,
            "regions": image.blur_regions
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply blur: {str(e)}"
        )


@router.get("/{image_id}/regions")
def get_blur_regions(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
        "blurred_at": image.manually_blurred_at
    }


@router.delete("/{image_id}/blur")
def remove_manual_blur(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove manual blur from an image."""
    # Verify user is an annotator
    if current_user.role != "annotator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only annotators can remove blur"
        )
    
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Delete the blurred file if it exists
    if image.annotated_blur_url:
        try:
            # Extract filename from URL
            blur_path = Path("backend") / image.annotated_blur_url.replace("file://", "")
            if blur_path.exists():
                blur_path.unlink()
        except Exception as e:
            # Log but don't fail if file deletion fails
            print(f"Warning: Could not delete blurred file: {e}")
    
    # Update database
    image.manually_blurred = False
    image.blur_regions = None
    image.manually_blurred_by = None
    image.manually_blurred_at = None
    image.annotated_blur_url = None
    
    db.commit()
    
    return {
        "success": True,
        "message": "Manual blur removed successfully"
    }
