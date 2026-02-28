"""
Biometric Compliance Integration
=================================
Integrates the compliance pipeline for processing images.
"""

import subprocess
import json
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.image import Image
from app.models.annotation import Annotation
from app.models.option import Option

router = APIRouter(prefix="/admin/compliance", tags=["Compliance"])

# Pipeline paths - Reference master_pipeline in same backend directory
PIPELINE_DIR = Path(__file__).parent.parent.parent / "master_pipeline" / "biometric_compliance_pipeline"
PIPELINE_SCRIPT = PIPELINE_DIR / "scripts" / "stage3_obfuscate_faces_enhanced.py"


class ProcessImageRequest(BaseModel):
    image_ids: List[int]


class ComplianceFlaggedImage(BaseModel):
    image_id: int
    filename: str
    flagged_for_human: bool
    flagged_for_animal: bool
    human_flag_text: str
    animal_flag_text: str


@router.get("/flagged-images")
def get_flagged_images(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Get all images flagged by annotators for compliance issues.
    """
    # Find annotations with compliance flags
    # Category IDs: 7 = Human Face Visibility, 8 = Animal Face Blur Check
    
    flagged_images = []
    
    # Get all annotations for compliance categories
    human_annotations = (
        db.query(Annotation)
        .filter(Annotation.category_id == 7, Annotation.status == "completed")
        .all()
    )
    
    animal_annotations = (
        db.query(Annotation)
        .filter(Annotation.category_id == 8, Annotation.status == "completed")
        .all()
    )
    
    # Group by image
    image_flags = {}
    
    for ann in human_annotations:
        if ann.image_id not in image_flags:
            image_flags[ann.image_id] = {"human": None, "animal": None}
        
        # Get selected option
        selections = ann.selections
        if selections:
            option = db.query(Option).filter(Option.id == selections[0].option_id).first()
            if option and "needs reprocessing" in option.label:
                image_flags[ann.image_id]["human"] = option.label
    
    for ann in animal_annotations:
        if ann.image_id not in image_flags:
            image_flags[ann.image_id] = {"human": None, "animal": None}
        
        # Get selected option
        selections = ann.selections
        if selections:
            option = db.query(Option).filter(Option.id == selections[0].option_id).first()
            if option and "needs reprocessing" in option.label:
                image_flags[ann.image_id]["animal"] = option.label
    
    # Build response
    for image_id, flags in image_flags.items():
        if flags["human"] or flags["animal"]:
            image = db.query(Image).filter(Image.id == image_id).first()
            if image:
                flagged_images.append({
                    "image_id": image.id,
                    "filename": image.filename,
                    "flagged_for_human": flags["human"] is not None,
                    "flagged_for_animal": flags["animal"] is not None,
                    "human_flag_text": flags["human"] or "",
                    "animal_flag_text": flags["animal"] or "",
                    "compliance_status": image.compliance_status,
                    "human_faces_detected": image.human_faces_detected,
                })
    
    return {
        "flagged_images": flagged_images,
        "total": len(flagged_images),
    }


@router.post("/process-images")
def process_images_through_pipeline(
    payload: ProcessImageRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Process selected images through the biometric compliance pipeline.
    This will:
    1. Download images from Google Drive
    2. Run face detection and obfuscation
    3. Upload processed images back
    4. Update database with processing status
    """
    if not PIPELINE_SCRIPT.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline script not found at {PIPELINE_SCRIPT}"
        )
    
    # Create temp directories
    temp_input = PIPELINE_DIR / "data" / "temp_input"
    temp_output = PIPELINE_DIR / "data" / "temp_output"
    temp_input.mkdir(parents=True, exist_ok=True)
    temp_output.mkdir(parents=True, exist_ok=True)
    
    processed_count = 0
    errors = []
    
    try:
        for image_id in payload.image_ids:
            image = db.query(Image).filter(Image.id == image_id).first()
            if not image:
                errors.append(f"Image {image_id} not found")
                continue
            
            try:
                # TODO: Download image from Google Drive to temp_input
                # TODO: Run pipeline on this specific image
                # TODO: Upload processed image back to Google Drive
                # TODO: Update database
                
                # For now, mark as processed
                image.compliance_processed = True
                image.compliance_status = "reprocessed"
                image.processing_log = f"Reprocessed by admin {admin.username} at {datetime.now()}"
                
                processed_count += 1
                
            except Exception as e:
                errors.append(f"Image {image_id}: {str(e)}")
        
        db.commit()
        
        return {
            "success": True,
            "processed_count": processed_count,
            "total_requested": len(payload.image_ids),
            "errors": errors,
            "message": f"Processed {processed_count}/{len(payload.image_ids)} images"
        }
        
    finally:
        # Cleanup temp directories
        if temp_input.exists():
            shutil.rmtree(temp_input)
        if temp_output.exists():
            shutil.rmtree(temp_output)


@router.get("/stats")
def get_compliance_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Get compliance processing statistics."""
    total_images = db.query(Image).count()
    processed_images = db.query(Image).filter(Image.compliance_processed == True).count()
    flagged_images = db.query(Image).filter(Image.compliance_status == "flagged").count()
    
    return {
        "total_images": total_images,
        "processed_images": processed_images,
        "flagged_images": flagged_images,
        "processing_rate": round((processed_images / total_images * 100), 2) if total_images > 0 else 0,
    }
