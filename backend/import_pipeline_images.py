"""
Import images from master pipeline's final output into the database.

Supports two workspace layouts:
  1. Per-folder workspaces (new):  pipeline_workspace/folders/{folder_id}/04_final_output/
  2. Legacy flat workspace:        pipeline_workspace/04_final_output/

Each per-folder workspace carries its own drive_metadata.json, obfuscation_results.json,
and 03_biometric_processed/{blurred,clean} folders.
"""
import sys
import json
from pathlib import Path
from sqlalchemy import text
from app.database import SessionLocal
from app.config import settings


def _import_from_workspace(db, workspace: Path, folder_id: str = None, existing_filenames: set = None):
    """
    Import images from a single workspace (either per-folder or legacy flat).
    
    Args:
        db: Database session
        workspace: Path to the workspace root (e.g. pipeline_workspace/ or pipeline_workspace/folders/{fid}/)
        folder_id: Google Drive folder ID (derived from directory name for per-folder workspaces)
        existing_filenames: Set of filenames already in the database
    
    Returns:
        dict with counts: new, updated, blurred, clean
    """
    final_output = workspace / "04_final_output"
    biometric_processed = workspace / "03_biometric_processed"
    
    if not final_output.exists():
        return {'new': 0, 'updated': 0, 'blurred': 0, 'clean': 0}
    
    # Load biometric results — prefer per-folder copy, fallback to central
    biometric_metadata = {}
    
    # Priority 1: per-folder workspace copy
    results_json_path = workspace / "obfuscation_results.json"
    
    # Priority 2: central biometric pipeline results
    if not results_json_path.exists():
        results_json_path = Path(__file__).parent / "master_pipeline" / "biometric_compliance_pipeline" / "results" / "obfuscation_results.json"
    
    if results_json_path.exists():
        try:
            with open(results_json_path, 'r') as f:
                results_data = json.load(f)
                for result in results_data.get('results', []):
                    filename = result.get('image') or result.get('output_name')
                    if filename:
                        biometric_metadata[filename] = result
            print(f"   📊 Loaded biometric metadata for {len(biometric_metadata)} images")
        except Exception as e:
            print(f"   ⚠️  Could not load biometric results: {e}")
    
    # Check blurred vs clean folders
    blurred_folder = biometric_processed / "blurred"
    clean_folder = biometric_processed / "clean"
    
    blurred_images = set()
    clean_images = set()
    
    if blurred_folder.exists():
        blurred_images = {f.name for f in blurred_folder.iterdir() if f.is_file()}
    if clean_folder.exists():
        clean_images = {f.name for f in clean_folder.iterdir() if f.is_file()}
    
    # Get all image files from final output
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
    image_files = [
        f for f in final_output.iterdir() 
        if f.is_file() and f.suffix.lower() in image_extensions
    ]
    
    if not image_files:
        return {'new': 0, 'updated': 0, 'blurred': 0, 'clean': 0}
    
    print(f"   📁 Found {len(image_files)} images in final output")
    
    # HEIC conversion map
    download_dir = workspace / "01_downloaded_from_drive"
    unique_dir = workspace / "02_unique_images"
    
    heic_conversion_map = {}
    manifest_path = download_dir / "_heic_conversions.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            for jpg_name, info in manifest.items():
                heic_conversion_map[jpg_name] = info['original_filename']
            if heic_conversion_map:
                print(f"   📷 Loaded {len(heic_conversion_map)} HEIC conversions from manifest")
        except Exception as e:
            print(f"   ⚠️  Could not read HEIC manifest: {e}")
    
    # Fallback HEIC detection
    if not heic_conversion_map:
        heic_on_disk = set()
        heic_originals_dir = download_dir / '_heic_originals'
        scan_dirs = [download_dir, unique_dir]
        if heic_originals_dir.is_dir():
            scan_dirs.append(heic_originals_dir)
        for d in scan_dirs:
            if d.is_dir():
                for f in d.iterdir():
                    if f.is_file() and f.suffix.lower() in ('.heic', '.heif', '.avif'):
                        heic_on_disk.add(f.name)
        for img_file in image_files:
            stem = img_file.stem
            if img_file.suffix.lower() in ('.jpg', '.jpeg'):
                for heic_name in heic_on_disk:
                    heic_stem = Path(heic_name).stem
                    if heic_stem == stem:
                        heic_conversion_map[img_file.name] = heic_name
                        break
    
    # Load filename → folder_id and filename → drive_file_id mappings from drive_metadata.json
    filename_folder_map = {}
    filename_to_drive_id = {}
    drive_meta_path = workspace / "drive_metadata.json"
    if drive_meta_path.exists():
        try:
            with open(drive_meta_path, 'r') as f:
                drive_meta = json.load(f)
            filename_folder_map = drive_meta.get("filename_folder_map", {})
            filename_to_drive_id = drive_meta.get("filename_to_drive_id", {})
            # If folder_id not provided, try to extract from metadata
            if not folder_id:
                folder_id = drive_meta.get("folder_id")
        except Exception as e:
            print(f"   ⚠️  Could not load drive metadata: {e}")
    
    counts = {'new': 0, 'updated': 0, 'blurred': 0, 'clean': 0}
    
    # Determine relative path prefix for URLs
    # For per-folder workspaces: master_pipeline/pipeline_workspace/folders/{folder_id}/04_final_output/
    # For legacy:                master_pipeline/pipeline_workspace/04_final_output/
    pipeline_ws = Path(__file__).parent / "master_pipeline" / "pipeline_workspace"
    try:
        rel_workspace = workspace.relative_to(pipeline_ws.parent.parent)  # relative to backend/
    except ValueError:
        rel_workspace = workspace
    
    for img_file in image_files:
        filename = img_file.name
        
        metadata = biometric_metadata.get(filename, {})
        action = metadata.get('action', 'unknown')
        face_count = metadata.get('face_count', 0)
        
        is_blurred = filename in blurred_images
        is_clean = filename in clean_images
        
        if is_blurred:
            compliance_status = 'blurred'
            counts['blurred'] += 1
        elif is_clean:
            compliance_status = 'clean'
            counts['clean'] += 1
        elif action == 'obfuscated':
            compliance_status = 'blurred'
            counts['blurred'] += 1
        elif action == 'no_face':
            compliance_status = 'clean'
            counts['clean'] += 1
        else:
            compliance_status = 'processed'
        
        # Resolve source folder ID for this image
        source_fid = folder_id  # default to the workspace's folder_id
        if not source_fid:
            lookup_name = heic_conversion_map.get(filename, filename)
            source_fid = filename_folder_map.get(lookup_name) or filename_folder_map.get(filename)
        
        # Resolve Google Drive file ID for this image
        # For HEIC-converted files, look up by original HEIC filename
        lookup_name_for_drive = heic_conversion_map.get(filename, filename)
        drive_file_id = filename_to_drive_id.get(lookup_name_for_drive) or filename_to_drive_id.get(filename)
        
        # URL path relative to backend directory
        relative_path = f"{rel_workspace}/04_final_output/{filename}"
        url = f"file://{relative_path}"
            
            if filename in existing_filenames:
            db.execute(text('''
                UPDATE images 
                SET 
                    compliance_processed = TRUE,
                    compliance_status = :compliance_status,
                    human_faces_detected = :face_count,
                    is_using_processed = TRUE,
                    processing_log = :processing_log,
                    source_drive_folder_id = COALESCE(source_drive_folder_id, :source_drive_folder_id),
                    image_drive_id = COALESCE(image_drive_id, :image_drive_id),
                    url = :url,
                    original_url = :original_url,
                    processed_url = :processed_url
                WHERE filename = :filename
            '''), {
                'filename': filename,
                'compliance_status': compliance_status,
                'face_count': face_count,
                'processing_log': f"Action: {action}, Faces: {face_count}",
                'source_drive_folder_id': source_fid,
                'image_drive_id': drive_file_id,
                'url': url,
                'original_url': relative_path,
                'processed_url': relative_path,
            })
            counts['updated'] += 1
        else:
            heic_original = heic_conversion_map.get(filename)
            orig_format = "HEIC" if heic_original else None
            
            db.execute(text('''
                INSERT INTO images (
                    filename, original_filename, original_format,
                    url, compliance_processed, compliance_status,
                    original_url, processed_url, is_improper,
                    human_faces_detected, is_using_processed,
                    processing_log, source_drive_folder_id,
                    image_drive_id, manually_blurred
                )
                VALUES (
                    :filename, :original_filename, :original_format,
                    :url, TRUE, :compliance_status,
                    :original_url, :processed_url, FALSE,
                    :face_count, TRUE,
                    :processing_log, :source_drive_folder_id,
                    :image_drive_id, FALSE
                )
            '''), {
                'filename': filename,
                'original_filename': heic_original,
                'original_format': orig_format,
                'url': url,
                'compliance_status': compliance_status,
                'face_count': face_count,
                'original_url': relative_path,
                'processed_url': relative_path,
                'processing_log': f"Action: {action}, Faces: {face_count}",
                'source_drive_folder_id': source_fid,
                'image_drive_id': drive_file_id,
            })
            counts['new'] += 1
            existing_filenames.add(filename)  # prevent duplicates across folders
    
    return counts


