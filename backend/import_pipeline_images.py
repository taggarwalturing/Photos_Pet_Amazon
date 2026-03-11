"""
Import images from master pipeline's deliverable output into the database.

Supports two workspace layouts:
  1. Per-folder workspaces (new):  pipeline_workspace/folders/{folder_id}/deliverable/
  2. Legacy flat workspace:        pipeline_workspace/deliverable/

Each per-folder workspace carries its own drive_metadata.json, obfuscation_results.json,
and deduplication_stats.json.

If deduplication_stats.json is missing, the importer will automatically run the
deduplicator on the downloaded images before importing, so duplicates are always
detected — no manual intervention required.

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

# Setup paths for deduplicator import
_SCRIPT_DIR = Path(__file__).parent
_MASTER_PIPELINE_DIR = _SCRIPT_DIR / "master_pipeline"
_DEDUP_DIR = _MASTER_PIPELINE_DIR / "FaceDetectionBlur"

# Register HEIC/HEIF support for PIL (needed for dedup scan of HEIC images)
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except ImportError:
    _HEIF_AVAILABLE = False

# Explicitly load .env to avoid stale os.environ
_BACKEND_ENV = dotenv_values(Path(__file__).parent / ".env")


def _auto_run_dedup(scan_folder: Path, stats_output_path: Path) -> dict:
    """
    Automatically run the deduplicator on a folder of images.
    Called when no pre-computed deduplication_stats.json is found.

    1. Converts any HEIC/HEIF/AVIF → JPEG (in-place) so they are scannable.
    2. Runs AdvancedDeduplicator on all scannable images.
    3. Saves deduplication_stats.json for future re-imports.

    Returns:
        dict with 'duplicate_map' and 'duplicate_filenames', or {} if dedup failed.
    """
    if not scan_folder.is_dir():
        return {}

    # Scannable image extensions (what the deduplicator supports)
    scannable_exts = {'.jpg', '.jpeg', '.png', '.webp'}
    heic_exts = {'.heic', '.heif', '.avif'}

    all_files = [f for f in scan_folder.iterdir() if f.is_file() and not f.name.startswith(('_', '.'))]
    image_files = [f for f in all_files if f.suffix.lower() in (scannable_exts | heic_exts)]

    if len(image_files) < 2:
        print(f"   ⏭️  Only {len(image_files)} image(s) in {scan_folder.name} — skipping dedup")
        return {}

    # ── Step 1: Convert HEIC/HEIF/AVIF to JPEG so dedup can scan them ──
    heic_files = [f for f in image_files if f.suffix.lower() in heic_exts]
    if heic_files:
        if not _HEIF_AVAILABLE:
            print(f"   ⚠️  {len(heic_files)} HEIC files found but pillow-heif not installed — they will be skipped by dedup")
        else:
            from PIL import Image as PILImage
            converted = 0
            originals_dir = scan_folder / '_heic_originals'
            originals_dir.mkdir(exist_ok=True)
            for hf in heic_files:
                jpg_path = scan_folder / (hf.stem + '.jpeg')
                if jpg_path.exists():
                    continue  # already converted
                try:
                    pil_img = PILImage.open(str(hf))
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    pil_img.save(str(jpg_path), 'JPEG', quality=95)
                    # Move original to _heic_originals
                    shutil.move(str(hf), str(originals_dir / hf.name))
                    converted += 1
                except Exception as e:
                    print(f"   ⚠️  Failed to convert {hf.name}: {e}")
            if converted:
                print(f"   🔄 Auto-converted {converted} HEIC/HEIF/AVIF → JPEG for dedup scan")

    # ── Step 2: Run deduplicator ──
    # Refresh file list after conversion
    scannable_images = [
        f for f in scan_folder.iterdir()
        if f.is_file() and f.suffix.lower() in scannable_exts and not f.name.startswith(('_', '.'))
    ]

    if len(scannable_images) < 2:
        print(f"   ⏭️  Only {len(scannable_images)} scannable image(s) — skipping dedup")
        return {}

    print(f"   🔍 Auto-running deduplication on {len(scannable_images)} images...")

    try:
        # Import deduplicator
        if str(_DEDUP_DIR) not in sys.path:
            sys.path.insert(0, str(_DEDUP_DIR))
        from image_deduplicator_advanced import AdvancedDeduplicator

        threshold = float(_BACKEND_ENV.get('DEDUP_THRESHOLD', '0.85'))
        deduplicator = AdvancedDeduplicator(similarity_threshold=threshold)
        deduplicator.scan_images(scan_folder)

        if not deduplicator.images:
            print(f"   ⚠️  Deduplicator found no images")
            return {}

        deduplicator.find_duplicates()

        # Build duplicate map
        duplicate_map = {}
        for img in deduplicator.images:
            if img.is_duplicate and img.duplicate_of:
                duplicate_map[img.filename] = img.duplicate_of

        # Also include HEIC sources of duplicate JPGs
        heic_manifest_path = scan_folder / "_heic_conversions.json"
        jpg_to_heic = {}
        if heic_manifest_path.exists():
            try:
                with open(heic_manifest_path, 'r') as f:
                    heic_manifest = json.load(f)
                for jpg_name, info in heic_manifest.items():
                    jpg_to_heic[jpg_name] = info.get('original_filename', '')
            except Exception:
                pass

        extended_duplicates = set(duplicate_map.keys())
        for dup_jpg in list(duplicate_map.keys()):
            heic_source = jpg_to_heic.get(dup_jpg)
            if heic_source:
                extended_duplicates.add(heic_source)

        stats = {
            'total_images': len(scannable_images),
            'unique_images': len(scannable_images) - len(duplicate_map),
            'duplicate_images': len(duplicate_map),
            'duplicate_pairs': len(duplicate_map),
            'duplicate_map': duplicate_map,
            'duplicate_filenames': list(extended_duplicates),
            'auto_generated': True,  # Mark that this was auto-generated by importer
        }

        if duplicate_map:
            print(f"   ⚠️  Found {len(duplicate_map)} duplicate(s)!")
            for dup, parent in duplicate_map.items():
                print(f"      {dup} → duplicate of {parent}")
        else:
            print(f"   ✅ No duplicates found in {len(scannable_images)} images")

        # Save for future re-imports
        try:
            with open(stats_output_path, 'w') as f:
                json.dump(stats, f, indent=2)
            print(f"   💾 Saved dedup stats to {stats_output_path.name}")
        except Exception as e:
            print(f"   ⚠️  Could not save dedup stats: {e}")

        return stats

    except ImportError as e:
        print(f"   ⚠️  Deduplicator not available ({e}) — skipping auto-dedup")
        return {}
    except Exception as e:
        print(f"   ⚠️  Auto-dedup failed: {e}")
        return {}


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
    
    # Download directory (used for dedup scan and HEIC mapping)
    download_dir = workspace / "01_downloaded_from_drive"

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
    else:
        # ── Auto-run deduplication if no stats file exists ──
        # Scan the deliverable folder (or download folder if it exists) for duplicates
        scan_folder = download_dir if download_dir.is_dir() else final_output
        dedup_result = _auto_run_dedup(scan_folder, dedup_stats_path)
        if dedup_result:
            duplicate_map = dedup_result.get('duplicate_map', {})
            duplicate_filenames = set(dedup_result.get('duplicate_filenames', []))
    
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
        gcs_input_uri = None
        if use_gcs and source_fid:
            gcs_obj_path = build_gcs_path(source_fid, filename, img_gcs_folder)
            gs_uri = f"gs://{bucket_name}/{gcs_obj_path}"
            url = gs_uri
            image_path = gs_uri
            # Always record the original input path
            gcs_input_uri = f"gs://{bucket_name}/input/{source_fid}/{filename}"
        else:
            url = f"file://{img_file}"
            image_path = str(img_file)
        
        is_prog_blurred = compliance_status in ("blurred", "processed", "obfuscated")
        
        if filename in existing_filenames:
            db.execute(text('''
                UPDATE images 
                SET 
                    pipeline_status = 'completed',
                    compliance_status = :compliance_status,
                    human_faces_detected = :face_count,
                    is_using_processed = TRUE,
                    source_folder_id = COALESCE(source_folder_id, :source_folder_id),
                    image_drive_id = COALESCE(image_drive_id, :image_drive_id),
                    original_filename = COALESCE(:original_filename, original_filename),
                    url = :url,
                    processed_url = :url,
                    is_programmatically_blurred = :is_programmatically_blurred,
                    gcs_folder = :gcs_folder,
                    gcs_input_path = COALESCE(:gcs_input_path, gcs_input_path)
                WHERE filename = :filename
            '''), {
                'filename': filename,
                'compliance_status': compliance_status,
                'face_count': face_count,
                'source_folder_id': source_fid,
                'image_drive_id': drive_file_id,
                'original_filename': original_drive_name,
                'url': url,
                'is_programmatically_blurred': is_prog_blurred,
                'gcs_folder': img_gcs_folder,
                'gcs_input_path': gcs_input_uri,
            })
            counts['updated'] += 1
        else:
            heic_original = heic_conversion_map.get(filename)
            orig_format = "HEIC" if heic_original else None
            orig_name_for_db = original_drive_name or heic_original

            from pathlib import PurePosixPath
            image_id_stem = PurePosixPath(filename).stem

            db.execute(text('''
                INSERT INTO images (
                    image_id,
                    filename, original_filename,
                    url, pipeline_status, compliance_status,
                    processed_url, is_improper,
                    human_faces_detected, is_using_processed,
                    source_folder_id,
                    image_drive_id, manually_blurred,
                    is_programmatically_blurred, is_manually_modified,
                    is_duplicate,
                    gcs_folder, gcs_input_path
                )
                VALUES (
                    :image_id,
                    :filename, :original_filename,
                    :url, 'completed', :compliance_status,
                    :url, FALSE,
                    :face_count, TRUE,
                    :source_folder_id,
                    :image_drive_id, FALSE,
                    :is_programmatically_blurred, FALSE,
                    FALSE,
                    :gcs_folder, :gcs_input_path
                )
            '''), {
                'image_id': image_id_stem,
                'filename': filename,
                'original_filename': orig_name_for_db,
                'url': url,
                'compliance_status': compliance_status,
                'face_count': face_count,
                'source_folder_id': source_fid,
                'image_drive_id': drive_file_id,
                'is_programmatically_blurred': is_prog_blurred,
                'gcs_folder': img_gcs_folder,
                'gcs_input_path': gcs_input_uri,
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

                dup_image_id_stem = PurePosixPath(dup_filename).stem

                db.execute(text('''
                    INSERT INTO images (
                        image_id,
                        filename, original_filename,
                        url, pipeline_status, compliance_status,
                        processed_url, is_improper,
                        human_faces_detected, is_using_processed,
                        source_folder_id,
                        image_drive_id, manually_blurred,
                        is_programmatically_blurred, is_manually_modified,
                        is_duplicate,
                        gcs_folder
                    )
                    VALUES (
                        :image_id,
                        :filename, :original_filename,
                        :url, 'pending', 'duplicate',
                        NULL, FALSE,
                        0, FALSE,
                        :source_folder_id,
                        :image_drive_id, FALSE,
                        FALSE, FALSE,
                        TRUE,
                        'input'
                    )
                '''), {
                    'image_id': dup_image_id_stem,
                    'filename': dup_filename,
                    'original_filename': orig_name_for_dup,
                    'url': dup_url,
                    'source_folder_id': source_fid,
                    'image_drive_id': dup_drive_id,
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
        
        # NOTE: Workspace cleanup is handled by the pipeline runner AFTER
        # stats have been read from local metadata files (gcs_metadata.json, etc.)
        
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
