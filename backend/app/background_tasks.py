"""
Background task scheduler for automated image processing
Runs every 2 hours to:
1. Check for new images in Google Drive
2. Process unprocessed images through biometric pipeline
3. Upload results back to Google Drive

Features:
- Multithreaded processing for speed
- Progress bar for visibility
- Automatic retry on failure
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
import sys
import re
import io
import subprocess
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from google.oauth2 import service_account
from googleapiclient.discovery import build
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from app.config import settings
from app.database import SessionLocal, engine
from app.models.image import Image
from app.utils.gdrive_upload import upload_image_to_drive, find_or_create_folder

logger = logging.getLogger(__name__)

# Paths - Reference master_pipeline in same backend directory
pipeline_base = Path(__file__).parent.parent / "master_pipeline" / "biometric_compliance_pipeline"
temp_download = pipeline_base / "data" / "gdrive_temp"


class AutoImageProcessor:
    """Automatic image processor that runs periodically"""
    
    def __init__(self):
        self.is_running = False
        self.last_run = None
        self.processed_count = 0
        self.failed_count = 0
        
    def get_drive_service(self):
        """Create Google Drive API service"""
        creds_dict = settings.google_service_account_credentials
        if not creds_dict:
            raise Exception("Google Drive credentials not configured")
        
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        return build('drive', 'v3', credentials=credentials)
    
    async def import_new_images_from_drive(self, db: Session) -> int:
        """
        Scan Google Drive folder RECURSIVELY and import any new images not in database
        Returns: Number of new images imported
        """
        try:
            service = self.get_drive_service()
            folder_id = settings.GOOGLE_DRIVE_FOLDER_ID
            
            # Recursively scan all subfolders for images
            all_images = []
            
            def scan_folder_recursive(current_folder_id, path=""):
                """Recursively scan folder and subfolders for images"""
                # Get all items in current folder
                query = f"'{current_folder_id}' in parents and trashed=false"
                results = service.files().list(
                    q=query,
                    fields="files(id, name, mimeType)",
                    pageSize=1000
                ).execute()
                
                items = results.get('files', [])
                
                for item in items:
                    # Skip processed_images folder (output folder)
                    if item['name'] in ['processed_images', 'blurred', 'clean']:
                        continue
                    
                    if item['mimeType'] == 'application/vnd.google-apps.folder':
                        # Recursively scan subfolder
                        new_path = f"{path}/{item['name']}" if path else item['name']
                        scan_folder_recursive(item['id'], new_path)
                    elif item['mimeType'].startswith('image/'):
                        # Found an image
                        all_images.append({
                            'id': item['id'],
                            'name': item['name'],
                            'path': path
                        })
            
            # Start recursive scan
            logger.info("🔍 Scanning Google Drive recursively for images...")
            scan_folder_recursive(folder_id)
            logger.info(f"Found {len(all_images)} total images in Google Drive")
            
            # Get existing filenames from database
            existing_filenames = {row[0] for row in db.execute(
                text("SELECT filename FROM images")
            ).fetchall()}
            
            new_count = 0
            for img in all_images:
                filename = img['name']
                
                # Skip if already in database
                if filename in existing_filenames:
                    continue
                
                file_id = img['id']
                url = f"https://drive.google.com/uc?export=view&id={file_id}"
                
                # Insert into database
                db.execute(text('''
                    INSERT INTO images (filename, url, compliance_processed)
                    VALUES (:filename, :url, FALSE)
                '''), {
                    'filename': filename,
                    'url': url
                })
                
                new_count += 1
                logger.info(f"  ✅ Imported new image: {filename} (from: {img['path']})")
            
            db.commit()
            
            if new_count > 0:
                logger.info(f"✅ Imported {new_count} new images from Google Drive")
            else:
                logger.info("✅ No new images found in Google Drive")
            
            return new_count
            
        except Exception as e:
            logger.error(f"❌ Failed to import images from Google Drive: {e}")
            return 0
    
    def download_gdrive_image(self, file_id: str, dest_path: Path) -> bool:
        """Download image from Google Drive"""
        try:
            service = self.get_drive_service()
            
            # Get file content
            request = service.files().get_media(fileId=file_id)
            
            # Download file
            with open(dest_path, 'wb') as f:
                downloader = request.execute()
                f.write(downloader)
            
            return True
        except Exception as e:
            logger.error(f"    ❌ Download failed: {e}")
            return False
    
    def process_single_image(self, img_data: tuple, folders: dict) -> dict:
        """
        Process a single image (thread-safe)
        Downloads from Google Drive, processes locally, serves from local
        Returns: dict with result info
        """
        img_id, filename, url = img_data
        
        # Skip screenshots and non-photo files
        skip_patterns = ['screenshot', 'screen shot', 'whatsapp image']
        filename_lower = filename.lower()
        if any(pattern in filename_lower for pattern in skip_patterns):
            # Mark as clean without processing (not a real photo)
            db = SessionLocal()
            try:
                safe_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.')).rstrip()
                local_path = f"file://{str(pipeline_base / 'data' / 'processed' / safe_filename)}"
                
                db.execute(text('''
                    UPDATE images 
                    SET original_url = :original_url,
                        processed_url = :processed_url,
                        url = :url,
                        is_using_processed = FALSE,
                        compliance_processed = TRUE,
                        compliance_status = 'skipped',
                        human_faces_detected = 0,
                        processing_method = 'auto-skip',
                        processing_log = 'Skipped: Screenshot/WhatsApp image'
                    WHERE id = :id
                '''), {
                    'url': local_path,
                    'original_url': url,
                    'processed_url': local_path,
                    'id': img_id
                })
                db.commit()
                db.close()
                return {'status': 'skipped', 'id': img_id, 'filename': filename}
            except Exception as e:
                db.close()
                return {'status': 'failed', 'reason': str(e), 'id': img_id, 'filename': filename}
        
        # Create new DB session for this thread
        db = SessionLocal()
        
        try:
            # Extract Google Drive file ID
            gdrive_match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
            if not gdrive_match:
                db.close()
                return {'status': 'failed', 'reason': 'Invalid URL', 'id': img_id, 'filename': filename}
            
            file_id = gdrive_match.group(1)
            safe_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.')).rstrip()
            
            # Create local folders
            processed_folder = pipeline_base / "data" / "processed"
            blurred_folder = pipeline_base / "data" / "processed" / "blurred"
            clean_folder = pipeline_base / "data" / "processed" / "clean"
            
            processed_folder.mkdir(parents=True, exist_ok=True)
            blurred_folder.mkdir(parents=True, exist_ok=True)
            clean_folder.mkdir(parents=True, exist_ok=True)
            
            # Download to temp
            temp_file = temp_download / safe_filename
            if not self.download_gdrive_image(file_id, temp_file):
                db.close()
                return {'status': 'failed', 'reason': 'Download failed', 'id': img_id, 'filename': filename}
            
            # Run pipeline with increased timeout (10 minutes for complex images)
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(pipeline_base / "scripts" / "stage3_obfuscate_faces_enhanced.py"),
                        "--input", str(temp_download),
                        "--output", str(pipeline_base / "data" / "obfuscated")
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minutes for very complex images
                )
            except subprocess.TimeoutExpired:
                # Image took too long - treat as clean (skip blurring)
                print(f"  ⏱️  TIMEOUT: {filename} - treating as clean", flush=True)
                logger.warning(f"Pipeline timeout for {filename}, treating as clean")
                
                # Save as clean
                final_clean_path = clean_folder / safe_filename
                if temp_file.exists():
                    import shutil
                    shutil.copy2(str(temp_file), str(final_clean_path))
                
                local_clean_url = f"file://{str(final_clean_path)}"
                
                db.execute(text('''
                    UPDATE images 
                    SET url = :url,
                        original_url = :original_url,
                        processed_url = :processed_url,
                        is_using_processed = FALSE,
                        compliance_processed = TRUE,
                        compliance_status = 'timeout',
                        human_faces_detected = 0,
                        processing_method = 'timeout-skip',
                        processing_log = 'Pipeline timeout after 600s, saved as clean'
                    WHERE id = :id
                '''), {
                    'url': local_clean_url,
                    'original_url': local_clean_url,
                    'processed_url': local_clean_url,
                    'id': img_id
                })
                db.commit()
                
                db.close()
                if temp_file.exists():
                    temp_file.unlink()
                    
                return {'status': 'timeout', 'id': img_id, 'filename': filename}
            
            # Check output
            blurred_file = pipeline_base / "data" / "obfuscated" / safe_filename
            original_url = url
            
            if blurred_file.exists():
                # Face detected - save blurred version locally
                final_blurred_path = blurred_folder / safe_filename
                blurred_file.rename(final_blurred_path)
                
                local_blurred_url = f"file://{str(final_blurred_path)}"
                local_original_url = f"file://{str(clean_folder / safe_filename)}"
                
                # Save original to clean folder for reference (if temp file still exists)
                if temp_file.exists():
                    import shutil
                    shutil.copy2(str(temp_file), str(clean_folder / safe_filename))
                
                print(f"  🔐 BLURRED: {filename} → {final_blurred_path.name}", flush=True)
                
                # Update database with local paths
                db.execute(text('''
                    UPDATE images 
                    SET url = :url,
                        original_url = :original_url,
                        processed_url = :processed_url,
                        is_using_processed = TRUE,
                        compliance_processed = TRUE,
                        compliance_status = 'processed',
                        human_faces_detected = 1,
                        processing_method = 'opencv'
                    WHERE id = :id
                '''), {
                    'url': local_blurred_url,
                    'original_url': local_original_url,
                    'processed_url': local_blurred_url,
                    'id': img_id
                })
                db.commit()
                
                db.close()
                if temp_file.exists():
                    temp_file.unlink()
                    
                return {'status': 'blurred', 'id': img_id, 'filename': filename}
                
            else:
                # No faces detected - save clean image locally
                final_clean_path = clean_folder / safe_filename
                
                # Copy from temp if it exists
                if temp_file.exists():
                    import shutil
                    shutil.copy2(str(temp_file), str(final_clean_path))
                
                local_clean_url = f"file://{str(final_clean_path)}"
                
                # Update database with local path
                db.execute(text('''
                    UPDATE images 
                    SET url = :url,
                        original_url = :original_url,
                        processed_url = :processed_url,
                        is_using_processed = FALSE,
                        compliance_processed = TRUE,
                        compliance_status = 'clean',
                        human_faces_detected = 0,
                        processing_method = 'opencv'
                    WHERE id = :id
                '''), {
                    'url': local_clean_url,
                    'original_url': local_clean_url,
                    'processed_url': local_clean_url,
                    'id': img_id
                })
                db.commit()
                
                db.close()
                if temp_file.exists():
                    temp_file.unlink()
                    
                return {'status': 'clean', 'id': img_id, 'filename': filename}
                
        except Exception as e:
            db.close()
            if temp_file.exists():
                temp_file.unlink()
            return {'status': 'failed', 'reason': str(e), 'id': img_id, 'filename': filename}
    
    async def process_unprocessed_images(self, db: Session) -> tuple[int, int]:
        """
        Process all unprocessed images through biometric pipeline
        Uses multithreading for parallel processing
        Returns: (processed_count, failed_count)
        """
        # Get ALL unprocessed images (no limit)
        result = db.execute(text('''
            SELECT id, filename, url 
            FROM images 
            WHERE compliance_processed = FALSE
            ORDER BY id
        '''))
        images = result.fetchall()
        
        if not images:
            logger.info("✅ All images are already processed")
            return 0, 0
        
        logger.info(f"📊 Found {len(images)} unprocessed images")
        
        # Ensure folders exist
        temp_download.mkdir(parents=True, exist_ok=True)
        obfuscated_dir = pipeline_base / "data" / "obfuscated"
        obfuscated_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup Google Drive folders
        try:
            main_folder_id = settings.GOOGLE_DRIVE_FOLDER_ID
            processed_folder_id = find_or_create_folder("processed_images", main_folder_id)
            blurred_folder_id = find_or_create_folder("blurred", processed_folder_id)
            folders = {'blurred': blurred_folder_id}
        except Exception as e:
            logger.error(f"❌ Failed to setup Google Drive folders: {e}")
            return 0, len(images)
        
        # Process images in parallel with progress bar
        processed_count = 0
        blurred_count = 0
        clean_count = 0
        skipped_count = 0
        timeout_count = 0
        failed_count = 0
        
        # Use ThreadPoolExecutor for parallel processing
        max_workers = 4  # Process 4 images simultaneously
        
        print(f"\n{'='*70}", flush=True)
        print(f"  🔐 Processing {len(images)} images with {max_workers} threads", flush=True)
        print(f"{'='*70}\n", flush=True)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_img = {
                executor.submit(self.process_single_image, img, folders): img
                for img in images
            }
            
            # Process results with progress bar (unbuffered output)
            with tqdm(total=len(images), desc="Processing images", unit="img", 
                     bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
                     file=sys.stdout, dynamic_ncols=True) as pbar:
                
                for future in as_completed(future_to_img):
                    result = future.result()
                    
                    if result['status'] == 'blurred':
                        blurred_count += 1
                        processed_count += 1
                        pbar.write(f"  🔐 BLURRED: {result['filename']}")
                        sys.stdout.flush()
                    elif result['status'] == 'clean':
                        clean_count += 1
                        processed_count += 1
                        pbar.write(f"  ✅ CLEAN: {result['filename']}")
                        sys.stdout.flush()
                    elif result['status'] == 'skipped':
                        skipped_count += 1
                        processed_count += 1
                        pbar.write(f"  ⏭️  SKIPPED: {result['filename']}")
                        sys.stdout.flush()
                    elif result['status'] == 'timeout':
                        timeout_count += 1
                        processed_count += 1
                        pbar.write(f"  ⏱️  TIMEOUT: {result['filename']}")
                        sys.stdout.flush()
                    else:
                        failed_count += 1
                        pbar.write(f"  ❌ FAILED: {result['filename']} - {result.get('reason', 'Unknown')}")
                        sys.stdout.flush()
                    
                    pbar.update(1)
        
        print(f"\n{'='*70}", flush=True)
        print(f"  ✨ Processing Complete!", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"  🔐 Faces blurred: {blurred_count}", flush=True)
        print(f"  ✅ Clean: {clean_count}", flush=True)
        print(f"  ⏭️  Skipped (screenshots/WhatsApp): {skipped_count}", flush=True)
        print(f"  ⏱️  Timeout (saved as clean): {timeout_count}", flush=True)
        print(f"  📁 Total processed: {processed_count}", flush=True)
        print(f"  ❌ Failed: {failed_count}", flush=True)
        print(f"{'='*70}\n", flush=True)
        
        return processed_count, failed_count
    
    async def run_processing_cycle(self):
        """Run a complete processing cycle"""
        if self.is_running:
            logger.info("⚠️  Processing cycle already running, skipping...")
            return
        
        self.is_running = True
        start_time = datetime.now()
        
        logger.info("=" * 70)
        logger.info(f"🔄 AUTO-PROCESSOR: Starting cycle at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)
        
        db = SessionLocal()
        try:
            # Step 1: Import new images from Google Drive
            logger.info("\n📥 Step 1: Checking for new images in Google Drive...")
            new_images = await self.import_new_images_from_drive(db)
            
            # Step 2: Process unprocessed images
            logger.info("\n🔐 Step 2: Processing unprocessed images...")
            processed, failed = await self.process_unprocessed_images(db)
            
            # Update counters
            self.processed_count += processed
            self.failed_count += failed
            self.last_run = datetime.now()
            
            # Summary
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info("\n" + "=" * 70)
            logger.info("✨ AUTO-PROCESSOR: Cycle Complete")
            logger.info("=" * 70)
            logger.info(f"📊 Results:")
            logger.info(f"   📥 New images imported: {new_images}")
            logger.info(f"   ✅ Images processed: {processed}")
            logger.info(f"   ❌ Failed: {failed}")
            logger.info(f"   ⏱️  Time taken: {elapsed:.1f} seconds")
            logger.info(f"   📈 Total processed (lifetime): {self.processed_count}")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"❌ Processing cycle failed: {e}", exc_info=True)
        finally:
            db.close()
            self.is_running = False
    
    async def start_scheduler(self):
        """Start the background scheduler (runs every 2 hours)"""
        logger.info("🚀 Auto-processor scheduler started (runs every 2 hours)")
        
        # Don't run immediately - Makefile handles first run
        # Just schedule recurring runs every 2 hours
        while True:
            await asyncio.sleep(2 * 60 * 60)  # 2 hours in seconds
            await self.run_processing_cycle()


# Global instance
auto_processor = AutoImageProcessor()


async def start_background_tasks():
    """Start all background tasks - returns immediately"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("🚀 Scheduling auto-processor (runs every 2 hours)")
        
        # Create task without awaiting - runs in background
        asyncio.create_task(auto_processor.start_scheduler())
        
        logger.info("✅ Background tasks scheduled successfully")
    except Exception as e:
        logger.error(f"❌ Failed to schedule background tasks: {e}")
        # Don't raise - allow app to start anyway
