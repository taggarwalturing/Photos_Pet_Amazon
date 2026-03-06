"""
Import images from master pipeline's final output into the database.
This script imports images from the pipeline workspace into the annotation tool database,
including biometric processing metadata from obfuscation_results.json.
"""
import sys
import json
from pathlib import Path
from sqlalchemy import text
from app.database import SessionLocal
from app.config import settings

def import_images_from_pipeline():
    """Import images from pipeline workspace to database with biometric metadata."""
    
    # Path to final output
    pipeline_workspace = Path(__file__).parent / "master_pipeline" / "pipeline_workspace"
    final_output = pipeline_workspace / "04_final_output"
    biometric_processed = pipeline_workspace / "03_biometric_processed"
    
    if not final_output.exists():
        print(f"❌ Final output folder not found: {final_output}")
        print(f"   Please run the master pipeline first.")
        return 0
    
    # Load biometric results JSON
    results_json_path = Path(__file__).parent / "master_pipeline" / "biometric_compliance_pipeline" / "results" / "obfuscation_results.json"
    biometric_metadata = {}
    
    if results_json_path.exists():
        try:
            with open(results_json_path, 'r') as f:
                results_data = json.load(f)
                for result in results_data.get('results', []):
                    filename = result.get('image') or result.get('output_name')
                    if filename:
                        biometric_metadata[filename] = result
            print(f"📊 Loaded biometric metadata for {len(biometric_metadata)} images")
        except Exception as e:
            print(f"⚠️  Could not load biometric results: {e}")
    else:
        print(f"⚠️  No biometric results found at {results_json_path}")
    
    # Check which images are in blurred vs clean folders
    blurred_folder = biometric_processed / "blurred"
    clean_folder = biometric_processed / "clean"
    
    blurred_images = set()
    clean_images = set()
    
    if blurred_folder.exists():
        blurred_images = {f.name for f in blurred_folder.iterdir() if f.is_file()}
        print(f"📁 Found {len(blurred_images)} images in blurred/ folder")
    
    if clean_folder.exists():
        clean_images = {f.name for f in clean_folder.iterdir() if f.is_file()}
        print(f"📁 Found {len(clean_images)} images in clean/ folder")
    
    # Get all image files from final output
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
    image_files = [
        f for f in final_output.iterdir() 
        if f.is_file() and f.suffix.lower() in image_extensions
    ]
    
    if not image_files:
        print(f"❌ No images found in {final_output}")
        return 0
    
    print(f"📁 Found {len(image_files)} images in final output")
    
    # ── Build HEIC → JPG conversion map ──
    download_dir = pipeline_workspace / "01_downloaded_from_drive"
    unique_dir = pipeline_workspace / "02_unique_images"
    
    # Method 1: Read from _heic_conversions.json manifest (new flow)
    heic_conversion_map = {}  # jpg_filename → heic_original_filename
    manifest_path = download_dir / "_heic_conversions.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            for jpg_name, info in manifest.items():
                heic_conversion_map[jpg_name] = info['original_filename']
            print(f"📷 Loaded {len(heic_conversion_map)} HEIC conversions from manifest")
        except Exception as e:
            print(f"⚠️  Could not read HEIC manifest: {e}")
    
    # Method 2: Fallback - scan disk for HEIC files (legacy flow)
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
    
    if heic_conversion_map:
        print(f"📷 Detected {len(heic_conversion_map)} HEIC → JPG conversions")
    
    db = SessionLocal()
    try:
        # Get existing filenames
        existing = db.execute(text("SELECT filename FROM images")).fetchall()
        existing_filenames = {row[0] for row in existing}
        
        print(f"📊 Database has {len(existing_filenames)} existing images")
        
        new_count = 0
        skipped_count = 0
        updated_count = 0
        blurred_count = 0
        clean_count = 0
        
        for img_file in image_files:
            filename = img_file.name
            
            # Determine compliance status and face count from metadata
            metadata = biometric_metadata.get(filename, {})
            action = metadata.get('action', 'unknown')
            face_count = metadata.get('face_count', 0)
            
            # Determine status based on folder location and action
            is_blurred = filename in blurred_images
            is_clean = filename in clean_images
            
            if is_blurred:
                compliance_status = 'blurred'
                blurred_count += 1
            elif is_clean:
                compliance_status = 'clean'
                clean_count += 1
            elif action == 'obfuscated':
                compliance_status = 'blurred'
                blurred_count += 1
            elif action == 'no_face':
                compliance_status = 'clean'
                clean_count += 1
            else:
                compliance_status = 'processed'
            
            # For local files, use file:// URL with relative path from backend directory
            relative_path = f"master_pipeline/pipeline_workspace/04_final_output/{filename}"
            url = f"file://{relative_path}"
            
            if filename in existing_filenames:
                # Update existing image with biometric metadata
                db.execute(text('''
                    UPDATE images 
                    SET 
                        compliance_processed = TRUE,
                        compliance_status = :compliance_status,
                        human_faces_detected = :face_count,
                        is_using_processed = TRUE,
                        processing_log = :processing_log
                    WHERE filename = :filename
                '''), {
                    'filename': filename,
                    'compliance_status': compliance_status,
                    'face_count': face_count,
                    'processing_log': f"Action: {action}, Faces: {face_count}"
                })
                updated_count += 1
                skipped_count += 1
            else:
                # Check if this file was converted from HEIC
                heic_original = heic_conversion_map.get(filename)
                orig_format = "HEIC" if heic_original else None
                
                # Insert new image
            db.execute(text('''
                INSERT INTO images (
                    filename, 
                        original_filename,
                        original_format,
                    url, 
                    compliance_processed,
                    compliance_status,
                    original_url,
                    processed_url,
                    is_improper,
                    human_faces_detected,
                        is_using_processed,
                        processing_log
                )
                VALUES (
                    :filename, 
                        :original_filename,
                        :original_format,
                    :url, 
                    TRUE,
                        :compliance_status,
                    :original_url,
                    :processed_url,
                    FALSE,
                        :face_count,
                        TRUE,
                        :processing_log
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
                    'processing_log': f"Action: {action}, Faces: {face_count}"
            })
            
            new_count += 1
            
            if (new_count + updated_count) % 100 == 0:
                print(f"   Processed {new_count + updated_count} images...")
        
        db.commit()
        
        print(f"\n✅ Import complete!")
        print(f"   • New images imported: {new_count}")
        print(f"   • Existing images updated: {updated_count}")
        print(f"   • Already in database: {skipped_count}")
        print(f"   • Images with blurred faces: {blurred_count}")
        print(f"   • Clean images (no faces): {clean_count}")
        print(f"   • Total in database: {len(existing_filenames) + new_count}")
        
        return new_count
        
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
