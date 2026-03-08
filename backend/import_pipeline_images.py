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
    
    counts = {'new': 0, 'updated': 0, 'blurred': 0, 'clean': 0}
    
    # Determine relative path prefix for URLs
    # For per-folder workspaces: master_pipeline/pipeline_workspace/folders/{folder_id}/deliverable/
    # For legacy:                master_pipeline/pipeline_workspace/deliverable/
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
        
        # Determine compliance status from biometric metadata
        if action == 'obfuscated':
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
        
        # ── Resolve Google Drive file ID and original filename ──
        # New-style: disk filename IS the drive file ID (e.g. "abc123.jpg")
        drive_file_id = disk_filename_to_drive_id.get(filename)
        original_drive_name = disk_filename_to_original.get(filename)
        
        # For HEIC-converted files: the HEIC disk name was drive_id.heic → now drive_id.jpg
        # Check heic_conversion_map for the pre-conversion disk name
        if not drive_file_id:
            pre_convert_name = heic_conversion_map.get(filename)  # e.g. "abc123.heic"
            if pre_convert_name:
                drive_file_id = disk_filename_to_drive_id.get(pre_convert_name)
                original_drive_name = disk_filename_to_original.get(pre_convert_name)
        
        # Legacy fallback (old-style downloads where disk name = original name)
        if not drive_file_id:
            lookup_name_for_drive = heic_conversion_map.get(filename, filename)
            drive_file_id = filename_to_drive_id.get(lookup_name_for_drive) or filename_to_drive_id.get(filename)
            # In legacy mode, original_filename is from HEIC conversion only
            if not original_drive_name:
                original_drive_name = heic_conversion_map.get(filename)
        
        # URL path relative to backend directory
        relative_path = f"{rel_workspace}/deliverable/{filename}"
        url = f"file://{relative_path}"
        image_path = str(img_file)
        
        # Determine if pipeline blurred this image
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
                    original_url = :original_url,
                    processed_url = :processed_url,
                    is_programmatically_blurred = :is_programmatically_blurred,
                    image_path = :image_path
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
                'original_url': relative_path,
                'processed_url': relative_path,
                'is_programmatically_blurred': is_prog_blurred,
                'image_path': image_path,
            })
            counts['updated'] += 1
        else:
            heic_original = heic_conversion_map.get(filename)
            orig_format = "HEIC" if heic_original else None
            # original_filename: prefer Drive original name, fall back to HEIC original
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
                    is_duplicate, parent_image, image_path
                )
                VALUES (
                    :filename, :original_filename, :original_format,
                    :url, TRUE, :compliance_status,
                    :original_url, :processed_url, FALSE,
                    :face_count, TRUE,
                    :processing_log, :source_drive_folder_id,
                    :image_drive_id, FALSE,
                    :is_programmatically_blurred, FALSE,
                    FALSE, NULL, :image_path
                )
            '''), {
                'filename': filename,
                'original_filename': orig_name_for_db,
                'original_format': orig_format,
                'url': url,
                'compliance_status': compliance_status,
                'face_count': face_count,
                'original_url': relative_path,
                'processed_url': relative_path,
                'processing_log': f"Action: {action}, Faces: {face_count}",
                'source_drive_folder_id': source_fid,
                'image_drive_id': drive_file_id,
                'is_programmatically_blurred': is_prog_blurred,
                'image_path': image_path,
            })
            counts['new'] += 1
            existing_filenames.add(filename)  # prevent duplicates across folders
    
    # Now mark duplicates in DB from dedup stats (images not in deliverable but in raw downloads)
    if duplicate_map:
        dup_count = 0
        for dup_filename, parent_filename in duplicate_map.items():
            # These files are NOT in deliverable (they were excluded), so record them separately
            if dup_filename not in existing_filenames:
                # Check if raw file exists on disk
                raw_path = download_dir / dup_filename
                if not raw_path.exists():
                    continue
                    
                # Resolve drive metadata (new-style first, then legacy)
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
                
                relative_dup_path = f"{rel_workspace}/01_downloaded_from_drive/{dup_filename}"
                dup_url = f"file://{relative_dup_path}"

                db.execute(text('''
                    INSERT INTO images (
                        filename, original_filename, original_format,
                        url, compliance_processed, compliance_status,
                        original_url, processed_url, is_improper,
                        human_faces_detected, is_using_processed,
                        processing_log, source_drive_folder_id,
                        image_drive_id, manually_blurred,
                        is_programmatically_blurred, is_manually_modified,
                        is_duplicate, parent_image, image_path
                    )
                    VALUES (
                        :filename, :original_filename, :original_format,
                        :url, FALSE, 'duplicate',
                        :original_url, NULL, FALSE,
                        0, FALSE,
                        'Marked as duplicate', :source_drive_folder_id,
                        :image_drive_id, FALSE,
                        FALSE, FALSE,
                        TRUE, :parent_image, :image_path
                    )
                '''), {
                    'filename': dup_filename,
                    'original_filename': orig_name_for_dup,
                    'original_format': orig_format,
                    'url': dup_url,
                    'original_url': relative_dup_path,
                    'source_drive_folder_id': source_fid,
                    'image_drive_id': dup_drive_id,
                    'parent_image': parent_filename,
                    'image_path': str(raw_path),
                })
                dup_count += 1
                existing_filenames.add(dup_filename)
        
        if dup_count:
            print(f"   📊 Recorded {dup_count} duplicate images in DB")
    
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
