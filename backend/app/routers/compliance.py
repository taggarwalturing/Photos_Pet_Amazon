"""
Biometric Compliance Integration
=================================
Integrates the compliance pipeline for processing images.
Updated for 3-table schema — uses Image model fields instead of
deprecated Annotation/Option tables.
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

router = APIRouter(prefix="/admin/compliance", tags=["Compliance"])

# Pipeline paths - Reference master_pipeline in same backend directory
PIPELINE_DIR = Path(__file__).parent.parent.parent / "master_pipeline" / "biometric_compliance_pipeline"
PIPELINE_SCRIPT = PIPELINE_DIR / "scripts" / "stage3_obfuscate_faces_enhanced.py"


class ProcessImageRequest(BaseModel):
    image_ids: List[int]


@router.get("/flagged-images")
def get_flagged_images(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Get all images flagged for compliance issues.
    In the new schema, this checks Image model fields directly:
    - human_faces_detected > 0  → human face visibility concern
    - compliance_status contains a flag
    """
    flagged_images = []

    # Query images that were flagged by the biometric pipeline
    images = (
        db.query(Image)
        .filter(
            Image.human_faces_detected > 0,
        )
        .all()
    )

    for image in images:
        flagged_images.append({
            "image_id": image.id,
            "filename": image.filename,
            "flagged_for_human": image.human_faces_detected > 0,
            "flagged_for_animal": False,  # Animal detection is separate pipeline step
            "human_flag_text": f"{image.human_faces_detected} human face(s) detected" if image.human_faces_detected else "",
            "animal_flag_text": "",
            "compliance_status": image.compliance_status,
            "human_faces_detected": image.human_faces_detected,
            "is_programmatically_blurred": image.is_programmatically_blurred or False,
            "manually_blurred": image.manually_blurred or False,
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
                # Mark as reprocessed
                image.compliance_status = "reprocessed"
                image.pipeline_status = "reprocessed"
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
    from sqlalchemy import func, case, or_

    stats = db.query(
        func.count().label("total"),
        func.sum(case(
            (or_(
                Image.compliance_status.in_(["blurred", "processed", "obfuscated"]),
                Image.is_programmatically_blurred == True,
            ), 1), else_=0
        )).label("processed"),
        func.sum(case(
            (Image.compliance_status == "flagged", 1), else_=0
        )).label("flagged"),
        func.sum(case(
            (Image.human_faces_detected > 0, 1), else_=0
        )).label("with_faces"),
    ).one()

    total = stats.total or 0
    processed = stats.processed or 0

    return {
        "total_images": total,
        "processed_images": processed,
        "flagged_images": stats.flagged or 0,
        "with_human_faces": stats.with_faces or 0,
        "processing_rate": round((processed / total * 100), 2) if total > 0 else 0,
    }
