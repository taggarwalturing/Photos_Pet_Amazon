from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text, inspect
import httpx
import re
import os
import io
import datetime
from contextlib import asynccontextmanager
from app.config import settings
from app.database import engine, Base, SessionLocal, get_db
from app.routers import auth, admin, annotator, compliance, compliance_management, pipeline, public_blur, annotator_blur, arbiter
from app.seed import seed_database
from app.models.image import Image

# Google Drive API imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Image processing imports
from PIL import Image as PILImage
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False

# Import all models so Base knows about them
from app.models import user, image, category, option, annotator_category, annotation, edit_request, notification, drive_folder, final_label  # noqa
from app.models import settings as settings_model  # noqa - rename to avoid conflict with config.settings

# Google Drive service account setup from settings
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_drive_service():
    """Create Google Drive API service using service account JSON file or settings."""
    import json as _json
    
    # Method 1: Use GOOGLE_SERVICE_ACCOUNT_FILE (JSON file path) — preferred
    sa_file = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
    if sa_file:
        from pathlib import Path
        # Try relative to backend directory
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        candidates = [
            Path(sa_file),  # absolute or cwd-relative
            Path(backend_dir) / sa_file,  # relative to backend/
            Path(backend_dir) / "master_pipeline" / sa_file,  # relative to pipeline/
        ]
        for creds_path in candidates:
            if creds_path.exists():
                with open(creds_path, 'r') as f:
                    creds_dict = _json.load(f)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict, scopes=SCOPES
                )
                return build('drive', 'v3', credentials=credentials)
    
    # Method 2: Use individual env vars (legacy)
    private_key = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY', '')
    if private_key:
        private_key = private_key.replace('\\n', '\n')
    credentials_info = {
            "type": getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_TYPE', 'service_account'),
            "project_id": getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_PROJECT_ID', ''),
            "private_key_id": getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID', ''),
        "private_key": private_key,
            "client_email": getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL', ''),
            "client_id": getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_CLIENT_ID', ''),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=credentials)
    
    raise ValueError("No Google Drive credentials configured. Set GOOGLE_SERVICE_ACCOUNT_FILE in .env")

# Create tables
Base.metadata.create_all(bind=engine)

# Add missing columns to existing tables (lightweight migration)
def _migrate():
    inspector = inspect(engine)
    if "annotations" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("annotations")}
        with engine.begin() as conn:
            if "review_status" not in existing:
                conn.execute(text("ALTER TABLE annotations ADD COLUMN review_status VARCHAR(20)"))
            if "review_note" not in existing:
                conn.execute(text("ALTER TABLE annotations ADD COLUMN review_note TEXT"))
            if "reviewed_by" not in existing:
                conn.execute(text("ALTER TABLE annotations ADD COLUMN reviewed_by INTEGER REFERENCES users(id)"))
            if "reviewed_at" not in existing:
                conn.execute(text("ALTER TABLE annotations ADD COLUMN reviewed_at TIMESTAMPTZ"))
            if "time_spent_seconds" not in existing:
                conn.execute(text("ALTER TABLE annotations ADD COLUMN time_spent_seconds INTEGER DEFAULT 0 NOT NULL"))
            if "is_rework" not in existing:
                conn.execute(text("ALTER TABLE annotations ADD COLUMN is_rework BOOLEAN DEFAULT FALSE NOT NULL"))
            if "rework_time_seconds" not in existing:
                conn.execute(text("ALTER TABLE annotations ADD COLUMN rework_time_seconds INTEGER DEFAULT 0 NOT NULL"))
        print("[MIGRATE] Checked/added review columns to annotations table")
    # Add improper columns to images table
    if "images" in inspector.get_table_names():
        existing_img = {col["name"] for col in inspector.get_columns("images")}
        with engine.begin() as conn:
            if "is_improper" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_improper BOOLEAN DEFAULT FALSE NOT NULL"))
            if "improper_reason" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN improper_reason TEXT"))
            if "marked_improper_by" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN marked_improper_by INTEGER REFERENCES users(id)"))
            if "marked_improper_at" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN marked_improper_at TIMESTAMPTZ"))
            # Add AI-generated detection columns
            if "is_ai_generated" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_ai_generated BOOLEAN"))
            if "ai_detection_confidence" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN ai_detection_confidence INTEGER"))
            if "marked_ai_by" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN marked_ai_by INTEGER REFERENCES users(id)"))
            if "marked_ai_at" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN marked_ai_at TIMESTAMPTZ"))
            # Add arbiter classifier columns
            if "arbiter_labels" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN arbiter_labels JSON"))
            if "arbiter_classified_at" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN arbiter_classified_at TIMESTAMPTZ"))
            # Add source Drive folder tracking
            if "source_drive_folder_id" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN source_drive_folder_id VARCHAR(255)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_source_drive_folder_id ON images(source_drive_folder_id)"))
            # Add Google Drive file ID tracking
            if "image_drive_id" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN image_drive_id VARCHAR(255)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_image_drive_id ON images(image_drive_id)"))
            # Add annotator blur/restore tracking columns
            if "is_blurred_annotator" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_blurred_annotator BOOLEAN DEFAULT FALSE NOT NULL"))
            if "is_restore_annotator" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_restore_annotator BOOLEAN DEFAULT FALSE NOT NULL"))
            if "restored_by_annotator_id" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN restored_by_annotator_id INTEGER REFERENCES users(id)"))
            if "restored_at_annotator" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN restored_at_annotator TIMESTAMP WITH TIME ZONE"))
            # Add deliverable image tracking columns
            if "deliverable_image_path" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN deliverable_image_path TEXT"))
            # Add clean status columns (user-requested)
            if "is_manually_modified" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_manually_modified BOOLEAN DEFAULT FALSE NOT NULL"))
            if "is_programmatically_blurred" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_programmatically_blurred BOOLEAN DEFAULT FALSE NOT NULL"))
            if "is_duplicate" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN is_duplicate BOOLEAN DEFAULT FALSE NOT NULL"))
            if "parent_image" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN parent_image VARCHAR(255)"))
            if "image_path" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN image_path TEXT"))
            if "gcs_folder" not in existing_img:
                conn.execute(text("ALTER TABLE images ADD COLUMN gcs_folder VARCHAR(20) DEFAULT 'input'"))
            # Drop legacy is_modified column (replaced by is_manually_modified)
            if "is_modified" in existing_img:
                conn.execute(text("ALTER TABLE images DROP COLUMN is_modified"))
                print("[MIGRATE] Dropped legacy is_modified column from images")
        print("[MIGRATE] Checked/added improper, AI-generated, arbiter, deliverable, and status columns to images table")

    # Drop dead annotator_image_assignments table (all annotators access all images now)
    if "annotator_image_assignments" in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE annotator_image_assignments"))
        print("[MIGRATE] Dropped dead table annotator_image_assignments")

    # ── Add performance indexes ─────────────────────────────────────
    with engine.begin() as conn:
        # Filename lookups (photo registry, dedup checks)
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_filename ON images(filename)"))
        # Deliverable filter queries
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_deliverable ON images(deliverable_image_path) WHERE deliverable_image_path IS NOT NULL"))
        # Annotation composite index (most common join pattern)
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_annotations_image_category ON annotations(image_id, category_id)"))
        # Annotator lookup + date for daily stats
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_annotations_annotator_updated ON annotations(annotator_id, updated_at)"))
        # Review status filtering
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_annotations_review_status ON annotations(review_status) WHERE review_status IS NOT NULL"))
        # Image compliance status
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_compliance ON images(compliance_status)"))
        # Manually blurred filter
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_manually_blurred ON images(manually_blurred) WHERE manually_blurred = TRUE"))
    print("[MIGRATE] Ensured performance indexes exist")

