"""
Import images from master pipeline's final output into the database.
This script imports images from the pipeline workspace into the annotation tool database.
"""
import sys
from pathlib import Path
from sqlalchemy import text
from app.database import SessionLocal
from app.config import settings

def import_images_from_pipeline():
    """Import images from pipeline workspace to database."""
    
    # Path to final output
    pipeline_workspace = Path(__file__).parent / "master_pipeline" / "pipeline_workspace"
    final_output = pipeline_workspace / "04_final_output"
    
    if not final_output.exists():
        print(f"❌ Final output folder not found: {final_output}")
        print(f"   Please run the master pipeline first.")
        return 0
    
    # Get all image files
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif'}
    image_files = [
        f for f in final_output.iterdir() 
        if f.is_file() and f.suffix.lower() in image_extensions
    ]
    
    if not image_files:
        print(f"❌ No images found in {final_output}")
        return 0
    
    print(f"📁 Found {len(image_files)} images in final output")
    
    db = SessionLocal()
    try:
        # Get existing filenames
        existing = db.execute(text("SELECT filename FROM images")).fetchall()
        existing_filenames = {row[0] for row in existing}
        
        print(f"📊 Database has {len(existing_filenames)} existing images")
        
        new_count = 0
        skipped_count = 0
        
        for img_file in image_files:
            filename = img_file.name
            
            if filename in existing_filenames:
                skipped_count += 1
                continue
            
            # For local files, use file:// URL with relative path from backend directory
            # The proxy endpoint will resolve this to the actual file
            relative_path = f"master_pipeline/pipeline_workspace/04_final_output/{filename}"
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
            
            if new_count % 100 == 0:
                print(f"   Imported {new_count} images...")
        
        db.commit()
        
        print(f"\n✅ Import complete!")
        print(f"   • New images imported: {new_count}")
        print(f"   • Already in database: {skipped_count}")
        print(f"   • Total in database: {len(existing_filenames) + new_count}")
        
        return new_count
        
    except Exception as e:
        print(f"❌ Error importing images: {e}")
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
