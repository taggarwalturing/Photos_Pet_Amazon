"""
Master Pipeline Control API
============================
Admin endpoints for controlling and monitoring the master pipeline.
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.image import Image

router = APIRouter(prefix="/admin/pipeline", tags=["Master Pipeline"])

# Pipeline status storage (in-memory for now, could be Redis in production)
pipeline_status = {
    "is_running": False,
    "current_step": None,
    "progress": {
        "download": {"status": "pending", "current": 0, "total": 0, "message": ""},
        "deduplicate": {"status": "pending", "current": 0, "total": 0, "message": ""},
        "biometric": {"status": "pending", "current": 0, "total": 0, "message": ""}
    },
    "started_at": None,
    "completed_at": None,
    "errors": [],
    "summary": {}
}


class PipelineRunRequest(BaseModel):
    download: bool = False
    deduplicate: bool = False
    biometric: bool = True
    use_llm: bool = False
    threshold: float = 0.85


class ReprocessRequest(BaseModel):
    image_ids: List[int]


@router.get("/status")
def get_pipeline_status(
    admin: User = Depends(require_admin)
):
    """Get current pipeline execution status."""
    return pipeline_status


@router.post("/start")
async def start_pipeline(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Start the master pipeline with specified steps."""
    global pipeline_status
    
    if pipeline_status["is_running"]:
        raise HTTPException(status_code=400, detail="Pipeline is already running")
    
    # Reset status
    pipeline_status = {
        "is_running": True,
        "current_step": None,
        "progress": {
            "download": {"status": "pending", "current": 0, "total": 0, "message": ""},
            "deduplicate": {"status": "pending", "current": 0, "total": 0, "message": ""},
            "biometric": {"status": "pending", "current": 0, "total": 0, "message": ""}
        },
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "errors": [],
        "summary": {},
        "requested_by": admin.username
    }
    
    # Run pipeline in background
    background_tasks.add_task(
        run_pipeline_background,
        request.download,
        request.deduplicate,
        request.biometric,
        request.use_llm,
        request.threshold,
        db
    )
    
    return {"message": "Pipeline started successfully", "status": pipeline_status}


@router.post("/stop")
def stop_pipeline(
    admin: User = Depends(require_admin)
):
    """Stop the currently running pipeline."""
    global pipeline_status
    
    if not pipeline_status["is_running"]:
        raise HTTPException(status_code=400, detail="No pipeline is currently running")
    
    # TODO: Implement graceful pipeline termination
    pipeline_status["is_running"] = False
    pipeline_status["current_step"] = "stopped"
    pipeline_status["completed_at"] = datetime.now().isoformat()
    
    return {"message": "Pipeline stop requested", "status": pipeline_status}


@router.get("/errors")
def get_pipeline_errors(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get images that failed during processing."""
    
    # Get images with processing errors
    failed_images = db.execute(text("""
        SELECT id, filename, compliance_status, processing_log, human_faces_detected
        FROM images
        WHERE compliance_status IN ('failed', 'error', 'needs_reprocess')
        OR processing_log LIKE '%error%'
        OR processing_log LIKE '%failed%'
        ORDER BY id DESC
    """)).fetchall()
    
    return {
        "total_errors": len(failed_images),
        "errors": [
            {
                "image_id": img[0],
                "filename": img[1],
                "status": img[2],
                "log": img[3],
                "faces_detected": img[4]
            }
            for img in failed_images
        ]
    }


@router.post("/reprocess")
async def reprocess_failed_images(
    request: ReprocessRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reprocess specific images that failed."""
    
    if pipeline_status["is_running"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot reprocess while pipeline is running"
        )
    
    # Verify images exist
    images = db.query(Image).filter(Image.id.in_(request.image_ids)).all()
    
    if len(images) != len(request.image_ids):
        raise HTTPException(
            status_code=404,
            detail=f"Some images not found. Found {len(images)} of {len(request.image_ids)}"
        )
    
    # Reset their processing status
    for image in images:
        image.compliance_processed = False
        image.compliance_status = "pending_reprocess"
        image.processing_log = f"Reprocess requested by {admin.username} at {datetime.now()}"
    
    db.commit()
    
    # Start reprocessing in background
    background_tasks.add_task(
        reprocess_images_background,
        request.image_ids,
        db
    )
    
    return {
        "message": f"Reprocessing {len(images)} images",
        "image_ids": request.image_ids
    }


@router.get("/summary")
def get_pipeline_summary(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get overall pipeline statistics."""
    
    stats = db.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN compliance_processed = TRUE THEN 1 ELSE 0 END) as processed,
            SUM(CASE WHEN compliance_status = 'clean' THEN 1 ELSE 0 END) as clean,
            SUM(CASE WHEN compliance_status = 'processed' THEN 1 ELSE 0 END) as blurred,
            SUM(CASE WHEN compliance_status IN ('failed', 'error') THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN human_faces_detected > 0 THEN 1 ELSE 0 END) as with_faces
        FROM images
    """)).fetchone()
    
    return {
        "total_images": stats[0] or 0,
        "processed": stats[1] or 0,
        "clean": stats[2] or 0,
        "blurred": stats[3] or 0,
        "failed": stats[4] or 0,
        "with_faces": stats[5] or 0,
        "pending": (stats[0] or 0) - (stats[1] or 0)
    }