def import_images_from_pipeline():
    """Import images from pipeline workspace to database with biometric metadata."""
    
    pipeline_workspace = Path(__file__).parent / "master_pipeline" / "pipeline_workspace"
    
    if not pipeline_workspace.exists():
        print(f"❌ Pipeline workspace not found: {pipeline_workspace}")
        return 0
    
    db = SessionLocal()
    try:
        # Get existing filenames
        existing = db.execute(text("SELECT filename FROM images")).fetchall()
        existing_filenames = {row[0] for row in existing}
        print(f"📊 Database has {len(existing_filenames)} existing images")
        
        total_new = 0
        total_updated = 0
        total_blurred = 0
        total_clean = 0
        
        # ── Check for per-folder workspaces (new layout) ──
        folders_dir = pipeline_workspace / "folders"
        per_folder_found = False
        
        if folders_dir.exists():
            folder_dirs = sorted([d for d in folders_dir.iterdir() if d.is_dir()])
            if folder_dirs:
                per_folder_found = True
                print(f"\n📂 Found {len(folder_dirs)} per-folder workspace(s)")
                
                for folder_dir in folder_dirs:
                    folder_id = folder_dir.name
                    print(f"\n{'─' * 50}")
                    print(f"📂 Importing folder: {folder_id}")
                    
                    counts = _import_from_workspace(
                        db, folder_dir, folder_id=folder_id, existing_filenames=existing_filenames
                    )
                    total_new += counts['new']
                    total_updated += counts['updated']
                    total_blurred += counts['blurred']
                    total_clean += counts['clean']
                    
                    print(f"   ✅ New: {counts['new']}, Updated: {counts['updated']}, "
                          f"Blurred: {counts['blurred']}, Clean: {counts['clean']}")
        
        # ── Check for legacy flat workspace ──
        legacy_final = pipeline_workspace / "04_final_output"
        if legacy_final.exists() and any(legacy_final.iterdir()):
            if not per_folder_found:
                print(f"\n📂 Found legacy flat workspace")
                counts = _import_from_workspace(
                    db, pipeline_workspace, folder_id=None, existing_filenames=existing_filenames
                )
                total_new += counts['new']
                total_updated += counts['updated']
                total_blurred += counts['blurred']
                total_clean += counts['clean']
            else:
                print(f"\n⚠️  Legacy flat workspace exists but skipping (per-folder workspaces found)")
        
        db.commit()
        
        print(f"\n{'=' * 50}")
        print(f"✅ Import complete!")
        print(f"   • New images imported: {total_new}")
        print(f"   • Existing images updated: {total_updated}")
        print(f"   • Images with blurred faces: {total_blurred}")
        print(f"   • Clean images (no faces): {total_clean}")
        print(f"   • Total in database: {len(existing_filenames)}")
        
        return total_new
        
    except Exception as e:
        print(f"❌ Error importing images: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("📥 IMPORTING PIPELINE IMAGES TO DATABASE")
    print("=" * 70)
    print()
    
    count = import_images_from_pipeline()
    
    if count > 0:
        print(f"\n🎉 Successfully imported {count} images!")
        print(f"   They are now available in the annotation UI.")
    else:
        print(f"\n⚠️  No new images were imported.")
    
    sys.exit(0 if count >= 0 else 1)
