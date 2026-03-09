"""
Import images from master pipeline's deliverable output into the database.

Supports two workspace layouts:
  1. Per-folder workspaces (new):  pipeline_workspace/folders/{folder_id}/deliverable/
  2. Legacy flat workspace:        pipeline_workspace/deliverable/

Each per-folder workspace carries its own drive_metadata.json, obfuscation_results.json,
and deduplication_stats.json.

Folder structure (simplified):
  pipeline_workspace/folders/{folder_id}/
    ├── 01_downloaded_from_drive/   ← raw downloads + HEIC conversions
    ├── deliverable/                ← final processed images
    ├── drive_metadata.json
    ├── deduplication_stats.json
    └── obfuscation_results.json
"""
import sys
import os
import json
import shutil
from pathlib import Path
from sqlalchemy import text
from dotenv import dotenv_values
from app.database import SessionLocal
from app.config import settings
from app.utils.gcs import gcs_path as build_gcs_path

# Explicitly load .env to avoid stale os.environ
_BACKEND_ENV = dotenv_values(Path(__file__).parent / ".env")


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
    final_output = workspace / "deliverable"
    
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
    
    # Load deduplication stats for is_duplicate / parent_image
    dedup_stats_path = workspace / "deduplication_stats.json"
    duplicate_map = {}      # filename → parent_filename
    duplicate_filenames = set()
    if dedup_stats_path.exists():
        try:
            with open(dedup_stats_path, 'r') as f:
                dedup_stats = json.load(f)
            duplicate_map = dedup_stats.get('duplicate_map', {})
            duplicate_filenames = set(dedup_stats.get('duplicate_filenames', []))
            if duplicate_map:
                print(f"   📊 Loaded dedup info: {len(duplicate_map)} duplicate pairs")
        except Exception as e:
            print(f"   ⚠️  Could not load dedup stats: {e}")
    
    # Get all image files from deliverable output
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
    image_files = [
        f for f in final_output.iterdir() 
        if f.is_file() and f.suffix.lower() in image_extensions
    ]
    
    if not image_files:
        return {'new': 0, 'updated': 0, 'blurred': 0, 'clean': 0}
    
    print(f"   📁 Found {len(image_files)} images in deliverable/")
    
    # HEIC conversion map
    download_dir = workspace / "01_downloaded_from_drive"
    
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
        scan_dirs = [download_dir]
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
    
    # Load filename mappings from drive_metadata.json
    # New-style (drive-id based filenames on disk):
    #   disk_filename_to_drive_id:  {disk_filename: drive_file_id}
    #   disk_filename_to_original:  {disk_filename: original_drive_name}
    # Legacy (original-name based filenames on disk):
    #   filename_to_drive_id:       {original_name: drive_file_id}
    #   filename_folder_map:        {original_name: folder_id}
    disk_filename_to_drive_id = {}
    disk_filename_to_original = {}
    filename_folder_map = {}
    filename_to_drive_id = {}
    drive_meta_path = workspace / "drive_metadata.json"
    gcs_meta_path = workspace / "gcs_metadata.json"
    if drive_meta_path.exists():
        try:
            with open(drive_meta_path, 'r') as f:
                drive_meta = json.load(f)
            disk_filename_to_drive_id = drive_meta.get("disk_filename_to_drive_id", {})
            disk_filename_to_original = drive_meta.get("disk_filename_to_original", {})
            filename_folder_map = drive_meta.get("filename_folder_map", {})
            filename_to_drive_id = drive_meta.get("filename_to_drive_id", {})
            # If folder_id not provided, try to extract from metadata
            if not folder_id:
                folder_id = drive_meta.get("folder_id")
            if disk_filename_to_drive_id:
                print(f"   📊 Loaded drive-id filename mapping for {len(disk_filename_to_drive_id)} images")
        except Exception as e:
            print(f"   ⚠️  Could not load drive metadata: {e}")
    elif gcs_meta_path.exists():
        try:
            with open(gcs_meta_path, 'r') as f:
                gcs_meta = json.load(f)
            gcs_blob_to_filename = gcs_meta.get("gcs_blob_to_filename", {})
            filename_to_gcs_blob = gcs_meta.get("filename_to_gcs_blob", {})
            if not folder_id:
                folder_id = gcs_meta.get("folder_id")
            # For GCS-sourced images, filename on disk IS the blob filename
            # No drive_id mapping needed — the filename itself is the key
            print(f"   📊 Loaded GCS metadata for {gcs_meta.get('total_in_gcs', 0)} blobs")
        except Exception as e:
            print(f"   ⚠️  Could not load GCS metadata: {e}")
    
    counts = {'new': 0, 'updated': 0, 'blurred': 0, 'clean': 0}
    
    bucket_name = _BACKEND_ENV.get("GCS_BUCKET_NAME") or os.getenv("GCS_BUCKET_NAME", "")
    use_gcs = bool(bucket_name)

    # Load GCS folder map (tells us which images are in clean/ vs blur/)
    gcs_folder_map = {}  # filename → "clean" | "blur"
    gcs_map_path = workspace / "gcs_folder_map.json"
    if gcs_map_path.exists():
        try:
            with open(gcs_map_path, 'r') as f:
                gcs_folder_map = json.load(f)
            print(f"   📊 Loaded GCS folder map for {len(gcs_folder_map)} images")
        except Exception as e:
            print(f"   ⚠️  Could not load GCS folder map: {e}")
    
    for img_file in image_files:
        filename = img_file.name
        
        metadata = biometric_metadata.get(filename, {})
        action = metadata.get('action', 'unknown')
        face_count = metadata.get('face_count', 0)
        
        if action == 'obfuscated':
            compliance_status = 'blurred'
            counts['blurred'] += 1
        elif action == 'no_face':
            compliance_status = 'clean'
            counts['clean'] += 1
        else:
            compliance_status = 'processed'
        
        source_fid = folder_id
        if not source_fid:
            lookup_name = heic_conversion_map.get(filename, filename)
            source_fid = filename_folder_map.get(lookup_name) or filename_folder_map.get(filename)
        
        drive_file_id = disk_filename_to_drive_id.get(filename)
        original_drive_name = disk_filename_to_original.get(filename)
        
        if not drive_file_id:
            pre_convert_name = heic_conversion_map.get(filename)
            if pre_convert_name:
                drive_file_id = disk_filename_to_drive_id.get(pre_convert_name)
                original_drive_name = disk_filename_to_original.get(pre_convert_name)
        
        if not drive_file_id:
            lookup_name_for_drive = heic_conversion_map.get(filename, filename)
            drive_file_id = filename_to_drive_id.get(lookup_name_for_drive) or filename_to_drive_id.get(filename)
            if not original_drive_name:
                original_drive_name = heic_conversion_map.get(filename)
        
        # Determine GCS folder stage for this image (clean or blur)
        img_gcs_folder = gcs_folder_map.get(filename, "clean")

        # Build gs:// URL based on GCS folder map
        if use_gcs and source_fid:
            gcs_obj_path = build_gcs_path(source_fid, filename, img_gcs_folder)
            gs_uri = f"gs://{bucket_name}/{gcs_obj_path}"
            url = gs_uri
            image_path = gs_uri
        else:
            url = f"file://{img_file}"
            image_path = str(img_file)
        
        is_prog_blurred = compliance_status in ("blurred", "processed", "obfuscated")
        
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
                    original_filename = COALESCE(:original_filename, original_filename),
                    url = :url,
                    original_url = :url,
                    processed_url = :url,
                    is_programmatically_blurred = :is_programmatically_blurred,
                    image_path = :image_path,
                    gcs_folder = :gcs_folder
                WHERE filename = :filename
            '''), {
                'filename': filename,
                'compliance_status': compliance_status,
                'face_count': face_count,
                'processing_log': f"Action: {action}, Faces: {face_count}",
                'source_drive_folder_id': source_fid,
                'image_drive_id': drive_file_id,
                'original_filename': original_drive_name,
                'url': url,
                'is_programmatically_blurred': is_prog_blurred,
                'image_path': image_path,
                'gcs_folder': img_gcs_folder,
            })
            counts['updated'] += 1
        else:
            heic_original = heic_conversion_map.get(filename)
            orig_format = "HEIC" if heic_original else None
            orig_name_for_db = original_drive_name or heic_original

            db.execute(text('''
                INSERT INTO images (
                    filename, original_filename, original_format,
                    url, compliance_processed, compliance_status,
                    original_url, processed_url, is_improper,
                    human_faces_detected, is_using_processed,
                    processing_log, source_drive_folder_id,
                    image_drive_id, manually_blurred,
                    is_programmatically_blurred, is_manually_modified,
                    is_duplicate, parent_image, image_path,
                    gcs_folder
                )
                VALUES (
                    :filename, :original_filename, :original_format,
                    :url, TRUE, :compliance_status,
                    :url, :url, FALSE,
                    :face_count, TRUE,
                    :processing_log, :source_drive_folder_id,
                    :image_drive_id, FALSE,
                    :is_programmatically_blurred, FALSE,
                    FALSE, NULL, :image_path,
                    :gcs_folder
                )
            '''), {
                'filename': filename,
                'original_filename': orig_name_for_db,
                'original_format': orig_format,
                'url': url,
                'compliance_status': compliance_status,
                'face_count': face_count,
                'processing_log': f"Action: {action}, Faces: {face_count}",
                'source_drive_folder_id': source_fid,
                'image_drive_id': drive_file_id,
                'is_programmatically_blurred': is_prog_blurred,
                'image_path': image_path,
                'gcs_folder': img_gcs_folder,
            })
            counts['new'] += 1
            existing_filenames.add(filename)
    
    # Mark duplicates from dedup stats
    if duplicate_map:
        dup_count = 0
        for dup_filename, parent_filename in duplicate_map.items():
            if dup_filename not in existing_filenames:
                raw_path = download_dir / dup_filename
                if not raw_path.exists():
                    continue
                    
                dup_drive_id = disk_filename_to_drive_id.get(dup_filename)
                dup_original_name = disk_filename_to_original.get(dup_filename)
                
                if not dup_drive_id:
                    pre_convert = heic_conversion_map.get(dup_filename)
                    if pre_convert:
                        dup_drive_id = disk_filename_to_drive_id.get(pre_convert)
                        dup_original_name = disk_filename_to_original.get(pre_convert)
                
                if not dup_drive_id:
                    lookup = heic_conversion_map.get(dup_filename, dup_filename)
                    dup_drive_id = filename_to_drive_id.get(lookup) or filename_to_drive_id.get(dup_filename)
                
                heic_original = heic_conversion_map.get(dup_filename)
                orig_format = "HEIC" if heic_original else None
                orig_name_for_dup = dup_original_name or heic_original
                
                # Duplicates are always in input/ (they exist in GCS already)
                if use_gcs and source_fid:
                    dup_gcs_obj = build_gcs_path(source_fid, dup_filename, "input")
                    dup_url = f"gs://{bucket_name}/{dup_gcs_obj}"
                    dup_image_path = dup_url
                else:
                    dup_url = f"file://{raw_path}"
                    dup_image_path = str(raw_path)

                db.execute(text('''
                    INSERT INTO images (
                        filename, original_filename, original_format,
                        url, compliance_processed, compliance_status,
                        original_url, processed_url, is_improper,
                        human_faces_detected, is_using_processed,
                        processing_log, source_drive_folder_id,
                        image_drive_id, manually_blurred,
                        is_programmatically_blurred, is_manually_modified,
                        is_duplicate, parent_image, image_path,
                        gcs_folder
                    )
                    VALUES (
                        :filename, :original_filename, :original_format,
                        :url, FALSE, 'duplicate',
                        :url, NULL, FALSE,
                        0, FALSE,
                        'Marked as duplicate', :source_drive_folder_id,
                        :image_drive_id, FALSE,
                        FALSE, FALSE,
                        TRUE, :parent_image, :image_path,
                        'input'
                    )
                '''), {
                    'filename': dup_filename,
                    'original_filename': orig_name_for_dup,
                    'original_format': orig_format,
                    'url': dup_url,
                    'source_drive_folder_id': source_fid,
                    'image_drive_id': dup_drive_id,
                    'parent_image': parent_filename,
                    'image_path': dup_image_path,
                })
                dup_count += 1
                existing_filenames.add(dup_filename)
        
        if dup_count:
            print(f"   📊 Recorded {dup_count} duplicate images in DB")
    
    return counts


def import_images_from_pipeline():
    """Import images from pipeline workspace to database with biometric metadata."""
    
    # Use PIPELINE_WORKSPACE from .env (e.g. /tmp/pipeline_workspace)
    env_workspace = _BACKEND_ENV.get("PIPELINE_WORKSPACE") or os.getenv("PIPELINE_WORKSPACE")
    if env_workspace:
        pipeline_workspace = Path(env_workspace)
    else:
        # Fallback to legacy path relative to this file
        pipeline_workspace = Path(__file__).parent / "master_pipeline" / "pipeline_workspace"
    
    print(f"📂 Pipeline workspace: {pipeline_workspace}")
    
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
        legacy_final = pipeline_workspace / "deliverable"
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
        
        # Cleanup local files after successful GCS upload
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if bucket_name and (total_new > 0 or total_updated > 0):
            try:
                if folders_dir.exists():
                    for folder_dir in sorted([d for d in folders_dir.iterdir() if d.is_dir()]):
                        shutil.rmtree(str(folder_dir), ignore_errors=True)
                    print(f"🧹 Cleaned up local pipeline workspace (files now in GCS)")
            except Exception as cleanup_err:
                print(f"⚠️  Cleanup warning: {cleanup_err}")
        
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