_migrate()

# Lifespan manager for background tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Seed database with admin users, categories, etc.
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    # Startup: Start background tasks
    try:
        from app.background_tasks import start_background_tasks
        await start_background_tasks()
    except Exception as e:
        import logging
        logging.error(f"Failed to start background tasks: {e}")
    yield


app = FastAPI(
    title="Photo Pets Annotation Tool",
    description="Image annotation tool for pet photo categorization",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(annotator.router, prefix="/api")
app.include_router(annotator_blur.router, prefix="/api")
app.include_router(compliance.router, prefix="/api")
app.include_router(compliance_management.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(public_blur.router, prefix="/api")
app.include_router(arbiter.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Image Proxy Endpoint ─────────────────────────────────────────
# Proxies images from Google Drive to bypass CORS restrictions
# With local file caching for fast subsequent loads

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "image_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cached_image(image_id: int):
    """Check if image is cached locally."""
    cache_path = os.path.join(CACHE_DIR, f"{image_id}.jpg")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read(), "image/jpeg"
    return None, None

def cache_image(image_id: int, content: bytes, mime_type: str):
    """Cache image locally (convert to JPEG for consistency)."""
    try:
        # Always save as JPEG for consistency
        cache_path = os.path.join(CACHE_DIR, f"{image_id}.jpg")
        
        # If not JPEG, convert using PIL
        if mime_type != "image/jpeg":
            try:
                pil_image = PILImage.open(io.BytesIO(content))
                if pil_image.mode in ('RGBA', 'P'):
                    pil_image = pil_image.convert('RGB')
                output_buffer = io.BytesIO()
                pil_image.save(output_buffer, format='JPEG', quality=85)
                content = output_buffer.getvalue()
            except Exception:
                pass  # Keep original content if conversion fails
        
        with open(cache_path, "wb") as f:
            f.write(content)
    except Exception as e:
        print(f"Failed to cache image {image_id}: {e}")

@app.get("/api/images/proxy/{image_id}")
def proxy_image(image_id: int):
    """
    Proxy endpoint to fetch images from S3, Google Drive, or local files.
    This bypasses CORS restrictions by fetching server-side with proper authentication.
    Converts HEIC/HEIF images to JPEG for browser compatibility.
    Uses local file caching for fast subsequent loads.
    """
    # Check cache first
    cached_content, cached_mime = get_cached_image(image_id)
    if cached_content:
        return Response(
            content=cached_content,
            media_type=cached_mime,
            headers={
                "Cache-Control": "public, max-age=604800",  # 7 days
                "X-Cache": "HIT",
            }
        )
    
    db = SessionLocal()
    try:
        img = db.query(Image).filter(Image.id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")
        
        url = img.url
        
        # Handle GCS gs:// URLs
        if url.startswith('gs://'):
            try:
                from app.utils.gcs import download_to_bytes, parse_gs_uri
                _, blob_path = parse_gs_uri(url)
                content = download_to_bytes(blob_path)
                ext = os.path.splitext(img.filename)[1].lower()
                mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                             '.gif': 'image/gif', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                cache_image(image_id, content, mime_type)
                return Response(
                    content=content, media_type=mime_type,
                    headers={"Cache-Control": "public, max-age=604800", "X-Cache": "MISS", "X-Source": "gcs"}
                )
            except Exception as e:
                print(f"[Proxy] GCS fetch failed for {img.filename}: {e}")
                raise HTTPException(status_code=502, detail=f"GCS fetch failed: {str(e)}")
        
        # Handle local file:// URLs
        if url.startswith('file://'):
            local_path = url.replace('file://', '')
            # Make it absolute if it's relative
            if not os.path.isabs(local_path):
                # Assume relative to backend directory
                backend_dir = os.path.dirname(os.path.dirname(__file__))
                local_path = os.path.join(backend_dir, local_path)
            
            if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                # Fallback: scan pipeline workspace folders for the file by filename
                filename = os.path.basename(local_path)
                from app.utils import get_pipeline_workspace
                workspace = str(get_pipeline_workspace())
                found = False
                
                # Build search directories: per-folder workspaces + legacy flat workspace
                search_roots = []
                folders_dir = os.path.join(workspace, "folders")
                if os.path.isdir(folders_dir):
                    for fd in sorted(os.listdir(folders_dir)):
                        fd_path = os.path.join(folders_dir, fd)
                        if os.path.isdir(fd_path):
                            search_roots.append(fd_path)
                search_roots.append(workspace)  # legacy flat workspace as fallback
                
                for search_root in search_roots:
                    if found:
                        break
                    for sub in ["deliverable", "01_downloaded_from_drive"]:
                        candidate = os.path.join(search_root, sub, filename)
                        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                            local_path = candidate
                            found = True
                            break
                if not found:
                    # Try GCS as an intermediate fallback — use DB gcs_folder for direct path
                    try:
                        from app.utils.gcs import download_to_bytes, gcs_path as build_gcs_path, blob_exists as gcs_blob_exists
                        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
                        fid = img.source_drive_folder_id
                        if gcs_bucket and fid:
                            # Try the DB-tracked stage first, then fallback stages
                            stages = [img.gcs_folder or "input"]
                            for s in ("blur", "clean", "input"):
                                if s not in stages:
                                    stages.append(s)
                            for stage in stages:
                                blob_name = build_gcs_path(fid, filename, stage)
                                if gcs_blob_exists(blob_name):
                                    gcs_content = download_to_bytes(blob_name)
                                    if len(gcs_content) > 0:
                                        ext_c = os.path.splitext(filename)[1].lower()
                                        mime_c = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                                                  '.png': 'image/png', '.gif': 'image/gif',
                                                  '.webp': 'image/webp'}.get(ext_c, 'image/jpeg')
                                        cache_image(image_id, gcs_content, mime_c)
                                        return Response(
                                            content=gcs_content, media_type=mime_c,
                                            headers={"Cache-Control": "public, max-age=604800",
                                                     "X-Cache": "GCS_FALLBACK", "X-Source": "gcs"}
                                        )
                    except ImportError:
                        pass
                    except Exception as gcs_fb_err:
                        print(f"[Proxy] GCS fallback failed for {filename}: {gcs_fb_err}")

                if not found:
                    # Last resort: try re-downloading from Google Drive
                    try:
                        gdrive_folder_id = getattr(settings, 'GOOGLE_DRIVE_FOLDER_ID', None)
                        if gdrive_folder_id:
                            service = get_drive_service()
                            query = f"name = '{filename}' and trashed = false"
                            results = service.files().list(
                                q=query,
                                fields="files(id, name, mimeType)",
                                spaces='drive',
                            ).execute()
                            gdrive_files = results.get('files', [])
                            if gdrive_files:
                                file_id = gdrive_files[0]['id']
                                request_dl = service.files().get_media(fileId=file_id)
                                file_buffer = io.BytesIO()
                                downloader = MediaIoBaseDownload(file_buffer, request_dl)
                                done = False
                                while not done:
                                    _, done = downloader.next_chunk()
                                file_buffer.seek(0)
                                gdrive_content = file_buffer.read()
                                if len(gdrive_content) > 0:
                                    # Save to download folder for future
                                    dl_folder = os.path.join(workspace, "01_downloaded_from_drive")
                                    os.makedirs(dl_folder, exist_ok=True)
                                    with open(os.path.join(dl_folder, filename), "wb") as f:
                                        f.write(gdrive_content)
                                    # Cache and serve
                                    cache_image(image_id, gdrive_content, 'image/jpeg')
                                    return Response(
                                        content=gdrive_content,
                                        media_type='image/jpeg',
                                        headers={"Cache-Control": "public, max-age=604800", "X-Cache": "GDRIVE_RESTORE"}
                                    )
                    except Exception as gdrive_err:
                        print(f"[Proxy] Google Drive fallback failed for {filename}: {gdrive_err}")
                    
                raise HTTPException(status_code=404, detail=f"Local image file not found: {local_path}")
            
            # Read local file
            with open(local_path, 'rb') as f:
                content = f.read()
            
            # Determine mime type from extension
            ext = os.path.splitext(local_path)[1].lower()
            filename = os.path.basename(local_path).lower()
            
            # Check if this is a HEIC/HEIF file that needs conversion
            is_heic = ext in ('.heic', '.heif') or 'heic' in filename or 'heif' in filename
            
            if is_heic and HEIF_SUPPORT:
                # Convert HEIC to JPEG for browser compatibility
                try:
                    file_buffer = io.BytesIO(content)
                    pil_image = PILImage.open(file_buffer)
                    # Convert to RGB if necessary (HEIC might have alpha)
                    if pil_image.mode in ('RGBA', 'P'):
                        pil_image = pil_image.convert('RGB')
                    
                    output_buffer = io.BytesIO()
                    pil_image.save(output_buffer, format='JPEG', quality=85)
                    content = output_buffer.getvalue()
                    mime_type = 'image/jpeg'
                except Exception as conv_err:
                    print(f"HEIC conversion failed for {local_path}: {conv_err}")
                    # Fall back to original content
                    mime_type = 'image/heic'
            else:
                mime_type = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                }.get(ext, 'image/jpeg')
            
            # Cache it
            cache_image(image_id, content, mime_type)
            
            return Response(
                content=content,
                media_type=mime_type,
                headers={
                    "Cache-Control": "public, max-age=604800",
                    "X-Cache": "MISS",
                    "X-Source": "local-file",
                }
            )
        
        # Extract Google Drive file ID from URL
        gdrive_match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
        if not gdrive_match:
            raise HTTPException(status_code=400, detail="Invalid image URL - must be Google Drive or file:// URL")
        
        file_id = gdrive_match.group(1)
        
        try:
            # Use Google Drive API to download the file
            service = get_drive_service()
            
            # Get file metadata to determine mime type
            file_metadata = service.files().get(fileId=file_id, fields='mimeType,name').execute()
            mime_type = file_metadata.get('mimeType', 'image/png')
            filename = file_metadata.get('name', '').lower()
            
            # Download the file content
            request = service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            file_buffer.seek(0)
            
            # Check if this is a HEIC/HEIF file that needs conversion
            is_heic = (
                mime_type in ('image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence') or
                filename.endswith('.heic') or filename.endswith('.heif')
            )
            
            if is_heic and HEIF_SUPPORT:
                # Convert HEIC to JPEG for browser compatibility
                try:
                    pil_image = PILImage.open(file_buffer)
                    # Convert to RGB if necessary (HEIC might have alpha)
                    if pil_image.mode in ('RGBA', 'P'):
                        pil_image = pil_image.convert('RGB')
                    
                    output_buffer = io.BytesIO()
                    pil_image.save(output_buffer, format='JPEG', quality=85)
                    output_buffer.seek(0)
                    content = output_buffer.read()
                    mime_type = 'image/jpeg'
                except Exception as conv_err:
                    print(f"HEIC conversion failed for {file_id}: {conv_err}")
                    # Fall back to original content
                    file_buffer.seek(0)
                    content = file_buffer.read()
            else:
                content = file_buffer.read()
            
            # Cache the image for future requests
            cache_image(image_id, content, mime_type)
            
            return Response(
                content=content,
                media_type=mime_type,
                headers={
                    "Cache-Control": "public, max-age=604800",  # 7 days
                    "X-Cache": "MISS",
                }
            )
        except Exception as e:
            print(f"Error fetching image {file_id}: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to fetch image: {str(e)}")
    finally:
        db.close()


@app.get("/api/images/signed-url/{image_id}")
def get_signed_url(image_id: int, folder: str = None):
    """
    Return a GCS signed URL for direct browser access.
    
    For images stored in GCS (url starts with gs://), generates a signed URL.
    For legacy file:// images, redirects to the proxy endpoint.
    
    Optional `folder` query param overrides gcs_folder (input/annotated/final),
    useful for showing the original via ?folder=input in the blur tool.
    """
    db = SessionLocal()
    try:
        img = db.query(Image).filter(Image.id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")
        
        url = img.url or ""
        
        if url.startswith("gs://"):
            from app.utils.gcs import generate_signed_url as sign, parse_gs_uri, gcs_path as build_gcs_path
            
            _, original_blob_path = parse_gs_uri(url)
            
            if folder and folder in ("input", "annotated") and img.source_drive_folder_id:
                blob_path = build_gcs_path(img.source_drive_folder_id, img.filename, folder)
            else:
                stage = img.gcs_folder or "input"
                blob_path = build_gcs_path(img.source_drive_folder_id or "", img.filename, stage)
            
            try:
                signed = sign(blob_path, expiration_seconds=3600)
                return {
                    "signed_url": signed,
                    "expires_in": 3600,
                    "stage": folder or img.gcs_folder or "input",
                    "image_id": image_id,
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to generate signed URL: {str(e)}")
        else:
            return {
                "signed_url": f"/api/images/proxy/{image_id}?t={int(datetime.datetime.now().timestamp())}",
                "expires_in": 86400,
                "stage": "legacy",
                "image_id": image_id,
            }
    finally:
        db.close()
