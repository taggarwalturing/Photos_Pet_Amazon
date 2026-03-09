"""
Google Cloud Storage utility for uploading, copying, signing, and deleting
images in the bucket layout:

  gs://{bucket}/input/{folder_id}/{filename}                — raw originals (added manually)
  gs://{bucket}/annotated/{folder_id}/clean/{filename}      — clean images (no blur)
  gs://{bucket}/annotated/{folder_id}/blur/{filename}       — blurred images (by pipeline or manual)

Authentication uses Application Default Credentials (ADC).
Run `gcloud auth application-default login` on the server to authenticate.
"""

import os
import datetime
from pathlib import Path
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.cloud import storage
import google.auth
from google.auth.transport.requests import Request

# Number of parallel upload threads (I/O bound → threads work well)
_MAX_UPLOAD_WORKERS = int(os.getenv("GCS_UPLOAD_WORKERS", "8"))


# ── Load backend/.env so GCS_BUCKET_NAME / GCS_PROJECT_ID are available ──
def _load_env():
    """Read backend/.env into os.environ (only missing keys)."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip()
                    if key not in os.environ:
                        os.environ[key] = value

_load_env()


VALID_STAGES = ("input", "clean", "blur")


def _service_account_path() -> str | None:
    """Return SA key path if it exists (used only for signing URLs)."""
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "turing-genai-ws-58339643dd3f.json")
    if os.path.isabs(sa_file) and os.path.exists(sa_file):
        return sa_file
    backend_dir = Path(__file__).resolve().parent.parent.parent
    candidates = [
        backend_dir / sa_file,
        backend_dir / "master_pipeline" / sa_file,
        Path(sa_file),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


@lru_cache(maxsize=1)
def _adc_credentials():
    """Get Application Default Credentials (user account via gcloud auth)."""
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return credentials, project


@lru_cache(maxsize=1)
def _client() -> storage.Client:
    credentials, project = _adc_credentials()
    return storage.Client(
        project=os.getenv("GCS_PROJECT_ID", project or "turing-gpt"),
        credentials=credentials,
    )


@lru_cache(maxsize=1)
def _bucket() -> storage.Bucket:
    bucket_name = os.getenv("GCS_BUCKET_NAME", "amazon-photo-pets")
    return _client().bucket(bucket_name)


def gcs_path(folder_id: str, filename: str, stage: str = "input") -> str:
    """
    Build the GCS blob path for an image.

    Stages:
      - ``input``  → ``input/{folder_id}/{filename}``
      - ``clean``  → ``annotated/{folder_id}/clean/{filename}``
      - ``blur``   → ``annotated/{folder_id}/blur/{filename}``
    """
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage '{stage}', must be one of {VALID_STAGES}")
    if stage == "input":
        return f"input/{folder_id}/{filename}"
    # clean or blur → under annotated/
    return f"annotated/{folder_id}/{stage}/{filename}"


def upload_file(local_path: str, dest_gcs_path: str, content_type: str = None) -> str:
    """Upload a local file to GCS. Returns the gs:// URI."""
    bucket = _bucket()
    blob = bucket.blob(dest_gcs_path)
    if content_type:
        blob.content_type = content_type
    blob.upload_from_filename(local_path)
    return f"gs://{bucket.name}/{dest_gcs_path}"


def upload_bytes(data: bytes, dest_gcs_path: str, content_type: str = "image/jpeg") -> str:
    """Upload raw bytes to GCS. Returns the gs:// URI."""
    bucket = _bucket()
    blob = bucket.blob(dest_gcs_path)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{bucket.name}/{dest_gcs_path}"


def upload_directory(local_dir: str, gcs_prefix: str, extensions: set = None,
                     max_workers: int = None) -> list[str]:
    """
    Parallel-upload all files in a local directory to GCS under the given prefix.
    Returns list of gs:// URIs for uploaded files.
    """
    if extensions is None:
        extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}

    files_to_upload = [
        (str(fpath), f"{gcs_prefix}/{fpath.name}")
        for fpath in Path(local_dir).iterdir()
        if fpath.is_file() and fpath.suffix.lower() in extensions
    ]
    if not files_to_upload:
        return []

    return upload_files_parallel(files_to_upload, max_workers=max_workers)


