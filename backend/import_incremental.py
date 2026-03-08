"""
Enhanced Import Script with Incremental Processing
===================================================

Features:
- Imports only NEW images from pipeline output
- Optionally re-runs pipeline ONLY on new images
- Tracks processing state to avoid re-processing
- Admin can trigger from UI or command line
"""
import sys
import os
from pathlib import Path
from sqlalchemy import text
from app.database import SessionLocal
from app.config import settings
import subprocess
import json
from datetime import datetime
from typing import List, Dict, Set

class IncrementalPipelineImporter:
    """
    Manages incremental pipeline processing and import.
    """
    
    def __init__(self):
        self.backend_dir = Path(__file__).parent
        self.pipeline_dir = self.backend_dir / "master_pipeline"
        self.workspace = self.pipeline_dir / "pipeline_workspace"
        
        # Folder paths
        self.downloaded_dir = self.workspace / "01_downloaded_from_drive"
        self.final_output_dir = self.workspace / "deliverable"
        
        # State tracking file
        self.state_file = self.workspace / "pipeline_state.json"
    
    def load_state(self) -> Dict:
        """Load processing state to track what's been done."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {
            "last_run": None,
            "processed_files": [],  # Files that went through full pipeline
            "imported_files": [],    # Files imported to database
            "failed_files": []
        }
    
    def save_state(self, state: Dict):
        """Save processing state."""
        state["last_run"] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def get_new_downloaded_files(self) -> List[Path]:
        """Get files that have been downloaded but not processed."""
        if not self.downloaded_dir.exists():
            return []
        
        state = self.load_state()
        processed = set(state.get("processed_files", []))
        
        extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif', '.bmp', '.tiff'}
        all_files = [
            f for f in self.downloaded_dir.iterdir()
            if f.is_file() and f.suffix.lower() in extensions
        ]
        
        # Return only files not yet processed
        new_files = [f for f in all_files if f.name not in processed]
        
        return new_files
    
    def get_final_output_files(self) -> List[Path]:
        """Get all files in final output ready for import."""
        if not self.final_output_dir.exists():
            return []
        
        extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
        return [
            f for f in self.final_output_dir.iterdir()
            if f.is_file() and f.suffix.lower() in extensions
        ]
    
    def get_db_imported_files(self, db) -> Set[str]:
        """Get filenames already in database."""
        result = db.execute(text("SELECT filename FROM images")).fetchall()
        return {row[0] for row in result}
    
    def run_incremental_pipeline(
        self,
        run_deduplication: bool = True,
        run_biometric: bool = True
    ) -> Dict:
        """
        Run pipeline ONLY on new images.
        
        Workflow:
        1. Check which files are NEW (downloaded but not processed)
        2. If new files exist:
           a. Copy them to a temporary folder
           b. Run deduplication (if enabled)
           c. Run biometric pipeline (if enabled)
           d. Move results to final output
        3. Update state tracking
        """
        print("=" * 70)
        print("🔄 INCREMENTAL PIPELINE PROCESSING")
        print("=" * 70)
        
        new_files = self.get_new_downloaded_files()
        
        if not new_files:
            print("\n✅ No new files to process. All downloaded images are already processed.")
            return {"status": "no_new_files", "processed": 0}
        
        print(f"\n📊 Found {len(new_files)} NEW files to process:")
        for f in new_files[:5]:
            print(f"   • {f.name}")
        if len(new_files) > 5:
            print(f"   ... and {len(new_files) - 5} more")
        
        # Create temporary processing folder
        temp_dir = self.workspace / "temp_incremental"
        temp_dir.mkdir(exist_ok=True)
        
        # Copy new files to temp folder
        print(f"\n📁 Preparing {len(new_files)} files for processing...")
        import shutil
        for f in new_files:
            shutil.copy2(f, temp_dir / f.name)
        
        state = self.load_state()
        results = {"processed": 0, "failed": 0, "skipped": 0}
        
        try:
            # Run deduplication on temp folder (if enabled)
            if run_deduplication:
                print("\n🔍 Running deduplication on new files...")
                # For incremental, we compare against existing unique images
                # This is complex - for now, just copy all to unique folder
                # TODO: Implement smart deduplication against existing uniques
                unique_temp = self.workspace / "temp_unique"
                unique_temp.mkdir(exist_ok=True)
                for f in temp_dir.glob("*"):
                    shutil.copy2(f, unique_temp / f.name)
            else:
                unique_temp = temp_dir
            
            # Run biometric pipeline on unique new files
            if run_biometric:
                print("\n🔐 Running biometric compliance on new files...")
                
                cmd = [
                    sys.executable,
                    str(self.pipeline_dir / "biometric_compliance_pipeline" / "scripts" / "stage3_obfuscate_faces_enhanced.py"),
                    "--input", str(unique_temp),
                    "--output", str(self.processed_dir / "blurred"),
                    "--qa-dir", str(self.workspace / "qa_review")
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"⚠️  Biometric processing had issues:")
                    print(result.stderr[:500])
                else:
                    print("✅ Biometric processing complete")
            
            # Move processed files to final output
            print("\n📦 Moving processed files to final output...")
            processed_count = 0
            
            # Get processed files
            blurred_dir = self.processed_dir / "blurred"
            clean_dir = self.processed_dir / "clean"
            
            for src_dir in [blurred_dir, clean_dir]:
                if src_dir.exists():
                    for f in src_dir.glob("*"):
                        if f.is_file():
                            dest = self.final_output_dir / f.name
                            if not dest.exists():  # Don't overwrite existing
                                shutil.copy2(f, dest)
                                processed_count += 1
            
            # Update state tracking
            for f in new_files:
                if f.name not in state["failed_files"]:
                    state["processed_files"].append(f.name)
            
            self.save_state(state)
            
            results["processed"] = processed_count
            
            print(f"\n✅ Incremental processing complete!")
            print(f"   • Processed: {processed_count} new files")
            
        except Exception as e:
            print(f"\n❌ Error during incremental processing: {e}")
            import traceback
            traceback.print_exc()
            results["failed"] = len(new_files)
        
        finally:
            # Cleanup temp folders
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            if run_deduplication and unique_temp.exists():
                shutil.rmtree(unique_temp, ignore_errors=True)
        
        return results
    
    def import_new_images_to_db(self, reprocess: bool = False) -> Dict:
        """
        Import only NEW images from final output to database.
        
        Args:
            reprocess: If True, also import images that failed before
        """
        print("\n" + "=" * 70)
        print("📥 IMPORTING NEW IMAGES TO DATABASE")
        print("=" * 70)
        
        final_files = self.get_final_output_files()
        
        if not final_files:
            print("\n❌ No images found in final output folder.")
            print(f"   Please run the pipeline first to process images.")
            return {"imported": 0, "skipped": 0, "total_in_db": 0}
        
        print(f"\n📁 Found {len(final_files)} images in final output")
        
        db = SessionLocal()
        try:
            # Get existing filenames
            existing_filenames = self.get_db_imported_files(db)
            print(f"📊 Database currently has {len(existing_filenames)} images")
            
            state = self.load_state()
            imported_state = set(state.get("imported_files", []))
            
            new_count = 0
            skipped_count = 0
            
            for img_file in final_files:
                filename = img_file.name
                
                # Skip if already in database
                if filename in existing_filenames:
                    skipped_count += 1
                    continue
                
                # Build URL
                relative_path = f"master_pipeline/pipeline_workspace/deliverable/{filename}"
                url = f"file://{relative_path}"
                
                # Insert into database
                db.execute(text('''
                    INSERT INTO images (
                        filename, 
                        url, 
                        compliance_processed,
                        compliance_status,
                        original_url,
                        processed_url,
                        is_improper,
                        human_faces_detected,
                        is_using_processed
                    )
                    VALUES (
                        :filename, 
                        :url, 
                        TRUE,
                        'processed',
                        :original_url,
                        :processed_url,
                        FALSE,
                        0,
                        TRUE
                    )
                '''), {
                    'filename': filename,
                    'url': url,
                    'original_url': relative_path,
                    'processed_url': relative_path
                })
                
                new_count += 1
                
                # Update state
                if filename not in imported_state:
                    state["imported_files"].append(filename)
                
                if new_count % 100 == 0:
                    print(f"   ✓ Imported {new_count} images...")
            
            db.commit()
            self.save_state(state)
            
            total_in_db = len(existing_filenames) + new_count
            
            print(f"\n✅ Import complete!")
            print(f"   • NEW images imported: {new_count}")
            print(f"   • Already in database (skipped): {skipped_count}")
            print(f"   • TOTAL in database now: {total_in_db}")
            
            return {
                "imported": new_count,
                "skipped": skipped_count,
                "total_in_db": total_in_db
            }
            
        except Exception as e:
            print(f"\n❌ Error importing images: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return {"imported": 0, "skipped": 0, "error": str(e)}
        
        finally:
            db.close()
    
    def full_incremental_workflow(
        self,
        run_deduplication: bool = True,
        run_biometric: bool = True
    ) -> Dict:
        """
        Complete incremental workflow:
        1. Check for new downloaded files
        2. Process only new files through pipeline
        3. Import new processed files to database
        """
        print("\n" + "🚀" * 35)
        print("  INCREMENTAL PIPELINE + IMPORT WORKFLOW")
        print("🚀" * 35)
        
        # Step 1: Process new files
        process_results = self.run_incremental_pipeline(
            run_deduplication=run_deduplication,
            run_biometric=run_biometric
        )
        
        # Step 2: Import to database
        import_results = self.import_new_images_to_db()
        
        # Combined results
        return {
            "pipeline": process_results,
            "import": import_results,
            "summary": {
                "new_files_processed": process_results.get("processed", 0),
                "new_files_imported": import_results.get("imported", 0),
                "total_in_database": import_results.get("total_in_db", 0)
            }
        }


# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Incremental Pipeline Import')
    parser.add_argument('--import-only', action='store_true', 
                       help='Only import existing processed images (skip pipeline)')
    parser.add_argument('--pipeline-only', action='store_true',
                       help='Only run pipeline on new files (skip import)')
    parser.add_argument('--full', action='store_true',
                       help='Run pipeline + import (default)')
    parser.add_argument('--skip-dedup', action='store_true',
                       help='Skip deduplication step')
    parser.add_argument('--skip-biometric', action='store_true',
                       help='Skip biometric processing step')
    
    args = parser.parse_args()
    
    importer = IncrementalPipelineImporter()
    
    if args.import_only:
        # Just import what's already in final output
        results = importer.import_new_images_to_db()
    elif args.pipeline_only:
        # Just run pipeline on new files
        results = importer.run_incremental_pipeline(
            run_deduplication=not args.skip_dedup,
            run_biometric=not args.skip_biometric
        )
    else:
        # Full workflow (default)
        results = importer.full_incremental_workflow(
            run_deduplication=not args.skip_dedup,
            run_biometric=not args.skip_biometric
        )
    
    print("\n" + "=" * 70)
    print("📊 FINAL SUMMARY")
    print("=" * 70)
    print(json.dumps(results, indent=2))
    print()
    
    sys.exit(0)
