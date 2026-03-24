from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query as WSQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text, inspect
import httpx
import re
import os
import io
import datetime
import threading
from contextlib import asynccontextmanager
from app.config import settings
from app.database import engine, Base, SessionLocal, get_db
from app.routers import auth, admin, annotator, compliance, compliance_management, pipeline, public_blur, annotator_blur, arbiter
from app.seed import seed_database
from app.models.image import Image
from app.ws_manager import lock_manager
from app.services.auth import decode_access_token

# Google Drive API imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Image processing imports
from PIL import Image as PILImage, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False

# Import all models so Base knows about them
from app.models import user, image, drive_folder  # noqa
from app.models import arbiter_prediction  # noqa

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

# ── Lightweight migration: add missing columns to existing tables ──
def _migrate():
    """
    Ensure the database schema matches the current models.
    Base.metadata.create_all() handles new tables, but existing tables
    may need new columns added.
    """
    inspector = inspect(engine)

    # ── Images table: add any columns that are in the model but missing from DB ──
    if "images" in inspector.get_table_names():
        existing_img = {col["name"] for col in inspector.get_columns("images")}
        new_columns = {
            # Column name → SQL definition
            "image_id": "VARCHAR(500)",
            "gcs_input_path": "VARCHAR(500)",
            "gcs_annotated_path": "VARCHAR(500)",
            "gcs_folder": "VARCHAR(50) DEFAULT 'input'",
            "is_duplicate": "BOOLEAN DEFAULT FALSE",
            "parent_image_id": "INTEGER REFERENCES images(id)",
            "pipeline_status": "VARCHAR(50) DEFAULT 'pending'",
            "compliance_status": "VARCHAR(50)",
            "human_faces_detected": "INTEGER DEFAULT 0",
            "is_ai_generated": "BOOLEAN DEFAULT FALSE",
            "ai_detection_confidence": "INTEGER",
            "marked_ai_by": "INTEGER REFERENCES users(id)",
            "marked_ai_at": "TIMESTAMPTZ",
            "human_visible": "BOOLEAN",
            "human_visible_marked_by": "INTEGER REFERENCES users(id)",
            "human_visible_marked_at": "TIMESTAMPTZ",
            "is_programmatically_blurred": "BOOLEAN DEFAULT FALSE",
            "is_manually_modified": "BOOLEAN DEFAULT FALSE",
            "is_using_processed": "BOOLEAN DEFAULT TRUE",
            "manually_blurred": "BOOLEAN DEFAULT FALSE",
            "manually_blurred_by": "INTEGER REFERENCES users(id)",
            "manually_blurred_at": "TIMESTAMPTZ",
            "is_blurred_annotator": "BOOLEAN DEFAULT FALSE",
            "is_restore_annotator": "BOOLEAN DEFAULT FALSE",
            "blur_regions": "JSON",
            "processed_url": "VARCHAR(1000)",
            "processing_method": "VARCHAR(50)",
            "annotation_status": "VARCHAR(50) DEFAULT 'pending'",
            "annotations": "JSON",
            "annotated_by": "INTEGER REFERENCES users(id)",
            "annotated_at": "TIMESTAMPTZ",
            "review_status": "VARCHAR(50)",
            "review_note": "TEXT",
            "reviewed_by": "INTEGER REFERENCES users(id)",
            "reviewed_at": "TIMESTAMPTZ",
            "is_improper": "BOOLEAN DEFAULT FALSE",
            "improper_reason": "TEXT",
            "marked_improper_by": "INTEGER REFERENCES users(id)",
            "marked_improper_at": "TIMESTAMPTZ",
            "assigned_annotator": "INTEGER REFERENCES users(id)",
            "locked_by": "INTEGER REFERENCES users(id)",
            "locked_at": "TIMESTAMPTZ",
            "deliverable_image_path": "VARCHAR(500)",
            "arbiter_labels": "JSON",
            "annotation_history": "JSON DEFAULT '[]'::json",
            "original_filename": "VARCHAR(500)",
            "image_drive_id": "VARCHAR(200)",
            "source_folder_id": "VARCHAR(200)",
            "updated_at": "TIMESTAMPTZ DEFAULT now()",
        }
        with engine.begin() as conn:
            for col_name, col_def in new_columns.items():
                if col_name not in existing_img:
                    try:
                        conn.execute(text(f"ALTER TABLE images ADD COLUMN {col_name} {col_def}"))
                    except Exception as e:
                        print(f"[MIGRATE] Warning: could not add {col_name}: {e}")
            # Rename legacy columns if they exist
            if "source_folder_id" in existing_img and "source_folder_id" not in existing_img:
                try:
                    conn.execute(text("ALTER TABLE images RENAME COLUMN source_folder_id TO source_folder_id"))
                except Exception:
                    pass
        # Drop deprecated columns from old schema
        deprecated_columns = [
            "compliance_processed", "processing_log", "original_url",
            "source_drive_folder_id", "image_path", "arbiter_classified_at",
            "annotated_blur_url", "restored_by_annotator_id",
            "restored_at_annotator", "original_format", "parent_image",
        ]
        # Re-read columns after adds
        existing_img_after = {c["name"] for c in inspect(engine).get_columns("images")}
        for old_col in deprecated_columns:
            if old_col in existing_img_after:
                try:
                    conn.execute(text(f"ALTER TABLE images DROP COLUMN IF EXISTS {old_col}"))
                    print(f"[MIGRATE] Dropped deprecated column: {old_col}")
                except Exception as e:
                    print(f"[MIGRATE] Warning: could not drop {old_col}: {e}")

        # Relax NOT NULL constraints that don't match the model
        for col_relax in ["url", "is_improper", "human_faces_detected",
                          "is_using_processed", "manually_blurred",
                          "is_blurred_annotator", "is_restore_annotator",
                          "is_manually_modified", "is_programmatically_blurred",
                          "is_duplicate"]:
            try:
                conn.execute(text(f"ALTER TABLE images ALTER COLUMN {col_relax} DROP NOT NULL"))
            except Exception:
                pass

        print("[MIGRATE] Checked images table columns")

    # ── Users table: add new columns ──
    if "users" in inspector.get_table_names():
        existing_usr = {col["name"] for col in inspector.get_columns("users")}
        user_new_columns = {
            "assigned_image_count": "INTEGER DEFAULT 0",
        }
        with engine.begin() as conn:
            for col_name, col_def in user_new_columns.items():
                if col_name not in existing_usr:
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                        print(f"[MIGRATE] Added users.{col_name}")
                    except Exception as e:
                        print(f"[MIGRATE] Warning: could not add users.{col_name}: {e}")
        print("[MIGRATE] Checked users table columns")

    # ── Performance indexes ──
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_image_id ON images(image_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_filename ON images(filename)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_compliance ON images(compliance_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_source_folder ON images(source_folder_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_annotation_status ON images(annotation_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_review_status ON images(review_status) WHERE review_status IS NOT NULL"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_annotated_by ON images(annotated_by)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_deliverable ON images(deliverable_image_path) WHERE deliverable_image_path IS NOT NULL"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_manually_blurred ON images(manually_blurred) WHERE manually_blurred = TRUE"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_images_assigned_annotator ON images(assigned_annotator)"))
        # Migrate data from old assigned_to column and drop it
        conn.execute(text("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='images' AND column_name='assigned_to') THEN
                    -- If both columns exist, copy data then drop old column
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='images' AND column_name='assigned_annotator') THEN
                        UPDATE images SET assigned_annotator = assigned_to WHERE assigned_to IS NOT NULL AND assigned_annotator IS NULL;
                        ALTER TABLE images DROP COLUMN assigned_to;
                    ELSE
                        -- Only old column exists, just rename
                        ALTER TABLE images RENAME COLUMN assigned_to TO assigned_annotator;
                    END IF;
                END IF;
            END $$;
        """))
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


# ── WebSocket for real-time lock broadcasts ──────────────────────
@app.websocket("/ws/locks")
async def ws_locks(websocket: WebSocket, token: str = WSQuery(None)):
    """
    Annotators connect here to receive real-time lock events.
    Auth via ?token=<jwt> query param (WebSocket can't use headers).
    """
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = int(payload.get("sub", 0))
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token payload")
        return

    await lock_manager.connect(websocket, user_id)
    try:
        # Keep connection alive — just wait for client messages (pings)
        while True:
            await websocket.receive_text()  # client can send pings; we just keep alive
    except WebSocketDisconnect:
        pass
    finally:
        await lock_manager.disconnect(websocket, user_id)


# ── Image Proxy Endpoint ─────────────────────────────────────────
# Proxies images from Google Drive to bypass CORS restrictions
# With local file caching for fast subsequent loads

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "image_cache")
THUMB_DIR = os.path.join(CACHE_DIR, "thumbnails")
VIEW_DIR = os.path.join(CACHE_DIR, "view")  # Medium-res for annotation/review
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)
os.makedirs(VIEW_DIR, exist_ok=True)

# Thumbnail size for gallery grid (max width/height)
THUMB_MAX_SIZE = 400
# View size for annotation/review (max width/height)
VIEW_MAX_SIZE = 1200


def get_cached_image(image_id: int):
    """Check if image is cached locally."""
    cache_path = os.path.join(CACHE_DIR, f"{image_id}.jpg")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read(), "image/jpeg"
    return None, None


def get_cached_thumbnail(image_id: int):
    """Check if thumbnail is cached locally."""
    thumb_path = os.path.join(THUMB_DIR, f"{image_id}.jpg")
    if os.path.exists(thumb_path):
        with open(thumb_path, "rb") as f:
            return f.read(), "image/jpeg"
    return None, None


def _to_jpeg(content: bytes, mime_type: str) -> bytes:
    """Convert image bytes to JPEG if not already."""
    if mime_type == "image/jpeg":
        return content
    try:
        pil_image = PILImage.open(io.BytesIO(content))
        if pil_image.mode in ('RGBA', 'P'):
            pil_image = pil_image.convert('RGB')
        buf = io.BytesIO()
        pil_image.save(buf, format='JPEG', quality=85)
        return buf.getvalue()
    except Exception:
        return content


def _make_thumbnail(content: bytes) -> bytes:
    """Create a small thumbnail from image bytes."""
    try:
        pil_image = PILImage.open(io.BytesIO(content))
        pil_image = ImageOps.exif_transpose(pil_image)  # Apply EXIF orientation
        if pil_image.mode in ('RGBA', 'P'):
            pil_image = pil_image.convert('RGB')
        pil_image.thumbnail((THUMB_MAX_SIZE, THUMB_MAX_SIZE), PILImage.LANCZOS)
        buf = io.BytesIO()
        pil_image.save(buf, format='JPEG', quality=70)
        return buf.getvalue()
    except Exception:
        return content  # Return original if thumbnail generation fails


def _make_view_image(content: bytes) -> bytes:
    """Create a medium-res image (1200px) for annotation/review views."""
    try:
        pil_image = PILImage.open(io.BytesIO(content))
        pil_image = ImageOps.exif_transpose(pil_image)  # Apply EXIF orientation
        if pil_image.mode in ('RGBA', 'P'):
            pil_image = pil_image.convert('RGB')
        w, h = pil_image.size
        if max(w, h) <= VIEW_MAX_SIZE:
            # Already small enough, just save as JPEG
            buf = io.BytesIO()
            pil_image.save(buf, format='JPEG', quality=85)
            return buf.getvalue()
        pil_image.thumbnail((VIEW_MAX_SIZE, VIEW_MAX_SIZE), PILImage.LANCZOS)
        buf = io.BytesIO()
        pil_image.save(buf, format='JPEG', quality=85)
        return buf.getvalue()
    except Exception:
        return content


def get_cached_view(image_id: int):
    """Check if medium-res view image is cached locally."""
    view_path = os.path.join(VIEW_DIR, f"{image_id}.jpg")
    if os.path.exists(view_path):
        with open(view_path, "rb") as f:
            return f.read(), "image/jpeg"
    return None, None


# Max cache sizes (bytes).  Full-res is the heavy one (~2-5MB each).
# View (~100KB) and thumb (~20KB) are small — no eviction needed.
FULL_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB for full-res images
_cache_evict_lock = threading.Lock()


def _evict_oldest_cached(cache_dir: str, max_bytes: int):
    """Remove oldest files from a cache directory until total size < max_bytes."""
    try:
        files = []
        for f in os.listdir(cache_dir):
            fp = os.path.join(cache_dir, f)
            if os.path.isfile(fp) and not os.path.isdir(fp):
                files.append((fp, os.path.getmtime(fp), os.path.getsize(fp)))
        total = sum(s for _, _, s in files)
        if total <= max_bytes:
            return
        # Sort oldest first
        files.sort(key=lambda x: x[1])
        while total > max_bytes and files:
            fp, _, sz = files.pop(0)
            try:
                os.remove(fp)
                total -= sz
            except OSError:
                pass
    except Exception:
        pass


def _normalize_full_image(content: bytes) -> bytes:
    """Apply EXIF orientation to full-res image so browser and server agree on orientation."""
    try:
        pil_image = PILImage.open(io.BytesIO(content))
        transposed = ImageOps.exif_transpose(pil_image)
        if transposed.mode in ('RGBA', 'P'):
            transposed = transposed.convert('RGB')
        buf = io.BytesIO()
        transposed.save(buf, format='JPEG', quality=95)
        return buf.getvalue()
    except Exception:
        return content


def cache_image(image_id: int, content: bytes, mime_type: str) -> bytes:
    """Cache full image (raw GCS bytes), medium-res view, and thumbnail.
    Thumbnails & views apply EXIF transpose (because PIL strips EXIF).
    Full-res is stored as-is so the browser can apply EXIF natively.
    Returns the raw content bytes."""
    try:
        jpeg_content = _to_jpeg(content, mime_type)
        # Save full image as-is (raw GCS bytes, browser handles EXIF)
        with open(os.path.join(CACHE_DIR, f"{image_id}.jpg"), "wb") as f:
            f.write(jpeg_content)
        # Save medium-res view (1200px) — exif_transpose applied inside
        view_content = _make_view_image(jpeg_content)
        with open(os.path.join(VIEW_DIR, f"{image_id}.jpg"), "wb") as f:
            f.write(view_content)
        # Save thumbnail — exif_transpose applied inside
        thumb_content = _make_thumbnail(jpeg_content)
        with open(os.path.join(THUMB_DIR, f"{image_id}.jpg"), "wb") as f:
            f.write(thumb_content)
        # Evict oldest full-res images if cache is too large
        with _cache_evict_lock:
            _evict_oldest_cached(CACHE_DIR, FULL_CACHE_MAX_BYTES)
        return content
    except Exception as e:
        print(f"Failed to cache image {image_id}: {e}")
        return content

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
                # Convert HEIC/HEIF to JPEG for browser compatibility
                if len(content) >= 12 and content[4:8] == b"ftyp" and content[8:12] in (b"heic", b"heix", b"hevc", b"mif1"):
                    try:
                        import pillow_heif
                        pillow_heif.register_heif_opener()
                        from PIL import Image as PILImg
                        pil_img = PILImg.open(io.BytesIO(content))
                        buf = io.BytesIO()
                        pil_img.save(buf, format="JPEG", quality=90)
                        content = buf.getvalue()
                        mime_type = "image/jpeg"
                    except Exception as heic_err:
                        print(f"[Proxy] HEIC conversion failed for {img.filename}: {heic_err}")
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
                        fid = img.source_folder_id
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


@app.get("/api/images/view/{image_id}")
def proxy_view(image_id: int):
    """
    Return a medium-res image (~1200px) for annotation/review views.
    Much faster than full-res proxy (~80-150KB vs 2-5MB).
    Perfect for annotation where pixel-perfect detail isn't needed.
    """
    # Check view cache first
    cached_content, cached_mime = get_cached_view(image_id)
    if cached_content:
        return Response(
            content=cached_content,
            media_type=cached_mime,
            headers={
                "Cache-Control": "public, max-age=604800",
                "X-Cache": "VIEW-HIT",
            }
        )

    # Check if full image is cached — generate view from it
    full_content, full_mime = get_cached_image(image_id)
    if full_content:
        view = _make_view_image(full_content)
        try:
            with open(os.path.join(VIEW_DIR, f"{image_id}.jpg"), "wb") as f:
                f.write(view)
        except Exception:
            pass
        return Response(
            content=view,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=604800",
                "X-Cache": "VIEW-GEN",
            }
        )

    # Neither cached — fetch from GCS, cache all sizes, return view
    db = SessionLocal()
    try:
        img = db.query(Image).filter(Image.id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")

        url = img.url or ""
        content = None

        if url.startswith('gs://'):
            try:
                from app.utils.gcs import download_to_bytes, parse_gs_uri
                _, blob_path = parse_gs_uri(url)
                content = download_to_bytes(blob_path)
            except Exception as e:
                print(f"[View] GCS fetch failed for {img.filename}: {e}")
                raise HTTPException(status_code=502, detail=f"GCS fetch failed")
        elif url.startswith('file://'):
            local_path = url.replace('file://', '')
            if not os.path.isabs(local_path):
                backend_dir = os.path.dirname(os.path.dirname(__file__))
                local_path = os.path.join(backend_dir, local_path)
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                with open(local_path, "rb") as f:
                    content = f.read()

        if not content:
            raise HTTPException(status_code=404, detail="Image not accessible")

        ext = os.path.splitext(img.filename)[1].lower()
        mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                     '.gif': 'image/gif', '.webp': 'image/webp'}.get(ext, 'image/jpeg')

        # Cache full + view + thumbnail
        cache_image(image_id, content, mime_type)

        # Return view-sized image
        view = _make_view_image(_to_jpeg(content, mime_type))
        return Response(
            content=view,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=604800",
                "X-Cache": "VIEW-MISS",
            }
        )
    finally:
        db.close()


@app.get("/api/images/thumb/{image_id}")
def proxy_thumbnail(image_id: int):
    """
    Return a small thumbnail (~400px) for gallery grid views.
    Much faster than the full proxy — typically 15-30KB vs 2-5MB.
    Auto-generates thumbnail on first request and caches it.
    """
    # Check thumbnail cache first
    cached_content, cached_mime = get_cached_thumbnail(image_id)
    if cached_content:
        return Response(
            content=cached_content,
            media_type=cached_mime,
            headers={
                "Cache-Control": "public, max-age=604800",
                "X-Cache": "THUMB-HIT",
            }
        )

    # Check if full image is cached — generate thumbnail from it
    full_content, full_mime = get_cached_image(image_id)
    if full_content:
        thumb = _make_thumbnail(full_content)
        # Save thumbnail for next time
        try:
            with open(os.path.join(THUMB_DIR, f"{image_id}.jpg"), "wb") as f:
                f.write(thumb)
        except Exception:
            pass
        return Response(
            content=thumb,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=604800",
                "X-Cache": "THUMB-GEN",
            }
        )

    # Neither cached — fetch from GCS, cache both, return thumbnail
    db = SessionLocal()
    try:
        img = db.query(Image).filter(Image.id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")

        url = img.url or ""
        content = None

        if url.startswith('gs://'):
            try:
                from app.utils.gcs import download_to_bytes, parse_gs_uri
                _, blob_path = parse_gs_uri(url)
                content = download_to_bytes(blob_path)
            except Exception as e:
                print(f"[Thumb] GCS fetch failed for {img.filename}: {e}")
                raise HTTPException(status_code=502, detail=f"GCS fetch failed")
        elif url.startswith('file://'):
            local_path = url.replace('file://', '')
            if not os.path.isabs(local_path):
                backend_dir = os.path.dirname(os.path.dirname(__file__))
                local_path = os.path.join(backend_dir, local_path)
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                with open(local_path, "rb") as f:
                    content = f.read()

        if not content:
            raise HTTPException(status_code=404, detail="Image not accessible")

        ext = os.path.splitext(img.filename)[1].lower()
        mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                     '.gif': 'image/gif', '.webp': 'image/webp'}.get(ext, 'image/jpeg')

        # Cache full image + thumbnail
        cache_image(image_id, content, mime_type)

        # Return thumbnail
        thumb = _make_thumbnail(_to_jpeg(content, mime_type))
        return Response(
            content=thumb,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=604800",
                "X-Cache": "THUMB-MISS",
            }
        )
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
            
            if folder and folder in ("input", "annotated") and img.source_folder_id:
                blob_path = build_gcs_path(img.source_folder_id, img.filename, folder)
            else:
                stage = img.gcs_folder or "input"
                blob_path = build_gcs_path(img.source_folder_id or "", img.filename, stage)
            
            try:
                signed = sign(blob_path, expiration_seconds=3600)
                # Verify the signed URL is actually valid by checking if SA has access
                # If the service account lacks GCS permissions, signed URLs return 403
                # In that case, fall back to the proxy endpoint which uses ADC
                return {
                    "signed_url": signed,
                    "expires_in": 3600,
                    "stage": folder or img.gcs_folder or "input",
                    "image_id": image_id,
                }
            except Exception as e:
                # Signed URL generation failed — fall back to proxy
                print(f"[SignedURL] Signing failed for image {image_id}, using proxy: {e}")
                folder_param = f"&folder={folder}" if folder else ""
                return {
                    "signed_url": f"/api/images/proxy/{image_id}?t={int(datetime.datetime.now().timestamp())}{folder_param}",
                    "expires_in": 86400,
                    "stage": folder or img.gcs_folder or "input",
                    "image_id": image_id,
                }
        else:
            return {
                "signed_url": f"/api/images/proxy/{image_id}?t={int(datetime.datetime.now().timestamp())}",
                "expires_in": 86400,
                "stage": "legacy",
                "image_id": image_id,
            }
    finally:
        db.close()