def upload_files_parallel(
    file_dest_pairs: list[tuple[str, str]],
    max_workers: int = None,
) -> list[str]:
    """
    Upload multiple local files to GCS in parallel.

    Args:
        file_dest_pairs: list of (local_path, gcs_dest_path) tuples
        max_workers: thread count (defaults to GCS_UPLOAD_WORKERS env, then 8)

    Returns:
        list of gs:// URIs that were successfully uploaded
    """
    if not file_dest_pairs:
        return []

    workers = max_workers or _MAX_UPLOAD_WORKERS
    bucket = _bucket()
    bucket_name = bucket.name
    uploaded: list[str] = []

    def _upload_one(pair):
        local_path, dest_path = pair
        blob = bucket.blob(dest_path)
        blob.upload_from_filename(local_path)
        return f"gs://{bucket_name}/{dest_path}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_upload_one, p): p for p in file_dest_pairs}
        for fut in as_completed(futures):
            try:
                uploaded.append(fut.result())
            except Exception as exc:
                local, dest = futures[fut]
                print(f"❌ GCS upload failed {Path(local).name} → {dest}: {exc}")

    return uploaded


def copy_blob(src_gcs_path: str, dst_gcs_path: str) -> str:
    """Server-side copy within the same bucket. Returns the gs:// URI of the copy."""
    bucket = _bucket()
    src_blob = bucket.blob(src_gcs_path)
    bucket.copy_blob(src_blob, bucket, dst_gcs_path)
    return f"gs://{bucket.name}/{dst_gcs_path}"


def delete_blob(blob_gcs_path: str) -> bool:
    """Delete a blob. Returns True if deleted, False if it didn't exist."""
    bucket = _bucket()
    blob = bucket.blob(blob_gcs_path)
    if blob.exists():
        blob.delete()
        return True
    return False


def download_to_bytes(blob_gcs_path: str) -> bytes:
    """Download a GCS blob into memory."""
    bucket = _bucket()
    blob = bucket.blob(blob_gcs_path)
    return blob.download_as_bytes()


def _signing_credentials():
    """
    Get credentials capable of signing URLs.
    ADC user credentials can't sign directly, so we try:
      1. Service account JSON key (if present) — can sign locally.
      2. IAM signBlob API via ADC — works if user has iam.serviceAccounts.signBlob permission.
    """
    sa_path = _service_account_path()
    if sa_path:
        from google.oauth2 import service_account as sa_mod
        return sa_mod.Credentials.from_service_account_file(
            sa_path, scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    return None


def generate_signed_url(blob_gcs_path: str, expiration_seconds: int = 3600) -> str:
    """Generate a V4 signed URL for direct browser access."""
    bucket = _bucket()
    blob = bucket.blob(blob_gcs_path)
    
    signing_creds = _signing_credentials()
    if signing_creds:
        return blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=expiration_seconds),
            method="GET",
            credentials=signing_creds,
        )
    
    # Fallback: use the ADC credentials with IAM-based signing
    credentials, _ = _adc_credentials()
    credentials.refresh(Request())
    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=expiration_seconds),
        method="GET",
        credentials=credentials,
        service_account_email=credentials.service_account_email if hasattr(credentials, 'service_account_email') else None,
    )


def blob_exists(blob_gcs_path: str) -> bool:
    bucket = _bucket()
    return bucket.blob(blob_gcs_path).exists()


def list_blobs(prefix: str, delimiter: str = None) -> list[str]:
    """
    List blob names under a given prefix.

    Args:
        prefix: GCS prefix to list (e.g. "input/folder123/")
        delimiter: If set (typically "/"), returns only "files" at this level,
                   not recursively.

    Returns:
        List of full blob names (e.g. ["input/folder123/img1.jpg", ...])
    """
    bucket = _bucket()
    blobs = bucket.list_blobs(prefix=prefix, delimiter=delimiter)
    return [b.name for b in blobs]


def list_prefixes(prefix: str) -> list[str]:
    """
    List "sub-folder" prefixes under a given prefix.

    For example, list_prefixes("input/") returns
    ["input/folder_A/", "input/folder_B/", ...].
    """
    bucket = _bucket()
    blobs_iter = bucket.list_blobs(prefix=prefix, delimiter="/")
    # We must consume the page iterator to populate prefixes
    _ = list(blobs_iter)
    return list(blobs_iter.prefixes)


def download_blob_to_file(blob_gcs_path: str, local_path: str) -> str:
    """Download a blob to a local file. Returns the local path."""
    bucket = _bucket()
    blob = bucket.blob(blob_gcs_path)
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(local_path)
    return local_path


def parse_gs_uri(gs_uri: str) -> tuple[str, str]:
    """Parse 'gs://bucket/path/to/blob' into (bucket_name, blob_path)."""
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"Not a gs:// URI: {gs_uri}")
    without_scheme = gs_uri[5:]
    bucket_name, _, blob_path = without_scheme.partition("/")
    return bucket_name, blob_path