# Background task functions

def run_pipeline_background(
    download: bool,
    deduplicate: bool,
    biometric: bool,
    use_llm: bool,
    threshold: float,
    db: Session
):
    """Run the master pipeline in the background."""
    import subprocess
    import sys
    from pathlib import Path
    import threading
    global pipeline_status
    
    try:
        print(f"[PIPELINE] Starting pipeline: download={download}, deduplicate={deduplicate}, biometric={biometric}")
        
        # Build command
        pipeline_dir = Path(__file__).parent.parent.parent / "master_pipeline"
        cmd = [
            sys.executable,
            str(pipeline_dir / "master_pipeline.py")
        ]
        
        if download:
            cmd.append("--download")
        
        if deduplicate:
            cmd.append("--deduplicate")
            if use_llm:
                cmd.append("--use-llm")
            cmd.extend(["--threshold", str(threshold)])
        
        if biometric:
            cmd.append("--pipeline")
        
        print(f"[PIPELINE] Running command: {' '.join(cmd)}")
        pipeline_status["current_step"] = "initializing"
        
        # Run pipeline with real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr with stdout
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True,
            cwd=str(pipeline_dir)
        )
        
        # Read output line by line
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                    
                line = line.strip()
                print(f"[PIPELINE OUTPUT] {line}")
                
                # Parse progress numbers from output like "Comparing:   9%|▊         | 20821/242556"
                import re
                
                # Extract current/total from patterns like "20821/242556"
                progress_match = re.search(r'(\d+)/(\d+)', line)
                if progress_match:
                    current = int(progress_match.group(1))
                    total = int(progress_match.group(2))
                    
                    # Determine which step based on context
                    if "download" in line.lower() or "downloading" in line.lower():
                        pipeline_status["progress"]["download"]["current"] = current
                        pipeline_status["progress"]["download"]["total"] = total
                    elif "compar" in line.lower() or "duplicat" in line.lower() or "dedup" in line.lower():
                        pipeline_status["progress"]["deduplicate"]["current"] = current
                        pipeline_status["progress"]["deduplicate"]["total"] = total
                    elif "process" in line.lower() or "biometric" in line.lower() or "face" in line.lower():
                        pipeline_status["progress"]["biometric"]["current"] = current
                        pipeline_status["progress"]["biometric"]["total"] = total
                
                # Parse progress from output
                if "Step 1:" in line or "STEP 1:" in line or "Downloading" in line.lower():
                    pipeline_status["current_step"] = "download"
                    pipeline_status["progress"]["download"]["status"] = "running"
                    pipeline_status["progress"]["download"]["message"] = line
                elif "Step 2:" in line or "STEP 2:" in line or "Deduplicat" in line:
                    pipeline_status["current_step"] = "deduplicate"
                    pipeline_status["progress"]["deduplicate"]["status"] = "running"
                    pipeline_status["progress"]["deduplicate"]["message"] = line
                elif "Step 3:" in line or "STEP 3:" in line or "Biometric" in line:
                    pipeline_status["current_step"] = "biometric"
                    pipeline_status["progress"]["biometric"]["status"] = "running"
                    pipeline_status["progress"]["biometric"]["message"] = line
                
                # Check for errors
                if "error" in line.lower() or "failed" in line.lower():
                    pipeline_status["errors"].append(line)
        
        # Wait for completion
        returncode = process.wait()
        print(f"[PIPELINE] Process completed with return code: {returncode}")
        
        # Update final status
        pipeline_status["is_running"] = False
        pipeline_status["completed_at"] = datetime.now().isoformat()
        
        if returncode == 0:
            pipeline_status["current_step"] = "completed"
            for step in pipeline_status["progress"]:
                if pipeline_status["progress"][step]["status"] == "running":
                    pipeline_status["progress"][step]["status"] = "completed"
            print("[PIPELINE] Pipeline completed successfully")
        else:
            pipeline_status["current_step"] = "failed"
            pipeline_status["errors"].append(f"Pipeline failed with code {returncode}")
            print(f"[PIPELINE] Pipeline failed with code {returncode}")
        
    except Exception as e:
        print(f"[PIPELINE] Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        pipeline_status["is_running"] = False
        pipeline_status["current_step"] = "error"
        pipeline_status["completed_at"] = datetime.now().isoformat()
        pipeline_status["errors"].append(f"Exception: {str(e)}")


def reprocess_images_background(image_ids: List[int], db: Session):
    """Reprocess specific images in the background."""
    import subprocess
    import sys
    from pathlib import Path
    
    try:
        # Get image files
        images = db.query(Image).filter(Image.id.in_(image_ids)).all()
        
        # TODO: Implement selective reprocessing
        # For now, just mark them for reprocessing and they'll be picked up
        # in the next pipeline run
        
        for image in images:
            image.processing_log = f"Queued for reprocessing at {datetime.now()}"
        
        db.commit()
        
    except Exception as e:
        print(f"Reprocessing error: {e}")


@router.post("/sync-status")
def sync_pipeline_status(
    admin: User = Depends(require_admin)
):
    """
    Sync pipeline status from the actual pipeline results file.
    Useful when pipeline was run from terminal instead of UI.
    """
    global pipeline_status
    
    try:
        # Read the actual pipeline results
        backend_dir = Path(__file__).parent.parent.parent
        results_file = backend_dir / "master_pipeline" / "biometric_compliance_pipeline" / "results" / "obfuscation_results.json"
        
        if not results_file.exists():
            raise HTTPException(status_code=404, detail="Pipeline results file not found. Has the pipeline been run?")
        
        import json
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        # Check workspace for actual counts
        workspace = backend_dir / "master_pipeline" / "pipeline_workspace"
        downloaded_dir = workspace / "01_downloaded_from_drive"
        unique_dir = workspace / "02_unique_images"
        
        downloaded_count = len(list(downloaded_dir.glob("*.*"))) if downloaded_dir.exists() else 0
        unique_count = len(list(unique_dir.glob("*.*"))) if unique_dir.exists() else 0
        
        # Update pipeline status with actual results
        pipeline_status = {
            "is_running": False,
            "current_step": "completed",
            "progress": {
                "download": {
                    "status": "completed",
                    "current": downloaded_count,
                    "total": downloaded_count,
                    "message": f"Downloaded {downloaded_count} images from Google Drive"
                },
                "deduplicate": {
                    "status": "completed",
                    "current": unique_count,
                    "total": unique_count,
                    "message": f"Found {unique_count} unique images"
                },
                "biometric": {
                    "status": "completed",
                    "current": results['total_images'],
                    "total": results['total_images'],
                    "message": f"Processed {results['total_images']} images - {results['statistics']['clean']} clean, {results['statistics']['obfuscated']} obfuscated, {results['statistics']['verification_failed']} QA review"
                }
            },
            "started_at": None,
            "completed_at": datetime.now().isoformat(),
            "errors": [],
            "summary": {
                "total_processed": results['total_images'],
                "clean": results['statistics']['clean'],
                "obfuscated": results['statistics']['obfuscated'],
                "qa_required": results['statistics']['verification_failed'],
                "failed": results['statistics']['failed']
            }
        }
        
        return {
            "success": True,
            "message": "Pipeline status synced successfully",
            "status": pipeline_status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync pipeline status: {str(e)}")
