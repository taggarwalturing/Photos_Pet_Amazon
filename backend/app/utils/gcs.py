"""
Google Cloud Storage utility for uploading, copying, signing, and deleting
images in the three-folder bucket layout:

  gs://{bucket}/input/{folder_id}/{filename}       — originals from Drive
  gs://{bucket}/annotated/{folder_id}/{filename}    — after annotator blur
  gs://{bucket}/final/{folder_id}/{filename}        — after admin approval

Authentication uses Application Default Credentials (ADC).
Run `gcloud auth application-default login` on the server to authenticate.
"""

import os
import datetime
from pathlib import Path
from functools import lru_cache

from google.cloud import storage
import google.auth
from google.auth.transport.requests import Request


VALID_STAGES = ("input", "annotated", "final")


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


def _client() -> storage.Client:
    credentials, project = _adc_credentials()
    return storage.Client(
        project=os.getenv("GCS_PROJECT_ID", project or "turing-gpt"),
        credentials=credentials,
    )


def _bucket() -> storage.Bucket:
    bucket_name = os.getenv("GCS_BUCKET_NAME", "amazon-photo-pets")
    return _client().bucket(bucket_name)


def gcs_path(folder_id: str, filename: str, stage: str = "input") -> str:
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage '{stage}', must be one of {VALID_STAGES}")
    return f"{stage}/{folder_id}/{filename}"


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


def upload_directory(local_dir: str, gcs_prefix: str, extensions: set = None) -> list[str]:
    """
    Batch-upload all files in a local directory to GCS under the given prefix.
    Returns list of gs:// URIs for uploaded files.
    """
    if extensions is None:
        extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
    uploaded = []
    bucket = _bucket()
    for fpath in Path(local_dir).iterdir():
        if fpath.is_file() and fpath.suffix.lower() in extensions:
            dest = f"{gcs_prefix}/{fpath.name}"
            blob = bucket.blob(dest)
            blob.upload_from_filename(str(fpath))
            uploaded.append(f"gs://{bucket.name}/{dest}")
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


def parse_gs_uri(gs_uri: str) -> tuple[str, str]:
    """Parse 'gs://bucket/path/to/blob' into (bucket_name, blob_path)."""
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"Not a gs:// URI: {gs_uri}")
    without_scheme = gs_uri[5:]
    bucket_name, _, blob_path = without_scheme.partition("/")
    return bucket_name, blob_path
