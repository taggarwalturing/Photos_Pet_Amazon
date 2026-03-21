#!/usr/bin/env python3
"""
One-time script: Import images into the database directly from GCS.

This is used when images have been processed and uploaded to GCS
(annotated/{folder_id}/clean/ and annotated/{folder_id}/blur/)
but never imported into the database (e.g., because the local workspace
was cleaned up before the import step ran).

Usage:
    cd backend/
    python import_from_gcs_direct.py
"""
import os
import sys
from pathlib import Path, PurePosixPath

# Ensure app modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from sqlalchemy import text
from app.database import SessionLocal
from app.utils.gcs import list_blobs, gcs_path as build_gcs_path


def import_from_gcs():
    bucket_name = os.getenv("GCS_BUCKET_NAME", "amazon-photo-pets")
    if not bucket_name:
        print("❌ GCS_BUCKET_NAME not set")
        return 0

    db = SessionLocal()
    try:
        # Get existing filenames in DB
        existing = db.execute(text("SELECT filename FROM images")).fetchall()
        existing_filenames = {row[0] for row in existing}
        print(f"📊 Database currently has {len(existing_filenames)} images")

        # Get all folder_ids with downloaded_count = 0 but total_in_drive > 0
        folders = db.execute(text("""
            SELECT folder_id, total_in_drive
            FROM drive_folders
            WHERE (downloaded_count IS NULL OR downloaded_count = 0)
              AND (total_in_drive IS NOT NULL AND total_in_drive > 0)
            ORDER BY folder_id
        """)).fetchall()

        if not folders:
            print("✅ No folders to import (all already have images in DB)")
            return 0

        print(f"\n📂 Found {len(folders)} folder(s) to import from GCS")
        total_imported = 0

        for folder_id, total_in_drive in folders:
            print(f"\n{'─' * 50}")
            print(f"📂 Folder: {folder_id} ({total_in_drive} images in GCS)")

            folder_new = 0

            # List images in annotated/{folder_id}/clean/
            clean_prefix = f"annotated/{folder_id}/clean/"
            clean_blobs = list_blobs(clean_prefix)
            image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'}
            clean_files = [
                os.path.basename(b) for b in clean_blobs
                if os.path.splitext(b)[1].lower() in image_exts
            ]

            # List images in annotated/{folder_id}/blur/
            blur_prefix = f"annotated/{folder_id}/blur/"
            blur_blobs = list_blobs(blur_prefix)
            blur_files = [
                os.path.basename(b) for b in blur_blobs
                if os.path.splitext(b)[1].lower() in image_exts
            ]

            # Also list input/ to detect all images (for dedup detection)
            input_prefix = f"input/{folder_id}/"
            input_blobs = list_blobs(input_prefix)
            input_files = set(
                os.path.basename(b) for b in input_blobs
                if os.path.splitext(b)[1].lower() in image_exts
            )

            processed_files = set(clean_files) | set(blur_files)
            # Images in input/ but not in annotated/ are duplicates
            duplicate_files = input_files - processed_files

            print(f"   Clean: {len(clean_files)}, Blurred: {len(blur_files)}, "
                  f"Duplicates: {len(duplicate_files)}")

            # Import clean images
            for filename in clean_files:
                if filename in existing_filenames:
                    continue
                gcs_obj = build_gcs_path(folder_id, filename, "clean")
                url = f"gs://{bucket_name}/{gcs_obj}"
                gcs_input = f"gs://{bucket_name}/input/{folder_id}/{filename}"
                image_id_stem = PurePosixPath(filename).stem

                db.execute(text('''
                    INSERT INTO images (
                        image_id, filename, url, pipeline_status,
                        compliance_status, processed_url, is_improper,
                        human_faces_detected, is_using_processed,
                        source_folder_id, manually_blurred,
                        is_programmatically_blurred, is_manually_modified,
                        is_duplicate, gcs_folder, gcs_input_path
                    ) VALUES (
                        :image_id, :filename, :url, 'completed',
                        'clean', :url, FALSE,
                        0, TRUE,
                        :source_folder_id, FALSE,
                        FALSE, FALSE,
                        FALSE, 'clean', :gcs_input_path
                    )
                '''), {
                    'image_id': image_id_stem,
                    'filename': filename,
                    'url': url,
                    'source_folder_id': folder_id,
                    'gcs_input_path': gcs_input,
                })
                existing_filenames.add(filename)
                folder_new += 1

            # Import blurred images
            for filename in blur_files:
                if filename in existing_filenames:
                    continue
                gcs_obj = build_gcs_path(folder_id, filename, "blur")
                url = f"gs://{bucket_name}/{gcs_obj}"
                gcs_input = f"gs://{bucket_name}/input/{folder_id}/{filename}"
                image_id_stem = PurePosixPath(filename).stem

                db.execute(text('''
                    INSERT INTO images (
                        image_id, filename, url, pipeline_status,
                        compliance_status, processed_url, is_improper,
                        human_faces_detected, is_using_processed,
                        source_folder_id, manually_blurred,
                        is_programmatically_blurred, is_manually_modified,
                        is_duplicate, gcs_folder, gcs_input_path
                    ) VALUES (
                        :image_id, :filename, :url, 'completed',
                        'blurred', :url, FALSE,
                        1, TRUE,
                        :source_folder_id, FALSE,
                        TRUE, FALSE,
                        FALSE, 'blur', :gcs_input_path
                    )
                '''), {
                    'image_id': image_id_stem,
                    'filename': filename,
                    'url': url,
                    'source_folder_id': folder_id,
                    'gcs_input_path': gcs_input,
                })
                existing_filenames.add(filename)
                folder_new += 1

            # Import duplicate images (from input/ only)
            for filename in duplicate_files:
                if filename in existing_filenames:
                    continue
                gcs_input = f"gs://{bucket_name}/input/{folder_id}/{filename}"
                image_id_stem = PurePosixPath(filename).stem

                db.execute(text('''
                    INSERT INTO images (
                        image_id, filename, url, pipeline_status,
                        compliance_status, processed_url, is_improper,
                        human_faces_detected, is_using_processed,
                        source_folder_id, manually_blurred,
                        is_programmatically_blurred, is_manually_modified,
                        is_duplicate, gcs_folder, gcs_input_path
                    ) VALUES (
                        :image_id, :filename, :gcs_input, 'pending',
                        'duplicate', NULL, FALSE,
                        0, FALSE,
                        :source_folder_id, FALSE,
                        FALSE, FALSE,
                        TRUE, 'input', :gcs_input
                    )
                '''), {
                    'image_id': image_id_stem,
                    'filename': filename,
                    'gcs_input': gcs_input,
                    'source_folder_id': folder_id,
                })
                existing_filenames.add(filename)

            print(f"   ✅ Imported {folder_new} new images")
            total_imported += folder_new

        db.commit()

        # Update drive_folders stats
        print(f"\n📊 Updating drive_folders stats...")
        for folder_id, _ in folders:
            count = db.execute(
                text("SELECT COUNT(*) FROM images WHERE source_folder_id = :fid"),
                {"fid": folder_id}
            ).scalar() or 0
            dup_count = db.execute(
                text("SELECT COUNT(*) FROM images WHERE source_folder_id = :fid AND is_duplicate = TRUE"),
                {"fid": folder_id}
            ).scalar() or 0
            blurred = db.execute(
                text("SELECT COUNT(*) FROM images WHERE source_folder_id = :fid AND compliance_status = 'blurred'"),
                {"fid": folder_id}
            ).scalar() or 0
            clean = db.execute(
                text("SELECT COUNT(*) FROM images WHERE source_folder_id = :fid AND compliance_status = 'clean'"),
                {"fid": folder_id}
            ).scalar() or 0

            db.execute(text("""
                UPDATE drive_folders SET
                    downloaded_count = :count,
                    unique_count = :unique,
                    duplicate_count = :dups,
                    blurred_count = :blurred,
                    clean_count = :clean,
                    error_log = NULL,
                    status = 'completed'
                WHERE folder_id = :fid
            """), {
                'count': count,
                'unique': count - dup_count,
                'dups': dup_count,
                'blurred': blurred,
                'clean': clean,
                'fid': folder_id,
            })

        db.commit()

        # Final summary
        total_in_db = db.execute(text("SELECT COUNT(*) FROM images")).scalar()
        total_non_dup = db.execute(
            text("SELECT COUNT(*) FROM images WHERE is_duplicate = FALSE")
        ).scalar()
        print(f"\n{'=' * 50}")
        print(f"✅ Import complete!")
        print(f"   • New images imported: {total_imported}")
        print(f"   • Total in database: {total_in_db}")
        print(f"   • Non-duplicate: {total_non_dup}")
        return total_imported

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("📥 IMPORTING IMAGES FROM GCS TO DATABASE (Direct)")
    print("=" * 70)
    print()
    count = import_from_gcs()
    if count > 0:
        print(f"\n🎉 Successfully imported {count} images!")
    else:
        print(f"\n⚠️  No new images were imported.")
    sys.exit(0)
