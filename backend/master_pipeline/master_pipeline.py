#!/usr/bin/env python3
"""
Complete Image Processing Pipeline
===================================

Workflow:
1. Download all images from Google Drive
2. Run deduplicator (with optional LLM validation)
3. Run biometric pipeline on unique images only
4. Upload to S3 (optional)

This saves time by:
- Not processing duplicates through expensive biometric pipeline
- Organizing images before annotation

Usage:
    python master_pipeline.py --download --deduplicate --pipeline --s3
"""

import os
import sys
import shutil
import json
from pathlib import Path
from typing import List, Dict, Optional
import argparse
from datetime import datetime
from tqdm import tqdm

# Setup paths
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import pipeline configuration
from pipeline_config import get_config

# Try to import app config (optional for standalone use)
try:
    from app.config import settings
    from app.database import SessionLocal
    from sqlalchemy import text
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False
    settings = None

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class MasterPipeline:
    """
    Complete pipeline orchestrator
    """
    
    def __init__(self, workspace_dir: Optional[str] = None, config=None):
        """
        Initialize the master pipeline.
        
        Args:
            workspace_dir: Optional workspace directory (overrides config)
            config: Optional PipelineConfig instance (uses global config if not provided)
        """
        # Get configuration
        self.config = config or get_config()
        
        # Use provided workspace or config workspace
        if workspace_dir:
            self.workspace = Path(workspace_dir)
        else:
            self.workspace = self.config.workspace
        
        self.workspace.mkdir(exist_ok=True)
        
        # Define folder structure from config
        self.folders = {
            'downloaded': self.config.downloaded_dir,
            'unique': self.config.unique_dir,
            'duplicate_clusters': self.config.duplicate_clusters_dir,
            'processed_unique': self.config.biometric_processed_dir,
            'final_output': self.config.final_output_dir,
        }
        
        # Create all folders
        for folder in self.folders.values():
            folder.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 Workspace: {self.workspace}")
        print(f"   Structure created:")
        for name, path in self.folders.items():
            print(f"     • {name}: {path.name}")
    
    def step1_download_from_drive(self) -> int:
        """
        Step 1: Download all images from Google Drive
        Returns: Number of images downloaded
        """
        print("\n" + "=" * 70)
        print("📥 STEP 1: Download Images from Google Drive")
        print("=" * 70)
        
        if not GDRIVE_AVAILABLE:
            print("❌ Google Drive libraries not available")
            return 0
        
        # Get Drive service - use config first, fallback to settings
        if self.config.google_service_account_file:
            import json
            creds_file = Path(self.config.google_service_account_file)
            if creds_file.exists():
                with open(creds_file, 'r') as f:
                    creds_dict = json.load(f)
            else:
                print(f"❌ Service account file not found: {creds_file}")
                return 0
        elif APP_AVAILABLE and settings:
            creds_dict = settings.google_service_account_credentials
        else:
            print("❌ Google Drive credentials not configured")
            print("   Set GOOGLE_SERVICE_ACCOUNT_FILE in .env or configure app settings")
            return 0
            print("❌ Google Drive credentials not configured")
            print("   Set GOOGLE_SERVICE_ACCOUNT_FILE in .env or configure app settings")
            return 0
        
        if not creds_dict.get('client_email'):
            print("❌ Invalid Google Drive credentials")
            return 0
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)
        
        # Get folder ID from config
        folder_id = self.config.google_drive_folder_id
        if not folder_id:
            print("❌ Google Drive folder ID not configured")
            print("   Set GOOGLE_DRIVE_FOLDER_ID in .env")
            return 0
        
        # List all images recursively
        print("🔍 Scanning Google Drive folders...")
        images = self._list_all_drive_images(service, folder_id)
        
        print(f"✅ Found {len(images)} images")
        
        if len(images) == 0:
            print("⚠️  No images found")
            return 0
        
        # Download images
        download_folder = self.folders['downloaded']
        print(f"\n📥 Downloading to: {download_folder}")
        
        downloaded = 0
        for img in tqdm(images, desc="Downloading"):
            try:
                # Download
                request = service.files().get_media(fileId=img['id'])
                
                output_path = download_folder / img['name']
                
                # Skip if already downloaded
                if output_path.exists():
                    continue
                
                with open(output_path, 'wb') as f:
                    from io import BytesIO
                    file_buffer = BytesIO()
                    downloader = MediaIoBaseDownload(file_buffer, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    file_buffer.seek(0)
                    f.write(file_buffer.read())
                
                downloaded += 1
                
            except Exception as e:
                print(f"❌ Failed to download {img['name']}: {e}")
        
        print(f"\n✅ Downloaded {downloaded} new images")
        print(f"📊 Total in folder: {len(list(download_folder.glob('*')))} images")
        
        return len(list(download_folder.glob('*')))
    
    def _list_all_drive_images(self, service, folder_id: str) -> List[Dict]:
        """Recursively list all images from Google Drive"""
        extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.avif', '.bmp', '.tiff', '.tif'}
        images = []
        folders_to_process = [folder_id]
        
        while folders_to_process:
            current_folder = folders_to_process.pop(0)
            query = f"'{current_folder}' in parents and trashed=false"
            page_token = None
            
            while True:
                results = service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType)',
                    pageToken=page_token,
                    pageSize=100
                ).execute()
                
                items = results.get('files', [])
                
                for item in items:
                    if item['mimeType'] == 'application/vnd.google-apps.folder':
                        folders_to_process.append(item['id'])
                    else:
                        ext = os.path.splitext(item['name'])[1].lower()
                        if ext in extensions:
                            images.append(item)
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
        
        return images
    
    def step2_deduplicate(
        self,
        use_llm: bool = None,
        threshold: float = None,
        max_llm_validations: int = None
    ) -> Dict:
        """
        Step 2: Run deduplication
        
        Creates:
        - 02_unique_images/ - Unique images (originals)
        - 02_duplicate_clusters/ - Folders for each duplicate group
        
        Args:
            use_llm: Use LLM validation (uses config if None)
            threshold: Deduplication threshold (uses config if None)
            max_llm_validations: Max LLM calls (uses config if None)
        
        Returns: Statistics
        """
        print("\n" + "=" * 70)
        print("🔍 STEP 2: Deduplication")
        print("=" * 70)
        
        # Use config values if not provided
        use_llm = use_llm if use_llm is not None else self.config.use_llm_validation
        threshold = threshold if threshold is not None else self.config.dedup_threshold
        max_llm_validations = max_llm_validations if max_llm_validations is not None else self.config.max_llm_validations
        
        input_folder = self.folders['downloaded']
        unique_folder = self.folders['unique']
        clusters_folder = self.folders['duplicate_clusters']
        
        # Check if using LLM
        if use_llm:
            print("🤖 Using LLM-enhanced validation")
            
            # Check for OpenAI API key
            if not self.config.openai_api_key:
                print("❌ OpenAI API key not configured")
                print("   Set OPENAI_API_KEY in .env")
                return {}
            
            from llm_duplicate_validator import LLMDuplicateValidator
            
            validator = LLMDuplicateValidator(
                openai_api_key=self.config.openai_api_key,
                deduplicator_threshold=threshold
            )
            
            results = validator.find_and_validate_duplicates(
                input_folder=str(input_folder),
                output_folder=str(self.workspace / "deduplication_results"),
                max_validations=max_llm_validations
            )
            
            # Load validated duplicates
            with open(self.workspace / "deduplication_results" / "validated_duplicates.json") as f:
                duplicate_pairs = json.load(f)
            
            # Build duplicate mapping
            duplicate_map = {}  # duplicate -> original
            for pair in duplicate_pairs:
                original = Path(pair['original']).name
                duplicate = Path(pair['duplicate']).name
                duplicate_map[duplicate] = original
        
        else:
            print("⚡ Using advanced deduplicator only (no LLM)")
            
            # Import and run deduplicator
            sys.path.insert(0, str(SCRIPT_DIR / 'FaceDetectionBlur'))
            from image_deduplicator_advanced import AdvancedDeduplicator
            
            # Note: AdvancedDeduplicator uses similarity_threshold (higher = more similar required)
            # Pass threshold directly - higher values mean stricter matching
            similarity_threshold = threshold  # 0.85 means 85% similarity required
            
            # Initialize deduplicator
            deduplicator = AdvancedDeduplicator(similarity_threshold=similarity_threshold)
            
            # Scan and analyze images
            deduplicator.scan_images(input_folder)
            
            if not deduplicator.images:
                print("❌ No images found!")
                return {}
            
            # Find duplicates
            deduplicator.find_duplicates()
            
            # Create temporary output for deduplicator
            temp_dedup_output = self.workspace / 'temp_dedup'
            temp_dedup_output.mkdir(exist_ok=True)
            
            # Segregate into originals and duplicates
            deduplicator.segregate_images(temp_dedup_output)
            
            # Build duplicate mapping from deduplicator results
            duplicate_map = {}  # duplicate -> original
            for img in deduplicator.images:
                if img.is_duplicate and img.duplicate_of:
                    duplicate_map[img.filename] = img.duplicate_of
        
        print(f"\n✅ Found {len(duplicate_map)} duplicate images")
        
        # Organize into clusters
        print("\n📂 Creating cluster structure...")
        
        # Copy unique images and create clusters
        all_images = list(input_folder.glob('*'))
        originals = set()
        duplicates = set()
        
        for img_path in all_images:
            img_name = img_path.name
            
            if img_name in duplicate_map:
                # It's a duplicate
                duplicates.add(img_name)
            else:
                # Check if it's an original (has duplicates pointing to it)
                if img_name in duplicate_map.values():
                    originals.add(img_name)
                else:
                    # Truly unique (no duplicates)
                    originals.add(img_name)
        
        # Copy originals to unique folder
        print(f"\n📋 Copying {len(originals)} unique images...")
        for img_name in tqdm(originals, desc="Copying unique"):
            src = input_folder / img_name
            dst = unique_folder / img_name
            if not dst.exists():
                shutil.copy2(src, dst)
        
        # Create duplicate clusters
        print(f"\n📁 Creating duplicate clusters...")
        
        # Group duplicates by original
        clusters = {}
        for dup, orig in duplicate_map.items():
            if orig not in clusters:
                clusters[orig] = []
            clusters[orig].append(dup)
        
        for cluster_id, (original, duplicates_list) in enumerate(clusters.items(), 1):
            cluster_folder = clusters_folder / f"cluster_{cluster_id:04d}_{Path(original).stem}"
            cluster_folder.mkdir(exist_ok=True)
            
            # Copy original
            src = input_folder / original
            if src.exists():
                shutil.copy2(src, cluster_folder / f"ORIGINAL_{original}")
            
            # Copy duplicates
            for dup in duplicates_list:
                src = input_folder / dup
                if src.exists():
                    shutil.copy2(src, cluster_folder / f"duplicate_{dup}")
        
        # Clean up temp folder
        if not use_llm and temp_dedup_output.exists():
            shutil.rmtree(temp_dedup_output)
        
        stats = {
            'total_images': len(all_images),
            'unique_images': len(originals),
            'duplicate_images': len(duplicates),
            'duplicate_pairs': len(duplicate_map),
            'clusters': len(clusters),
            'compression_ratio': f"{(1 - len(originals) / len(all_images)) * 100:.1f}%" if len(all_images) > 0 else "0%"
        }
        
        print("\n📊 Deduplication Results:")
        print(f"   Total images: {stats['total_images']}")
        print(f"   Unique images: {stats['unique_images']}")
        print(f"   Duplicate images: {stats['duplicate_images']}")
        print(f"   Clusters created: {stats['clusters']}")
        print(f"   Compression: {stats['compression_ratio']}")
        
        # Save stats
        with open(self.workspace / 'deduplication_stats.json', 'w') as f:
            json.dump(stats, f, indent=2)
        
        return stats
    
    def step3_biometric_pipeline(self) -> Dict:
        """
        Step 3: Run biometric compliance pipeline on unique images only
        
        Processes: 02_unique_images/ → 03_biometric_processed/
        """
        print("\n" + "=" * 70)
        print("🔐 STEP 3: Biometric Compliance Pipeline")
        print("=" * 70)
        
        input_folder = self.folders['unique']
        output_folder = self.folders['processed_unique']
        
        # Create subfolders
        blurred_folder = output_folder / 'blurred'
        clean_folder = output_folder / 'clean'
        blurred_folder.mkdir(exist_ok=True)
        clean_folder.mkdir(exist_ok=True)
        
        print(f"📥 Input: {input_folder}")
        print(f"📤 Output: {output_folder}")
        
        # Get images to process
        images = list(input_folder.glob('*'))
        
        # Apply image limit if in testing mode
        if self.config.limit_images and len(images) > self.config.limit_images:
            print(f"\n⚠️  Testing mode: Processing only first {self.config.limit_images} images")
            images = images[:self.config.limit_images]
        
        print(f"\n🖼️  Processing {len(images)} unique images...")
        
        # Run pipeline on the entire directory (batch processing)
        pipeline_script = self.config.biometric_run_script
        
        if not pipeline_script.exists():
            print(f"❌ Pipeline script not found: {pipeline_script}")
            return {}
        
        # Create temporary output directory for pipeline
        temp_pipeline_output = self.workspace / 'temp_pipeline_output'
        temp_pipeline_output.mkdir(exist_ok=True)
        
        temp_qa_dir = self.workspace / 'temp_qa'
        temp_qa_dir.mkdir(exist_ok=True)
        
        print("\n🚀 Running biometric compliance pipeline...")
        print("   This will detect and blur human faces...")
        print(f"   Input folder: {input_folder}")
        print(f"   Processing {len(images)} images...")
        print()
        
        try:
            import subprocess
            import sys
            
            # Run pipeline with live output streaming
            process = subprocess.Popen(
                [
                    'python3',
                    str(pipeline_script),
                    '--input', str(input_folder),
                    '--output', str(temp_pipeline_output),
                    '--qa-dir', str(temp_qa_dir)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Stream output line by line
            print("📊 Pipeline Progress:")
            print("-" * 70)
            
            output_lines = []
            for line in process.stdout:
                # Print progress bars and important lines
                line = line.rstrip()
                if line:
                    # Show progress bars (contains % or 'it/s')
                    if '%' in line or 'it/s' in line or 'Obfuscating:' in line:
                        print(f"\r{line}", end='', flush=True)
                    # Show stage headers
                    elif 'STAGE' in line or '===' in line:
                        print(f"\n{line}")
                    # Show summary lines
                    elif any(keyword in line for keyword in ['Successfully', 'Clean images', 'No faces', 'Verification', 'QA review']):
                        print(f"\n   {line}")
                    
                    output_lines.append(line)
            
            # Wait for process to complete
            return_code = process.wait(timeout=3600)
            
            print("\n" + "-" * 70)
            print(f"\n📊 Pipeline execution complete!")
            print(f"   Return code: {return_code}")
            
            if return_code != 0:
                print(f"\n⚠️  Pipeline had issues:")
                print(f"\n--- Last 30 lines of output ---")
                print('\n'.join(output_lines[-30:]))
            else:
                print("   ✅ All stages completed successfully!")
            
        except subprocess.TimeoutExpired:
            print("\n❌ Pipeline timed out after 1 hour")
            if process:
                process.kill()
            return {'blurred': 0, 'clean': 0, 'qa_required': 0, 'skipped': 0, 'failed': len(images)}
        except Exception as e:
            print(f"\n❌ Pipeline error: {e}")
            import traceback
            traceback.print_exc()
            return {'blurred': 0, 'clean': 0, 'qa_required': 0, 'skipped': 0, 'failed': len(images)}
        
        # The pipeline uses the paths we provided:
        # - temp_pipeline_output (--output parameter) - images with blurred faces that passed verification
        # - temp_qa (--qa-dir parameter) - images with blurred faces that need QA review
        # - biometric_clean_dir (from config) - images without any faces detected
        
        pipeline_obfuscated_folder = temp_pipeline_output  # Use the temp folder we passed
        pipeline_clean_folder = self.config.biometric_clean_dir  # Clean images go to permanent location
        pipeline_qa_folder = temp_qa_dir  # Use the temp QA folder we passed
        
        processed_stats = {'blurred': 0, 'clean': 0, 'qa_required': 0, 'skipped': 0, 'failed': 0}
        
        print("\n📂 Organizing processed images...")
        print(f"   Reading from pipeline output folders...")
        
        # Copy blurred/obfuscated images
        if pipeline_obfuscated_folder.exists():
            obfuscated_images = list(pipeline_obfuscated_folder.glob('*'))
            print(f"   Found {len(obfuscated_images)} obfuscated images")
            for img_path in obfuscated_images:
                if img_path.is_file() and not img_path.name.startswith('.'):
                    try:
                        shutil.copy2(img_path, blurred_folder / img_path.name)
                        processed_stats['blurred'] += 1
                    except Exception as e:
                        print(f"   ⚠️  Error copying blurred image {img_path.name}: {e}")
        
        # Copy clean images (no faces)
        if pipeline_clean_folder.exists():
            clean_images = list(pipeline_clean_folder.glob('*'))
            print(f"   Found {len(clean_images)} clean images")
            for img_path in clean_images:
                if img_path.is_file() and not img_path.name.startswith('.'):
                    try:
                        shutil.copy2(img_path, clean_folder / img_path.name)
                        processed_stats['clean'] += 1
                    except Exception as e:
                        print(f"   ⚠️  Error copying clean image {img_path.name}: {e}")
        
        # Copy QA review images (verification failed) - treat as blurred
        if pipeline_qa_folder.exists():
            qa_images = list(pipeline_qa_folder.glob('*'))
            print(f"   Found {len(qa_images)} QA review images (adding to blurred folder)")
            for img_path in qa_images:
                if img_path.is_file() and not img_path.name.startswith('.'):
                    try:
                        shutil.copy2(img_path, blurred_folder / img_path.name)
                        processed_stats['qa_required'] += 1
                    except Exception as e:
                        print(f"   ⚠️  Error copying QA image {img_path.name}: {e}")
        
        # Read pipeline results JSON to get accurate stats
        pipeline_results_file = self.config.biometric_results_dir / 'obfuscation_results.json'
        if pipeline_results_file.exists():
            try:
                with open(pipeline_results_file) as f:
                    pipeline_results = json.load(f)
                    pipeline_stats = pipeline_results.get('statistics', {})
                    processed_stats['failed'] = pipeline_stats.get('failed', 0)
                    processed_stats['skipped'] = pipeline_stats.get('skipped', 0)
                    print(f"   ✓ Loaded pipeline statistics from results file")
            except Exception as e:
                print(f"   ⚠️  Could not read pipeline results: {e}")
        
        # Calculate actual skipped/failed from input vs output
        total_output = processed_stats['blurred'] + processed_stats['clean'] + processed_stats['qa_required']
        input_count = len(images)
        
        # If we didn't get stats from JSON, calculate from difference
        if processed_stats['failed'] == 0 and processed_stats['skipped'] == 0:
            unaccounted = input_count - total_output
            if unaccounted > 0:
                processed_stats['failed'] = unaccounted
                print(f"   ⚠️  {unaccounted} images unaccounted for (marked as failed)")
        
        print(f"\n🧹 Cleaning up pipeline output folders...")
        # Clean up pipeline folders after copying
        for folder in [pipeline_obfuscated_folder, pipeline_clean_folder, pipeline_qa_folder]:
            if folder.exists():
                for img_path in folder.glob('*'):
                    if img_path.is_file():
                        try:
                            img_path.unlink()
                        except:
                            pass
        
        # Clean up temp folders
        shutil.rmtree(temp_pipeline_output, ignore_errors=True)
        shutil.rmtree(temp_qa_dir, ignore_errors=True)
        
        # Copy failed images log if it exists
        failed_log = self.config.biometric_results_dir / 'failed_images.log'
        if failed_log.exists():
            shutil.copy2(failed_log, self.workspace / 'failed_images.log')
            print(f"\n📋 Failed images log copied to: {self.workspace / 'failed_images.log'}")
        
        print("\n📊 Pipeline Results:")
        print(f"   📥 Input images: {input_count}")
        print(f"   🔐 Blurred (faces detected): {processed_stats['blurred']}")
        print(f"     ↳ Obfuscated (passed verification): {processed_stats['blurred'] - processed_stats['qa_required']}")
        print(f"     ↳ QA Review (needs manual check): {processed_stats['qa_required']}")
        print(f"   ✅ Clean (no faces): {processed_stats['clean']}")
        print(f"   ❌ Failed to process: {processed_stats['failed']}")
        print(f"   ⏭️  Skipped: {processed_stats['skipped']}")
        
        # QA images are already included in blurred count, so don't double-count
        total_accounted = processed_stats['blurred'] + processed_stats['clean'] + processed_stats['failed'] + processed_stats['skipped']
        print(f"   📦 Total processed: {total_accounted}")
        
        # Validate counts
        if total_accounted != input_count:
            print(f"\n⚠️  WARNING: Count mismatch detected!")
            print(f"   Expected: {input_count} images")
            print(f"   Accounted: {total_accounted} images")
            print(f"   Difference: {input_count - total_accounted} images")
        else:
            print(f"   ✅ All {input_count} images accounted for!")
        
        # Save stats
        with open(self.workspace / 'pipeline_stats.json', 'w') as f:
            json.dump(processed_stats, f, indent=2)
        
        return processed_stats
    
    def step4_consolidate_output(self) -> Dict:
        """
        Step 4: Consolidate final output
        
        Creates final_output/ with:
        - All processed images (blurred + clean)
        - manifest.json with metadata
        """
        print("\n" + "=" * 70)
        print("📦 STEP 4: Consolidate Final Output")
        print("=" * 70)
        
        final_folder = self.folders['final_output']
        processed_folder = self.folders['processed_unique']
        
        # Copy all processed images to final output
        for subfolder in ['blurred', 'clean']:
            src_folder = processed_folder / subfolder
            if src_folder.exists():
                for img in src_folder.glob('*'):
                    shutil.copy2(img, final_folder / img.name)
        
        final_count = len(list(final_folder.glob('*')))
        
        # Create manifest
        manifest = {
            'processing_date': datetime.now().isoformat(),
            'total_final_images': final_count,
            'workspace': str(self.workspace),
            'folders': {
                'downloaded': len(list(self.folders['downloaded'].glob('*'))),
                'unique': len(list(self.folders['unique'].glob('*'))),
                'processed': final_count,
                'clusters': len(list(self.folders['duplicate_clusters'].glob('*')))
            }
        }
        
        with open(final_folder / 'manifest.json', 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"\n✅ Final output ready: {final_folder}")
        print(f"   📊 {final_count} images ready for annotation")
        
        return manifest
    
    def run_complete_pipeline(
        self,
        download: bool = True,
        deduplicate: bool = True,
        pipeline: bool = True,
        use_llm: bool = None,
        dedup_threshold: float = None
    ):
        """
        Run the complete pipeline.
        
        Args:
            download: Run download step
            deduplicate: Run deduplication step
            pipeline: Run biometric pipeline step
            use_llm: Use LLM validation (uses config if None)
            dedup_threshold: Deduplication threshold (uses config if None)
        """
        # Use config values if not provided
        use_llm = use_llm if use_llm is not None else self.config.use_llm_validation
        dedup_threshold = dedup_threshold if dedup_threshold is not None else self.config.dedup_threshold
        
        print("\n" + "=" * 70)
        print("🚀 MASTER PIPELINE START")
        print("=" * 70)
        print(f"   Download: {download}")
        print(f"   Deduplicate: {deduplicate} (LLM: {use_llm})")
        print(f"   Biometric: {pipeline}")
        print(f"   Threshold: {dedup_threshold}")
        
        if self.config.dry_run:
            print(f"\n⚠️  DRY RUN MODE - No actual processing will occur")
            return
        
        start_time = datetime.now()
        
        # Step 1: Download
        if download:
            downloaded_count = self.step1_download_from_drive()
            if downloaded_count == 0:
                print("❌ No images to process")
                return
        
        # Step 2: Deduplicate
        if deduplicate:
            dedup_stats = self.step2_deduplicate(
                use_llm=use_llm,
                threshold=dedup_threshold
            )
        
        # Step 3: Biometric Pipeline
        if pipeline:
            pipeline_stats = self.step3_biometric_pipeline()
        
        # Step 4: Consolidate
        manifest = self.step4_consolidate_output()
        
        # Final summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 70)
        print("✅ PIPELINE COMPLETE")
        print("=" * 70)
        print(f"⏱️  Total time: {duration / 60:.1f} minutes")
        print(f"\n📁 Final output: {self.folders['final_output']}")
        print(f"   Ready for annotation: {manifest['total_final_images']} images")
        
        print(f"\n📂 Workspace structure:")
        print(f"   • Downloaded: {self.folders['downloaded']}")
        print(f"   • Unique: {self.folders['unique']}")
        print(f"   • Duplicate clusters: {self.folders['duplicate_clusters']}")
        print(f"   • Processed: {self.folders['processed_unique']}")
        print(f"   • Final output: {self.folders['final_output']}")


def main():
    """Main entry point for the pipeline."""
    parser = argparse.ArgumentParser(description='Master image processing pipeline')
    parser.add_argument('--workspace', help='Workspace directory (overrides env)')
    parser.add_argument('--download', action='store_true', help='Download from Google Drive')
    parser.add_argument('--deduplicate', action='store_true', help='Run deduplication')
    parser.add_argument('--pipeline', action='store_true', help='Run biometric pipeline')
    parser.add_argument('--all', action='store_true', help='Run complete pipeline')
    parser.add_argument('--use-llm', action='store_true', help='Use LLM for duplicate validation')
    parser.add_argument('--threshold', type=float, help='Deduplication threshold (overrides env)')
    parser.add_argument('--max-llm', type=int, help='Max LLM validations (cost control)')
    parser.add_argument('--config', action='store_true', help='Show configuration and exit')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no processing)')
    
    args = parser.parse_args()
    
    # Get configuration
    config = get_config()
    
    # Override config with command-line args
    if args.dry_run:
        config.dry_run = True
    
    # Show config if requested
    if args.config:
        config.print_config()
        is_valid, errors = config.validate()
        if not is_valid:
            print("\n❌ Configuration errors:")
            for error in errors:
                print(f"   • {error}")
            return 1
        return 0
    
    # Validate config
    is_valid, errors = config.validate()
    if not is_valid:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"   • {error}")
        print("\nRun with --config to see full configuration")
        return 1
    
    # If --all, enable everything
    if args.all:
        args.download = True
        args.deduplicate = True
        args.pipeline = True
    
    # Apply defaults from config if no flags were specified
    if not any([args.download, args.deduplicate, args.pipeline, args.all]):
        # No flags specified, use config defaults
        if config.run_all_by_default:
            args.download = True
            args.deduplicate = True
            args.pipeline = True
        else:
            args.download = config.run_download_by_default
            args.deduplicate = config.run_deduplicate_by_default
            args.pipeline = config.run_biometric_by_default
    
    # Create pipeline with config
    pipeline = MasterPipeline(workspace_dir=args.workspace, config=config)
    
    # Run pipeline
    pipeline.run_complete_pipeline(
        download=args.download,
        deduplicate=args.deduplicate,
        pipeline=args.pipeline,
        use_llm=args.use_llm,
        dedup_threshold=args.threshold
    )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
