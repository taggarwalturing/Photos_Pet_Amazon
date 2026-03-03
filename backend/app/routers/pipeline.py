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

# Pipeline status storage (in-memory for now)
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


@router.get("/stats")
def get_pipeline_stats(
    db: Session = Depends(get_db)
):
    """Get detailed pipeline statistics for UI display."""
    
    # Get image stats from database
    stats = db.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN compliance_processed = TRUE THEN 1 ELSE 0 END) as processed,
            SUM(CASE WHEN compliance_processed = FALSE OR compliance_processed IS NULL THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN compliance_status IN ('failed', 'error') THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN human_faces_detected > 0 OR compliance_status IN ('blurred', 'processed', 'obfuscated') THEN 1 ELSE 0 END) as with_faces,
            SUM(CASE WHEN (human_faces_detected = 0 OR human_faces_detected IS NULL) AND compliance_status = 'clean' THEN 1 ELSE 0 END) as without_faces,
            SUM(CASE WHEN compliance_status LIKE '%screenshot%' OR processing_log LIKE '%screenshot%' THEN 1 ELSE 0 END) as screenshots
        FROM images
    """)).fetchone()
    
    # Try to get deduplication stats from workspace if available
    try:
        backend_dir = Path(__file__).parent.parent.parent
        workspace = backend_dir / "master_pipeline" / "pipeline_workspace"
        
        # Count unique images folder
        unique_dir = workspace / "02_unique_images"
        unique_count = 0
        if unique_dir.exists():
            extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
            unique_count = len([f for f in unique_dir.iterdir() if f.is_file() and f.suffix.lower() in extensions])
        
        # Count duplicate clusters
        clusters_dir = workspace / "02_duplicate_clusters"
        duplicate_count = 0
        cluster_count = 0
        if clusters_dir.exists():
            cluster_count = len([d for d in clusters_dir.iterdir() if d.is_dir()])
            # Count total duplicates across all clusters
            for cluster_dir in clusters_dir.iterdir():
                if cluster_dir.is_dir():
                    dup_files = [f for f in cluster_dir.iterdir() if f.is_file() and f.name != '.gitkeep']
                    # Subtract 1 for the original, rest are duplicates
                    if dup_files:
                        duplicate_count += len(dup_files) - 1
        
    except Exception as e:
        print(f"Error reading deduplication stats: {e}")
        unique_count = 0
        duplicate_count = 0
        cluster_count = 0
    
    total = stats[0] or 0
    processed = stats[1] or 0
    pending = stats[2] or 0
    failed = stats[3] or 0
    
    # Load Drive metadata
    drive_meta = {}
    drive_meta_path = workspace / "drive_metadata.json"
    if drive_meta_path.exists():
        try:
            with open(drive_meta_path, 'r') as f:
                drive_meta = json.load(f)
        except Exception:
            pass
    
    return {
        "total_images": total,
        "processed": processed,
        "pending": pending,
        "failed": failed,
        "unique_images": unique_count if unique_count > 0 else total - duplicate_count,
        "duplicate_images": duplicate_count,
        "duplicate_clusters": cluster_count,
        "images_with_faces": stats[4] or 0,
        "images_without_faces": stats[5] or 0,
        "screenshots_skipped": stats[6] or 0,
        "status": "idle" if not pipeline_status["is_running"] else pipeline_status["current_step"],
        "last_run": pipeline_status.get("completed_at"),
        # Drive metadata
        "total_in_drive": drive_meta.get("total_in_drive", 0),
        "drive_unique_filenames": drive_meta.get("unique_filenames", 0),
        "drive_duplicate_filenames": drive_meta.get("duplicate_filename_count", 0),
        "drive_duplicate_details": drive_meta.get("duplicate_filenames", {}),
        "drive_scanned_at": drive_meta.get("scanned_at", ""),
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


@router.post("/incremental-import")
async def run_incremental_import(
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin)
):
    """
    Run incremental pipeline processing.
    
    This intelligently:
    1. Detects NEW downloaded images that haven't been processed
    2. Processes ONLY those new images (not the entire collection)
    3. Imports the newly processed images to the database
    
    Example: If you have images 1-1000 already processed and imported,
    and then download images 1001-1500, this will process only 1001-1500.
    """
    if pipeline_status["is_running"]:
        raise HTTPException(
            status_code=400,
            detail="Pipeline is already running. Please wait for it to complete."
        )
    
    # Run incremental import in background
    background_tasks.add_task(run_incremental_import_background)
    
    return {
        "message": "Incremental import started",
        "info": "Processing only NEW images that haven't been processed yet"
    }


@router.get("/check-new-images")
def check_for_new_images(
    admin: User = Depends(require_admin)
):
    """
    Check how many NEW images are available for processing.
    
    Returns counts of:
    - Downloaded but not processed
    - Processed but not imported to DB
    - Already in database
    """
    try:
        backend_dir = Path(__file__).parent.parent.parent
        workspace = backend_dir / "master_pipeline" / "pipeline_workspace"
        
        # Load state tracking
        state_file = workspace / "pipeline_state.json"
        if state_file.exists():
            with open(state_file, 'r') as f:
                state = json.load(f)
        else:
            state = {"processed_files": [], "imported_files": []}
        
        # Count downloaded files
        downloaded_dir = workspace / "01_downloaded_from_drive"
        downloaded_files = []
        if downloaded_dir.exists():
            extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
            downloaded_files = [
                f.name for f in downloaded_dir.iterdir()
                if f.is_file() and f.suffix.lower() in extensions
            ]
        
        # Count final output files
        final_output_dir = workspace / "04_final_output"
        final_files = []
        if final_output_dir.exists():
            extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
            final_files = [
                f.name for f in final_output_dir.iterdir()
                if f.is_file() and f.suffix.lower() in extensions
            ]
        
        # Count database files
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            db_files = db.execute(text("SELECT filename FROM images")).fetchall()
            db_filenames = {row[0] for row in db_files}
        finally:
            db.close()
        
        # Calculate differences
        processed_set = set(state.get("processed_files", []))
        downloaded_set = set(downloaded_files)
        final_set = set(final_files)
        
        new_downloaded = downloaded_set - processed_set  # Downloaded but not processed
        new_final = final_set - db_filenames  # Processed but not imported
        
        return {
            "new_to_process": len(new_downloaded),
            "new_to_import": len(new_final),
            "total_downloaded": len(downloaded_files),
            "total_processed": len(final_files),
            "total_in_database": len(db_filenames),
            "ready_for_incremental": len(new_downloaded) > 0 or len(new_final) > 0,
            "recommendation": (
                f"Run incremental import to process {len(new_downloaded)} new images and import {len(new_final)} processed images"
                if (len(new_downloaded) > 0 or len(new_final) > 0)
                else "No new images found. All images are up to date."
            )
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking for new images: {str(e)}")


# Background task for incremental import
def run_incremental_import_background():
    """Run incremental import in the background."""
    import sys
    global pipeline_status
    
    try:
        pipeline_status["is_running"] = True
        pipeline_status["current_step"] = "incremental_import"
        pipeline_status["started_at"] = datetime.now().isoformat()
        
        backend_dir = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(backend_dir))
        
        # Import and run the incremental importer
        from import_incremental import IncrementalPipelineImporter
        
        importer = IncrementalPipelineImporter()
        results = importer.full_incremental_workflow(
            run_deduplication=False,  # Skip dedup for speed (can be enabled if needed)
            run_biometric=True
        )
        
        pipeline_status["is_running"] = False
        pipeline_status["current_step"] = "completed"
        pipeline_status["completed_at"] = datetime.now().isoformat()
        pipeline_status["summary"] = results.get("summary", {})
        
        print(f"[INCREMENTAL IMPORT] Completed: {results}")
        
    except Exception as e:
        print(f"[INCREMENTAL IMPORT] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        pipeline_status["is_running"] = False
        pipeline_status["current_step"] = "error"
        pipeline_status["completed_at"] = datetime.now().isoformat()
        pipeline_status["errors"].append(f"Incremental import error: {str(e)}")
