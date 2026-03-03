"""
Migration: Add original_filename and original_format columns to images table.
Backfills HEIC → JPG conversion data by checking the pipeline workspace.
"""
from sqlalchemy import create_engine, text
import os
from pathlib import Path

database_url = os.getenv('DATABASE_URL', 'sqlite:///./photo_annotation.db')
engine = create_engine(database_url)


def migrate():
    print("🔄 Adding original_filename and original_format columns to images table...")
    with engine.begin() as conn:
        result = conn.execute(text("SELECT * FROM images LIMIT 1"))
        existing_columns = [col for col in result.keys()]

        if 'original_filename' not in existing_columns:
            print("  ✓ Adding original_filename column...")
            conn.execute(text("ALTER TABLE images ADD COLUMN original_filename VARCHAR(255)"))
        else:
            print("  ℹ original_filename column already exists")

        if 'original_format' not in existing_columns:
            print("  ✓ Adding original_format column...")
            conn.execute(text("ALTER TABLE images ADD COLUMN original_format VARCHAR(20)"))
        else:
            print("  ℹ original_format column already exists")

    print("\n🔄 Backfilling HEIC → JPG conversion data...")
    backfill_heic_conversions()

    print("\n✅ Migration completed successfully!")


def backfill_heic_conversions():
    """
    Scan the pipeline workspace for HEIC files that were converted to JPG.
    Update the DB records with the original filename and format.
    """
    backend_dir = Path(__file__).parent.parent
    workspace = backend_dir / "master_pipeline" / "pipeline_workspace"
    download_dir = workspace / "01_downloaded_from_drive"
    unique_dir = workspace / "02_unique_images"

    # Collect all HEIC files on disk
    heic_files = set()
    for d in [download_dir, unique_dir]:
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() == '.heic':
                    heic_files.add(f.name)

    if not heic_files:
        print("  ℹ No HEIC files found on disk, nothing to backfill.")
        return

    print(f"  Found {len(heic_files)} HEIC files on disk")

    updated = 0
    with engine.begin() as conn:
        # Get all image filenames from DB
        rows = conn.execute(text("SELECT id, filename FROM images")).fetchall()

        for row in rows:
            img_id, filename = row
            stem = os.path.splitext(filename)[0]
            current_ext = os.path.splitext(filename)[1].lower()

            # Check if this is a converted file (e.g., IMG_0906.jpg has a HEIC original)
            if current_ext in ('.jpg', '.jpeg'):
                heic_name = stem + ".HEIC"
                heic_name_lower = stem + ".heic"

                matching_heic = None
                if heic_name in heic_files:
                    matching_heic = heic_name
                elif heic_name_lower in heic_files:
                    matching_heic = heic_name_lower

                if matching_heic:
                    conn.execute(
                        text("UPDATE images SET original_filename = :orig, original_format = :fmt WHERE id = :id"),
                        {"orig": matching_heic, "fmt": "HEIC", "id": img_id}
                    )
                    updated += 1
                    print(f"    ✓ {filename} ← originally {matching_heic}")

    print(f"  Updated {updated} images with HEIC conversion data")


if __name__ == "__main__":
    print("=" * 70)
    print("DATABASE MIGRATION: Add Original Filename Tracking")
    print("=" * 70)
    print()
    try:
        migrate()
        print("\n🎉 All done!")
    except Exception as e:
        print(f"\n⚠️  Migration error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
