#!/usr/bin/env python3
"""
Complete Image Processing Pipeline
===================================

Workflow (runs per folder_id in isolation):
1. Download all images from a single Google Drive folder
2. Run deduplicator (within that folder only — no cross-folder comparison)
3. Run biometric pipeline on unique images only → output to deliverable/
   (DB tracks duplicate / blurred state; no intermediate folders)

Each folder_id gets its own workspace:
  pipeline_workspace/folders/{folder_id}/
    ├── 01_downloaded_from_drive/
    ├── deliverable/
    └── drive_metadata.json

Usage:
    python master_pipeline.py --download --deduplicate --pipeline --folder-ids ID1,ID2
"""

import os
import sys
import shutil
import json
from pathlib import Path
from typing import List, Dict, Optional
import argparse
from datetime import datetime
from tqdm import tqdm as _tqdm
import functools
# Force tqdm to write to stdout so subprocess can capture progress
tqdm = functools.partial(_tqdm, file=sys.stdout, mininterval=1)

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

# Register HEIC/HEIF support for PIL
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False


class MasterPipeline:
    """
    Complete pipeline orchestrator.
    Each instance operates on a single workspace directory.
    For per-folder isolation, create a new instance per folder.
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
        
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        # Simplified folder structure — only raw download and deliverable
        self.folders = {
            'downloaded': self.workspace / '01_downloaded_from_drive',
            'final_output': self.workspace / 'deliverable',
        }
        
        # Create all folders
        for folder in self.folders.values():
            folder.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 Workspace: {self.workspace}")
        print(f"   Structure created:")
        for name, path in self.folders.items():
            print(f"     • {name}: {path.name}")
    
    def _get_drive_service(self):
        """Get authenticated Google Drive service."""
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not available")
        
        if self.config.google_service_account_file:
            creds_file = Path(self.config.google_service_account_file)
            if creds_file.exists():
                with open(creds_file, 'r') as f:
                    creds_dict = json.load(f)
            else:
                raise FileNotFoundError(f"Service account file not found: {creds_file}")
        elif APP_AVAILABLE and settings:
            creds_dict = settings.google_service_account_credentials
        else:
            raise RuntimeError("Google Drive credentials not configured")
        
        if not creds_dict.get('client_email'):
            raise ValueError("Invalid Google Drive credentials")
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
        
    def step1_download_from_drive(self, folder_id: str) -> int:
        """
        Step 1: Download all images from a single Google Drive folder.
        
        Files are saved using their Google Drive file ID as the filename
        (e.g. ``1a2B3c4D5e.jpg``) to avoid collisions.  A mapping from
        drive_file_id → original_filename is persisted in
        ``drive_metadata.json`` and later imported into the database.
        
        Args:
            folder_id: Google Drive folder ID to download from.
        
        Returns: Number of images in the download folder after completion
        """
        print("\n" + "=" * 70)
        print("📥 STEP 1: Download Images from Google Drive")
        print(f"   Folder ID: {folder_id}")
        print("=" * 70)
        
        service = self._get_drive_service()
        
        # List all images recursively in this single folder
        print(f"🔍 Scanning folder: {folder_id}")
        all_images = self._list_all_drive_images(service, folder_id)
        print(f"✅ Found {len(all_images)} images")
        
        if len(all_images) == 0:
            print("⚠️  No images found")
            return 0
        
        # Save Drive metadata for this folder (includes file_id→name map)
        self._save_drive_metadata(all_images, folder_id)
        
        # Download images — saved as {drive_file_id}.{ext}
        download_folder = self.folders['downloaded']
        print(f"\n📥 Downloading to: {download_folder}")
        
        heic_exts = {'.heic', '.heif', '.avif'}
        heic_originals_dir = download_folder / '_heic_originals'
        
        downloaded = 0
        skipped = 0
        for img in tqdm(all_images, desc="Downloading"):
            try:
                drive_file_id = img['id']
                original_name = img['name']
                ext = os.path.splitext(original_name)[1].lower()  # e.g. .jpg, .heic
                disk_filename = f"{drive_file_id}{ext}"
                output_path = download_folder / disk_filename
                
                # Skip if already downloaded (exact file exists)
                if output_path.exists() and output_path.stat().st_size > 0:
                    continue
                
                # For HEIC/HEIF/AVIF: also skip if already converted to JPG
                if ext in heic_exts:
                    jpg_path = download_folder / f"{drive_file_id}.jpg"
                    heic_orig = heic_originals_dir / disk_filename
                    if jpg_path.exists() and jpg_path.stat().st_size > 0:
                        skipped += 1
                        continue
                    if heic_orig.exists() and heic_orig.stat().st_size > 0:
                        skipped += 1
                        continue
                
                # Clean up any 0-byte leftover from a previous failed download
                if output_path.exists() and output_path.stat().st_size == 0:
                    output_path.unlink()
                
                request = service.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
                
                # Download to BytesIO first, then write to disk only on success
                from io import BytesIO
                file_buffer = BytesIO()
                downloader = MediaIoBaseDownload(file_buffer, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                
                file_buffer.seek(0)
                data = file_buffer.read()
                
                if len(data) == 0:
                    print(f"⚠️  Empty download for {original_name} (id={drive_file_id})")
                    continue
                
                with open(output_path, 'wb') as f:
                    f.write(data)
                
                downloaded += 1
                
            except Exception as e:
                # Clean up 0-byte file if download failed after file creation
                if output_path.exists() and output_path.stat().st_size == 0:
                    try:
                        output_path.unlink()
                    except Exception:
                        pass
                print(f"❌ Failed to download {img['name']} (id={img['id']}): {e}")
        
        if skipped > 0:
            print(f"⏭️  Skipped {skipped} already-converted HEIC/HEIF/AVIF files")
        
        print(f"\n✅ Downloaded {downloaded} new images")
        print(f"📊 Total in folder: {len(list(download_folder.glob('*')))} images")
        
        # Auto-convert HEIC/HEIF/AVIF to JPG right after download
        converted = self._convert_unsupported_formats(download_folder)
        if converted > 0:
            print(f"🔄 Converted {converted} HEIC/HEIF/AVIF images to JPG")
            # Update drive_metadata.json so disk_filename mappings point to .jpg
            self._update_metadata_for_conversions(download_folder)
        
        return len(list(download_folder.glob('*')))
    
    def _save_drive_metadata(self, images: List[Dict], folder_id: str):
        """Save metadata about what was found in this Google Drive folder.
        
        Key mappings stored:
        - drive_id_to_original_name:  {drive_file_id: original_filename}
        - drive_id_to_disk_filename:  {drive_file_id: disk_filename}  (file_id.ext)
        - disk_filename_to_drive_id:  {disk_filename: drive_file_id}  (reverse)
        - disk_filename_to_original:  {disk_filename: original_filename}
        
        Legacy mappings (kept for backward compat):
        - filename_to_drive_id:       {original_name: drive_file_id}  (first-wins)
        - filename_folder_map:        {original_name: folder_id}
        """
        from collections import Counter
        all_names = [img['name'] for img in images]
        name_counts = Counter(all_names)
        unique_names = set(all_names)
        dup_names = {n: c for n, c in name_counts.items() if c > 1}

        # Core mappings (drive_file_id based — no collision possible)
        drive_id_to_original_name = {}
        drive_id_to_disk_filename = {}
        disk_filename_to_drive_id = {}
        disk_filename_to_original = {}

        # Legacy mappings (original-name based — first-wins for duplicate names)
        filename_folder_map = {}
        filename_to_drive_id = {}

        for img in images:
            name = img['name']
            drive_id = img['id']
            ext = os.path.splitext(name)[1].lower()
            disk_name = f"{drive_id}{ext}"

            drive_id_to_original_name[drive_id] = name
            drive_id_to_disk_filename[drive_id] = disk_name
            disk_filename_to_drive_id[disk_name] = drive_id
            disk_filename_to_original[disk_name] = name

            if name not in filename_folder_map:
                filename_folder_map[name] = folder_id
            if name not in filename_to_drive_id:
                filename_to_drive_id[name] = drive_id

        metadata = {
            "folder_id": folder_id,
            "total_in_drive": len(images),
            "unique_filenames": len(unique_names),
            "duplicate_filename_count": sum(c - 1 for c in name_counts.values() if c > 1),
            "duplicate_filenames": {n: c for n, c in sorted(dup_names.items())},
            "scanned_at": datetime.now().isoformat(),
            # Primary mappings (drive-id keyed — collision-free)
            "drive_id_to_original_name": drive_id_to_original_name,
            "drive_id_to_disk_filename": drive_id_to_disk_filename,
            "disk_filename_to_drive_id": disk_filename_to_drive_id,
            "disk_filename_to_original": disk_filename_to_original,
            # Legacy mappings (original-name keyed — kept for backward compat)
            "filename_folder_map": filename_folder_map,
            "filename_to_drive_id": filename_to_drive_id,
        }

        metadata_path = self.workspace / "drive_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"📊 Drive: {metadata['total_in_drive']} total, "
              f"{metadata['unique_filenames']} unique filenames, "
              f"{metadata['duplicate_filename_count']} duplicate filenames")

    def _update_metadata_for_conversions(self, download_folder: Path):
        """Update drive_metadata.json after HEIC/HEIF/AVIF → JPG conversion.
        
        Replaces disk_filename entries so that they reference the .jpg file
        (which is the actual file on disk) instead of the original .heic/.heif/.avif.
        """
        metadata_path = self.workspace / "drive_metadata.json"
        manifest_path = download_folder / '_heic_conversions.json'
        
        if not metadata_path.exists() or not manifest_path.exists():
            return
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            with open(manifest_path, 'r') as f:
                conversions = json.load(f)
        except Exception:
            return
        
        # Build a mapping: original_heic_name → jpg_name  (e.g. {id}.heic → {id}.jpg)
        heic_to_jpg = {}
        for jpg_name, info in conversions.items():
            orig = info.get('original_filename', '')
            if orig:
                heic_to_jpg[orig] = jpg_name
        
        if not heic_to_jpg:
            return
        
        # Update disk_filename_to_drive_id and disk_filename_to_original
        old_d2d = metadata.get('disk_filename_to_drive_id', {})
        old_d2o = metadata.get('disk_filename_to_original', {})
        new_d2d = {}
        new_d2o = {}
        
        for disk_name, drive_id in old_d2d.items():
            if disk_name in heic_to_jpg:
                # Replace .heic key with .jpg key
                new_d2d[heic_to_jpg[disk_name]] = drive_id
                new_d2o[heic_to_jpg[disk_name]] = old_d2o.get(disk_name, '')
            else:
                new_d2d[disk_name] = drive_id
                new_d2o[disk_name] = old_d2o.get(disk_name, '')
        
        # Update drive_id_to_disk_filename
        old_id2disk = metadata.get('drive_id_to_disk_filename', {})
        new_id2disk = {}
        for drive_id, disk_name in old_id2disk.items():
            if disk_name in heic_to_jpg:
                new_id2disk[drive_id] = heic_to_jpg[disk_name]
            else:
                new_id2disk[drive_id] = disk_name
        
        metadata['disk_filename_to_drive_id'] = new_d2d
        metadata['disk_filename_to_original'] = new_d2o
        metadata['drive_id_to_disk_filename'] = new_id2disk
        metadata['heic_conversions'] = heic_to_jpg  # Track what was converted
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"📝 Updated drive_metadata.json: {len(heic_to_jpg)} HEIC→JPG mappings")

    def _convert_unsupported_formats(self, folder: Path) -> int:
        """
        Convert HEIC/HEIF/AVIF images to JPG in-place.
        
        - Converts the file to .jpg
        - Moves the original to a '_heic_originals' subfolder for traceability
        - Tracks the conversion in a JSON manifest (saved after each file)
        
        Returns: number of files converted
        """
        unsupported_exts = {'.heic', '.heif', '.avif'}
        originals_dir = folder / '_heic_originals'
        manifest_path = folder / '_heic_conversions.json'
        
        # Load existing manifest
        manifest = {}
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}
        
        # Also check _heic_originals for files already converted but not in manifest
        already_converted = set()
        if originals_dir.exists():
            for f in originals_dir.iterdir():
                if f.is_file():
                    already_converted.add(f.name)
        
        # Find all unsupported format files
        to_convert = []
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in unsupported_exts:
                jpg_name = f.stem + '.jpg'
                jpg_path = folder / jpg_name
                # Skip if already converted (manifest, existing jpg, or original in _heic_originals)
                if jpg_name in manifest or jpg_path.exists() or f.name in already_converted:
                    continue
                to_convert.append(f)
        
        if not to_convert:
            return 0
        
        print(f"\n🔄 Converting {len(to_convert)} HEIC/HEIF/AVIF files to JPG...")
        originals_dir.mkdir(exist_ok=True)
        
        converted = 0
        failed = 0
        for img_path in tqdm(to_convert, desc="Converting"):
            try:
                # Guard: verify file still exists (may have been moved by prior iteration)
                if not img_path.exists():
                    continue
                
                jpg_name = img_path.stem + '.jpg'
                jpg_path = folder / jpg_name
                
                # Double-check: skip if jpg was created by a concurrent/prior conversion
                if jpg_path.exists() and jpg_path.stat().st_size > 0:
                    # Just move the original — conversion already happened
                    shutil.move(str(img_path), str(originals_dir / img_path.name))
                    manifest[jpg_name] = {
                        'original_filename': img_path.name,
                        'original_format': img_path.suffix.upper().lstrip('.'),
                        'converted_at': datetime.now().isoformat(),
                    }
                    converted += 1
                    continue
                
                # Try loading with PIL + pillow-heif (best HEIC support)
                img = None
                if HEIF_AVAILABLE:
                    try:
                        from PIL import Image as PILImage
                        pil_img = PILImage.open(str(img_path))
                        if pil_img.mode != 'RGB':
                            pil_img = pil_img.convert('RGB')
                        pil_img.save(str(jpg_path), 'JPEG', quality=95)
                        img = True
                    except Exception:
                        pass
                
                # Fallback to OpenCV
                if img is None and CV2_AVAILABLE:
                    cv_img = cv2.imread(str(img_path))
                    if cv_img is not None:
                        cv2.imwrite(str(jpg_path), cv_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        img = True
                
                if img and jpg_path.exists() and jpg_path.stat().st_size > 0:
                    # Move original to _heic_originals for traceability
                    shutil.move(str(img_path), str(originals_dir / img_path.name))
                    
                    # Track in manifest
                    manifest[jpg_name] = {
                        'original_filename': img_path.name,
                        'original_format': img_path.suffix.upper().lstrip('.'),
                        'converted_at': datetime.now().isoformat(),
                    }
                    converted += 1
                else:
                    failed += 1
                    print(f"  ✗ Failed to convert {img_path.name}")
                    
            except Exception as e:
                failed += 1
                print(f"  ✗ Error converting {img_path.name}: {e}")
            
            # Save manifest after each batch of 10 conversions (incremental save)
            if converted > 0 and converted % 10 == 0:
                with open(manifest_path, 'w') as mf:
                    json.dump(manifest, mf, indent=2)
        
        # Final save of manifest
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        if failed > 0:
            print(f"⚠️  {failed} files could not be converted")
        
        return converted
    
    def _list_all_drive_images(self, service, folder_id: str) -> List[Dict]:
        """Recursively list all images from Google Drive, tagging each with its root folder_id."""
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
                    pageSize=100,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                ).execute()
                
                items = results.get('files', [])
                
                for item in items:
                    if item['mimeType'] == 'application/vnd.google-apps.folder':
                        folders_to_process.append(item['id'])
                    else:
                        ext = os.path.splitext(item['name'])[1].lower()
                        if ext in extensions:
                            item['source_folder_id'] = folder_id  # tag with root folder ID
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
        Step 2: Run deduplication (within this folder's workspace only).
        
        DB-driven: marks duplicates via deduplication_stats.json,
        which is read by import_pipeline_images.py to set is_duplicate / parent_image.
        No intermediate folders are created.
        """
        print("\n" + "=" * 70)
        print("🔍 STEP 2: Deduplication")
        print("=" * 70)
        
        # Use config values if not provided
        use_llm = use_llm if use_llm is not None else self.config.use_llm_validation
        threshold = threshold if threshold is not None else self.config.dedup_threshold
        max_llm_validations = max_llm_validations if max_llm_validations is not None else self.config.max_llm_validations
        
        input_folder = self.folders['downloaded']
        
        # Check if using LLM
        if use_llm:
            print("🤖 Using LLM-enhanced validation")
            
            if not self.config.openai_api_key:
                print("❌ OpenAI API key not configured")
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
            
            with open(self.workspace / "deduplication_results" / "validated_duplicates.json") as f:
                duplicate_pairs = json.load(f)
            
            duplicate_map = {}
            for pair in duplicate_pairs:
                original = Path(pair['original']).name
                duplicate = Path(pair['duplicate']).name
                duplicate_map[duplicate] = original
        
        else:
            print("⚡ Using advanced deduplicator only (no LLM)")
            
            sys.path.insert(0, str(SCRIPT_DIR / 'FaceDetectionBlur'))
            from image_deduplicator_advanced import AdvancedDeduplicator
            
            similarity_threshold = threshold
            deduplicator = AdvancedDeduplicator(similarity_threshold=similarity_threshold)
            deduplicator.scan_images(input_folder)
            
            if not deduplicator.images:
                print("❌ No images found!")
                return {}
            
            deduplicator.find_duplicates()
            
            temp_dedup_output = self.workspace / 'temp_dedup'
            temp_dedup_output.mkdir(parents=True, exist_ok=True)
            (temp_dedup_output / 'originals').mkdir(parents=True, exist_ok=True)
            (temp_dedup_output / 'duplicates').mkdir(parents=True, exist_ok=True)
            deduplicator.segregate_images(temp_dedup_output)
            
            duplicate_map = {}
            for img in deduplicator.images:
                if img.is_duplicate and img.duplicate_of:
                    duplicate_map[img.filename] = img.duplicate_of
        
        print(f"\n✅ Found {len(duplicate_map)} duplicate images")
        
        # Load HEIC conversion manifest to map JPG duplicates back to their HEIC sources
        heic_manifest_path = input_folder / "_heic_conversions.json"
        jpg_to_heic = {}  # e.g. {"IMG_2771.jpg": "IMG_2771.HEIC"}
        if heic_manifest_path.exists():
            try:
                with open(heic_manifest_path, 'r') as f:
                    heic_manifest = json.load(f)
                for jpg_name, info in heic_manifest.items():
                    jpg_to_heic[jpg_name] = info.get('original_filename', '')
            except Exception:
                pass
        
        # Build extended duplicate set: include HEIC sources of duplicate JPGs
        extended_duplicates = set(duplicate_map.keys())
        for dup_jpg in list(duplicate_map.keys()):
            heic_source = jpg_to_heic.get(dup_jpg)
            if heic_source:
                extended_duplicates.add(heic_source)
                print(f"  ℹ️  Also excluding HEIC source: {heic_source} (conversion of duplicate {dup_jpg})")
        
        # Count originals vs duplicates (for stats only — no file copy)
        all_images = list(input_folder.glob('*'))
        originals = set()
        duplicates = set()
        
        for img_path in all_images:
            img_name = img_path.name
            if img_name.startswith('_') or img_name.startswith('.'):
                continue  # skip manifests/hidden files
            
            if img_name in extended_duplicates:
                duplicates.add(img_name)
            else:
                originals.add(img_name)
        
        # Clean up temp folder
        if not use_llm:
            temp_dedup_output = self.workspace / 'temp_dedup'
            if temp_dedup_output.exists():
                shutil.rmtree(temp_dedup_output)
        
        stats = {
            'total_images': len([f for f in all_images if f.is_file() and not f.name.startswith(('_', '.'))]),
            'unique_images': len(originals),
            'duplicate_images': len(duplicates),
            'duplicate_pairs': len(duplicate_map),
            'duplicate_map': duplicate_map,  # stored so import step can read it
            'duplicate_filenames': list(extended_duplicates),
            'compression_ratio': f"{(1 - len(originals) / max(len(originals) + len(duplicates), 1)) * 100:.1f}%"
        }
        
        print("\n📊 Deduplication Results:")
        print(f"   Total images: {stats['total_images']}")
        print(f"   Unique images: {stats['unique_images']}")
        print(f"   Duplicate images: {stats['duplicate_images']}")
        print(f"   Compression: {stats['compression_ratio']}")
        
        with open(self.workspace / 'deduplication_stats.json', 'w') as f:
            json.dump(stats, f, indent=2)
        
        return stats
    
    def step3_biometric_pipeline(self) -> Dict:
        """
        Step 3: Run biometric compliance pipeline on unique images only.
        
        Reads from 01_downloaded_from_drive/ (skipping duplicates via dedup stats),
        outputs directly to deliverable/.
        """
        print("\n" + "=" * 70)
        print("🔐 STEP 3: Biometric Compliance Pipeline")
        print("=" * 70)
        
        input_folder = self.folders['downloaded']
        output_folder = self.folders['final_output']  # deliverable/
        
        print(f"📥 Input: {input_folder}")
        print(f"📤 Output: {output_folder}")
        
        # Load deduplication stats to skip duplicates
        dedup_stats_path = self.workspace / 'deduplication_stats.json'
        duplicate_filenames = set()
        if dedup_stats_path.exists():
            try:
                with open(dedup_stats_path, 'r') as f:
                    dedup_stats = json.load(f)
                duplicate_filenames = set(dedup_stats.get('duplicate_filenames', []))
                print(f"   Skipping {len(duplicate_filenames)} duplicates from dedup step")
            except Exception as e:
                print(f"   ⚠️  Could not load dedup stats: {e}")
        
        # Filter to unique images only (create a temp input dir with symlinks/copies)
        temp_input = self.workspace / '_temp_biometric_input'
        temp_input.mkdir(exist_ok=True)
        
        image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'}
        unique_count = 0
        for img_path in input_folder.iterdir():
            if not img_path.is_file():
                continue
            if img_path.name.startswith(('_', '.')):
                continue
            if img_path.suffix.lower() not in image_exts:
                continue
            if img_path.name in duplicate_filenames:
                continue
            # Symlink to temp input (avoids copying)
            link_path = temp_input / img_path.name
            if not link_path.exists():
                try:
                    os.symlink(img_path.resolve(), link_path)
                except OSError:
                    shutil.copy2(img_path, link_path)
            unique_count += 1
        
        print(f"\n🖼️  Processing {unique_count} unique images...")
        
        # Apply image limit if in testing mode
        if self.config.limit_images and unique_count > self.config.limit_images:
            print(f"\n⚠️  Testing mode: Processing only first {self.config.limit_images} images")
        
        # Run pipeline on the filtered directory
        pipeline_script = self.config.biometric_run_script
        
        if not pipeline_script.exists():
            print(f"❌ Pipeline script not found: {pipeline_script}")
            shutil.rmtree(temp_input, ignore_errors=True)
            return {}
        
        # Create temporary output directory for pipeline
        temp_pipeline_output = self.workspace / 'temp_pipeline_output'
        temp_pipeline_output.mkdir(exist_ok=True)
        
        temp_qa_dir = self.workspace / 'temp_qa'
        temp_qa_dir.mkdir(exist_ok=True)
        
        print("\n🚀 Running biometric compliance pipeline...")
        print("   This will detect and blur human faces...")
        print(f"   Input folder: {temp_input}")
        print(f"   Processing {unique_count} images...")
        print()
        
        try:
            import subprocess
            
            process = subprocess.Popen(
                [
                    'python3',
                    str(pipeline_script),
                    '--input', str(temp_input),
                    '--output', str(temp_pipeline_output),
                    '--qa-dir', str(temp_qa_dir)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            print("📊 Pipeline Progress:")
            print("-" * 70)
            
            output_lines = []
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    if '%' in line or 'it/s' in line or 'Obfuscating:' in line:
                        print(f"\r{line}", end='', flush=True)
                    elif 'STAGE' in line or '===' in line:
                        print(f"\n{line}")
                    elif any(keyword in line for keyword in ['Successfully', 'Clean images', 'No faces', 'Verification', 'QA review']):
                        print(f"\n   {line}")
                    output_lines.append(line)
            
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
            shutil.rmtree(temp_input, ignore_errors=True)
            return {'blurred': 0, 'clean': 0, 'qa_required': 0, 'skipped': 0, 'failed': unique_count}
        except Exception as e:
            print(f"\n❌ Pipeline error: {e}")
            import traceback
            traceback.print_exc()
            shutil.rmtree(temp_input, ignore_errors=True)
            return {'blurred': 0, 'clean': 0, 'qa_required': 0, 'skipped': 0, 'failed': unique_count}
        
        # The biometric pipeline writes blurred images to temp_pipeline_output,
        # clean images to biometric_clean_dir, QA to temp_qa_dir.
        pipeline_obfuscated_folder = temp_pipeline_output
        pipeline_clean_folder = self.config.biometric_clean_dir
        pipeline_qa_folder = temp_qa_dir
        
        processed_stats = {'blurred': 0, 'clean': 0, 'qa_required': 0, 'skipped': 0, 'failed': 0}
        
        print("\n📂 Moving processed images to deliverable/...")
        
        # Copy blurred/obfuscated images → deliverable/
        if pipeline_obfuscated_folder.exists():
            obfuscated_images = list(pipeline_obfuscated_folder.glob('*'))
            print(f"   Found {len(obfuscated_images)} obfuscated images")
            for img_path in obfuscated_images:
                if img_path.is_file() and not img_path.name.startswith('.'):
                    try:
                        shutil.copy2(img_path, output_folder / img_path.name)
                        processed_stats['blurred'] += 1
                    except Exception as e:
                        print(f"   ⚠️  Error copying blurred image {img_path.name}: {e}")
        
        # Copy clean images (no faces) → deliverable/
        if pipeline_clean_folder.exists():
            clean_images = list(pipeline_clean_folder.glob('*'))
            print(f"   Found {len(clean_images)} clean images")
            for img_path in clean_images:
                if img_path.is_file() and not img_path.name.startswith('.'):
                    try:
                        shutil.copy2(img_path, output_folder / img_path.name)
                        processed_stats['clean'] += 1
                    except Exception as e:
                        print(f"   ⚠️  Error copying clean image {img_path.name}: {e}")
        
        # Copy QA review images (verification failed) → deliverable/ (treat as blurred)
        if pipeline_qa_folder.exists():
            qa_images = list(pipeline_qa_folder.glob('*'))
            print(f"   Found {len(qa_images)} QA review images (adding to deliverable)")
            for img_path in qa_images:
                if img_path.is_file() and not img_path.name.startswith('.'):
                    try:
                        shutil.copy2(img_path, output_folder / img_path.name)
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
                
                # Save a copy of biometric results in this folder's workspace
                results_copy_path = self.workspace / 'obfuscation_results.json'
                shutil.copy2(pipeline_results_file, results_copy_path)
                print(f"   ✓ Saved biometric results to workspace")
            except Exception as e:
                print(f"   ⚠️  Could not read pipeline results: {e}")
        
        # Calculate actual skipped/failed from input vs output
        total_output = processed_stats['blurred'] + processed_stats['clean'] + processed_stats['qa_required']
        
        if processed_stats['failed'] == 0 and processed_stats['skipped'] == 0:
            unaccounted = unique_count - total_output
            if unaccounted > 0:
                processed_stats['failed'] = unaccounted
                print(f"   ⚠️  {unaccounted} images unaccounted for (marked as failed)")
        
        print(f"\n🧹 Cleaning up temporary folders...")
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
        shutil.rmtree(temp_input, ignore_errors=True)
        
        # Copy failed images log if it exists
        failed_log = self.config.biometric_results_dir / 'failed_images.log'
        if failed_log.exists():
            shutil.copy2(failed_log, self.workspace / 'failed_images.log')
        
        print("\n📊 Pipeline Results:")
        print(f"   📥 Input images: {unique_count}")
        print(f"   🔐 Blurred (faces detected): {processed_stats['blurred']}")
        print(f"   ✅ Clean (no faces): {processed_stats['clean']}")
        print(f"   ❌ Failed to process: {processed_stats['failed']}")
        print(f"   ⏭️  Skipped: {processed_stats['skipped']}")
        
        with open(self.workspace / 'pipeline_stats.json', 'w') as f:
            json.dump(processed_stats, f, indent=2)
        
        return processed_stats
    
    def run_complete_pipeline(
        self,
        download: bool = True,
        deduplicate: bool = True,
        pipeline: bool = True,
        use_llm: bool = None,
        dedup_threshold: float = None,
        folder_id: str = None
    ):
        """
        Run the complete pipeline for a single folder.
        
        Args:
            download: Run download step
            deduplicate: Run deduplication step
            pipeline: Run biometric pipeline step
            use_llm: Use LLM validation
            dedup_threshold: Deduplication threshold
            folder_id: Google Drive folder ID to process
        """
        use_llm = use_llm if use_llm is not None else self.config.use_llm_validation
        dedup_threshold = dedup_threshold if dedup_threshold is not None else self.config.dedup_threshold
        
        print("\n" + "=" * 70)
        print("🚀 PIPELINE START")
        if folder_id:
            print(f"   Folder: {folder_id}")
        print(f"   Download: {download}")
        print(f"   Deduplicate: {deduplicate} (LLM: {use_llm})")
        print(f"   Biometric: {pipeline}")
        print(f"   Threshold: {dedup_threshold}")
        print("=" * 70)
        
        if self.config.dry_run:
            print(f"\n⚠️  DRY RUN MODE - No actual processing will occur")
            return
        
        start_time = datetime.now()
        
        # Step 1: Download
        if download:
            if not folder_id:
                folder_id = self.config.google_drive_folder_id
            if not folder_id:
                print("❌ No folder ID provided and none configured in .env")
                return
            downloaded_count = self.step1_download_from_drive(folder_id=folder_id)
            if downloaded_count == 0:
                print("❌ No images to process")
                return
        
        # Step 2: Deduplicate (within this folder only — DB-driven, no file copy)
        if deduplicate:
            self.step2_deduplicate(use_llm=use_llm, threshold=dedup_threshold)
        
        # Step 3: Biometric Pipeline → outputs directly to deliverable/
        if pipeline:
            self.step3_biometric_pipeline()
        elif not deduplicate:
            # If skipping both dedup and biometric, copy all downloaded to deliverable
            print("\n⏭️  Skipping dedup + biometric — copying all downloaded to deliverable...")
            downloaded_dir = self.folders['downloaded']
            deliverable_dir = self.folders['final_output']
            image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif', '.bmp', '.tiff', '.tif'}
            copied = 0
            for f in downloaded_dir.iterdir():
                if f.is_file() and f.suffix.lower() in image_exts and not f.name.startswith(('_', '.')) and not (deliverable_dir / f.name).exists():
                    shutil.copy2(f, deliverable_dir / f.name)
                    copied += 1
            print(f"   Copied {copied} images to deliverable/")
        else:
            # Dedup ran but biometric skipped — copy unique images to deliverable
            print("\n⏭️  Skipping biometric — copying unique images to deliverable...")
            dedup_stats_path = self.workspace / 'deduplication_stats.json'
            duplicate_filenames = set()
            if dedup_stats_path.exists():
                try:
                    with open(dedup_stats_path, 'r') as f:
                        dedup_stats = json.load(f)
                    duplicate_filenames = set(dedup_stats.get('duplicate_filenames', []))
                except Exception:
                    pass
            
            downloaded_dir = self.folders['downloaded']
            deliverable_dir = self.folders['final_output']
            image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'}
            copied = 0
            for f in downloaded_dir.iterdir():
                if f.is_file() and f.suffix.lower() in image_exts and not f.name.startswith(('_', '.')) and f.name not in duplicate_filenames:
                    if not (deliverable_dir / f.name).exists():
                        shutil.copy2(f, deliverable_dir / f.name)
                        copied += 1
            print(f"   Copied {copied} unique images to deliverable/")
        
        # Final summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 70)
        print("✅ PIPELINE COMPLETE")
        print("=" * 70)
        print(f"⏱️  Total time: {duration / 60:.1f} minutes")
        print(f"📁 Final output: {self.folders['final_output']}")


def run_for_folders(
    folder_ids: List[str],
    download: bool = True,
    deduplicate: bool = True,
    pipeline: bool = True,
    use_llm: bool = False,
    dedup_threshold: float = 0.85,
    config=None
):
    """
    Run the complete pipeline for each folder_id in isolation.
    
    Each folder gets its own workspace:
      pipeline_workspace/folders/{folder_id}/
    
    No cross-folder deduplication or comparison.
    """
    config = config or get_config()
    root_workspace = config.workspace
    
    print("\n" + "=" * 70)
    print(f"🚀 MASTER PIPELINE — Processing {len(folder_ids)} folder(s)")
    print("=" * 70)
    for i, fid in enumerate(folder_ids, 1):
        print(f"   {i}. {fid}")
    print()
    
    all_start = datetime.now()
    results = {}
    
    for idx, folder_id in enumerate(folder_ids, 1):
        print("\n" + "▓" * 70)
        print(f"▓  FOLDER {idx}/{len(folder_ids)}: {folder_id}")
        print("▓" * 70)
        
        # Create isolated per-folder workspace
        folder_workspace = root_workspace / "folders" / folder_id
        
        # Create pipeline instance for this folder
        p = MasterPipeline(workspace_dir=str(folder_workspace), config=config)
        
        try:
            p.run_complete_pipeline(
                download=download,
                deduplicate=deduplicate,
                pipeline=pipeline,
                use_llm=use_llm,
                dedup_threshold=dedup_threshold,
                folder_id=folder_id
            )
            results[folder_id] = "completed"
        except Exception as e:
            print(f"\n❌ Folder {folder_id} failed: {e}")
            import traceback
            traceback.print_exc()
            results[folder_id] = f"failed: {str(e)}"
    
    all_end = datetime.now()
    total_duration = (all_end - all_start).total_seconds()
    
    # Save combined summary
    summary = {
        "processed_at": datetime.now().isoformat(),
        "total_folders": len(folder_ids),
        "total_duration_seconds": total_duration,
        "results": results,
    }
    summary_path = root_workspace / "run_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n" + "=" * 70)
    print(f"✅ ALL FOLDERS PROCESSED")
    print("=" * 70)
    print(f"⏱️  Total time: {total_duration / 60:.1f} minutes")
    for fid, status in results.items():
        icon = "✅" if status == "completed" else "❌"
        print(f"   {icon} {fid}: {status}")
    
    return results


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
    parser.add_argument('--folder-ids', type=str, help='Comma-separated Google Drive folder IDs')
    
    args = parser.parse_args()
    
    # Get configuration
    config = get_config()
    
    if args.dry_run:
        config.dry_run = True
    
    if args.config:
        config.print_config()
        is_valid, errors = config.validate()
        if not is_valid:
            print("\n❌ Configuration errors:")
            for error in errors:
                print(f"   • {error}")
            return 1
        return 0
    
    is_valid, errors = config.validate()
    if not is_valid:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"   • {error}")
        return 1
    
    # If --all, enable everything
    if args.all:
        args.download = True
        args.deduplicate = True
        args.pipeline = True
    
    # Apply defaults from config if no flags were specified
    if not any([args.download, args.deduplicate, args.pipeline, args.all]):
        if config.run_all_by_default:
            args.download = True
            args.deduplicate = True
            args.pipeline = True
        else:
            args.download = config.run_download_by_default
            args.deduplicate = config.run_deduplicate_by_default
            args.pipeline = config.run_biometric_by_default
    
    # Parse folder IDs
    folder_ids = None
    if args.folder_ids:
        folder_ids = [fid.strip() for fid in args.folder_ids.split(',') if fid.strip()]
    
    threshold = args.threshold if args.threshold else config.dedup_threshold
    
    if folder_ids:
        # Run per-folder in isolation
        run_for_folders(
            folder_ids=folder_ids,
            download=args.download,
            deduplicate=args.deduplicate,
            pipeline=args.pipeline,
            use_llm=args.use_llm,
            dedup_threshold=threshold,
            config=config
        )
    else:
        # Legacy: single folder from config (or no download)
        pipeline = MasterPipeline(workspace_dir=args.workspace, config=config)
        pipeline.run_complete_pipeline(
            download=args.download,
            deduplicate=args.deduplicate,
            pipeline=args.pipeline,
            use_llm=args.use_llm,
            dedup_threshold=threshold,
            folder_id=config.google_drive_folder_id
        )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
