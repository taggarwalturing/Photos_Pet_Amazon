"""
Annotation Validation via VLM
==============================
Admin endpoint that sends human-annotated images to Gemini VLM
to verify if the annotations are aligned with the image content.
"""

import json
import base64
import io
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests as http_requests
from PIL import Image as PILImage
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.database import get_db, SessionLocal
from app.dependencies import require_admin
from app.models.user import User
from app.models.image import Image as ImageModel
from app.utils.categories import get_categories
from app.utils.gcs import (
    gcs_path as build_gcs_path,
    download_to_bytes as gcs_download,
)

router = APIRouter(prefix="/admin/validation", tags=["Annotation Validation"])

# ─── Constants ────────────────────────────────────────────────
CATEGORIES = ["lighting", "viewpoint", "environment", "occlusion", "activity", "multipet"]

CATEGORY_LABELS = {
    "lighting": "Lighting Variation",
    "viewpoint": "Angle & Perspective Variation",
    "environment": "Environmental Context Variation",
    "occlusion": "Occlusion & Partial Visibility",
    "activity": "Activity & Motion",
    "multipet": "Multi-Pet Disambiguation",
}

# ─── In-memory validation state ──────────────────────────────
validation_status = {
    "is_running": False,
    "processed": 0,
    "total": 0,
    "started_at": None,
    "completed_at": None,
    "results": [],        # [{image_id, filename, aligned, contradictions: [{category, human_label, vlm_label, reason}]}]
    "errors": [],
}

_stop_event = threading.Event()


# ─── Helpers ──────────────────────────────────────────────────

def _read_env():
    """Read backend/.env fresh (same as arbiter)."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    result = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def _load_config():
    """Load API config from .env."""
    env = _read_env()
    return {
        "api_url": env.get("TURING_API_URL", "https://kong.turing.com/api/v2/chat"),
        "model": env.get("GEMINI_MODEL", "gemini-2.5-pro"),
        "provider": env.get("GEMINI_PROVIDER", "google"),
        "timeout": int(env.get("TIMEOUT_SECONDS", "120")),
    }


def _encode_image(image_bytes: bytes, max_size_mb: float = 4.0) -> tuple:
    """Encode image bytes to base64, resizing if needed."""
    data = image_bytes
    if len(data) > max_size_mb * 1024 * 1024:
        img = PILImage.open(io.BytesIO(data))
        img.thumbnail((1024, 1024), PILImage.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        data = buf.getvalue()
    return base64.b64encode(data).decode("utf-8"), "image/jpeg"


def _get_image_bytes(image: ImageModel) -> bytes:
    """Download image from GCS."""
    folder_id = image.source_folder_id
    fname = image.filename
    if folder_id and fname:
        for stage in (image.gcs_folder or "clean", "input"):
            try:
                blob_path = build_gcs_path(folder_id, fname, stage)
                return gcs_download(blob_path)
            except Exception:
                continue
    raise ValueError(f"Could not download image {fname}")


def _build_validation_prompt(annotations: dict) -> str:
    """Build a VLM prompt that asks Gemini to verify human annotations."""
    categories_data = get_categories()
    cat_lookup = {c["key"]: c for c in categories_data}

    annotation_lines = []
    for cat_key in CATEGORIES:
        cat = cat_lookup.get(cat_key)
        if not cat:
            continue
        ann = annotations.get(cat_key, {})
        labels = ann.get("selected_labels", [])
        if not labels:
            # Try to resolve from option IDs
            ids = ann.get("selected_option_ids", [])
            for opt in cat.get("options", []):
                if opt["id"] in ids:
                    labels.append(opt["label"])
        if labels:
            annotation_lines.append(f"  - {cat['name']}: {', '.join(labels)}")
        else:
            annotation_lines.append(f"  - {cat['name']}: (no selection)")

    # Build all valid options for each category
    options_lines = []
    for cat_key in CATEGORIES:
        cat = cat_lookup.get(cat_key)
        if not cat:
            continue
        opts = [o["label"] for o in cat.get("options", [])]
        options_lines.append(f"  - {cat['name']}: {', '.join(opts)}")

    prompt = f"""You are a pet image annotation validator. You will be shown a pet image along with human annotations.

Your task: For each category, determine if the human annotation is CORRECT or INCORRECT based on what you observe in the image.

## Categories and Valid Options:
{chr(10).join(options_lines)}

## Human Annotations:
{chr(10).join(annotation_lines)}

## Instructions:
1. Look at the image carefully.
2. For EACH category, compare the human annotation with what you actually see.
3. Return your assessment as a JSON object with this EXACT structure:

```json
{{
  "overall_aligned": true/false,
  "categories": {{
    "lighting": {{
      "aligned": true/false,
      "human_label": "the human annotation",
      "vlm_suggestion": "what you think it should be",
      "reason": "brief explanation if misaligned"
    }},
    "viewpoint": {{ ... }},
    "environment": {{ ... }},
    "occlusion": {{ ... }},
    "activity": {{ ... }},
    "multipet": {{ ... }}
  }}
}}
```

Return ONLY valid JSON. No markdown, no explanation outside the JSON.
"""
    return prompt


def _call_gemini(api_url: str, model: str, provider: str, prompt: str,
                 image_b64: str, mime: str, timeout: int) -> dict:
    """Call Gemini VLM with image and prompt. Uses key pool."""
    from arbiter_classifier.key_pool import key_pool as _kp

    payload = {
        "model": model,
        "provider": provider,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}}
            ]
        }],
        "temperature": 0,
        "max_tokens": 1500,
    }

    last_error = None
    for _attempt in range(3):
        headers = _kp.get_headers()
        if headers is None:
            return {"error": "All API keys exhausted"}
        try:
            resp = http_requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in [200, 201]:
                _kp.report_success(headers)
                text = resp.json()["choices"][0]["message"]["content"]
                # Strip markdown code fences if present
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                return json.loads(text.strip())
            else:
                _kp.report_error(headers, resp.status_code)
                last_error = f"API returned {resp.status_code}: {resp.text[:200]}"
                if resp.status_code in [402, 403, 429]:
                    continue
                return {"error": last_error}
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse VLM response as JSON: {str(e)[:200]}"}
        except Exception as e:
            last_error = str(e)
            return {"error": last_error}

    return {"error": last_error or "All retries exhausted"}


# ─── Background validation runner ────────────────────────────

def _run_validation_background(image_ids: List[int]):
    """Run validation on a list of image IDs in the background."""
    global validation_status
    _stop_event.clear()

    cfg = _load_config()
    validation_status["is_running"] = True
    validation_status["processed"] = 0
    validation_status["total"] = len(image_ids)
    validation_status["started_at"] = datetime.now().isoformat()
    validation_status["completed_at"] = None
    validation_status["results"] = []
    validation_status["errors"] = []

    db = SessionLocal()
    try:
        for idx, img_id in enumerate(image_ids):
            if _stop_event.is_set():
                break

            image = db.query(ImageModel).filter(ImageModel.id == img_id).first()
            if not image or not image.annotations:
                validation_status["errors"].append(
                    f"Image {img_id}: no annotations found"
                )
                validation_status["processed"] = idx + 1
                continue

            try:
                # 1. Get image bytes
                img_bytes = _get_image_bytes(image)
                image_b64, mime = _encode_image(img_bytes)

                # 2. Build prompt with human annotations
                prompt = _build_validation_prompt(image.annotations)

                # 3. Call Gemini
                result = _call_gemini(
                    cfg["api_url"], cfg["model"], cfg["provider"],
                    prompt, image_b64, mime, cfg["timeout"]
                )

                if "error" in result:
                    validation_status["errors"].append(
                        f"{image.filename}: {result['error'][:200]}"
                    )
                    validation_status["processed"] = idx + 1
                    continue

                # 4. Parse result
                overall_aligned = result.get("overall_aligned", True)
                cats = result.get("categories", {})

                contradictions = []
                for cat_key, cat_result in cats.items():
                    if cat_key not in CATEGORIES:
                        continue
                    if not cat_result.get("aligned", True):
                        contradictions.append({
                            "category": CATEGORY_LABELS.get(cat_key, cat_key),
                            "category_key": cat_key,
                            "human_label": cat_result.get("human_label", ""),
                            "vlm_suggestion": cat_result.get("vlm_suggestion", ""),
                            "reason": cat_result.get("reason", ""),
                        })

                # If VLM found contradictions, override overall_aligned
                if contradictions:
                    overall_aligned = False

                # Get annotator info
                annotator_name = ""
                if image.annotated_by:
                    annotator = db.query(User).filter(User.id == image.annotated_by).first()
                    if annotator:
                        annotator_name = annotator.username

                result_entry = {
                    "image_id": image.id,
                    "filename": image.filename,
                    "source_folder_id": image.source_folder_id or "",
                    "annotator": annotator_name,
                    "aligned": overall_aligned,
                    "contradictions": contradictions,
                    "category_details": cats,
                }
                validation_status["results"].append(result_entry)

                # ── Persist to DB ──
                image.vlm_validation = {
                    "aligned": overall_aligned,
                    "contradictions": contradictions,
                    "category_details": cats,
                }
                image.vlm_validated_at = datetime.now()
                db.commit()

            except Exception as e:
                validation_status["errors"].append(
                    f"{image.filename}: {str(e)[:200]}"
                )

            validation_status["processed"] = idx + 1
            time.sleep(0.2)  # Small delay to avoid overwhelming the API

    except Exception as e:
        validation_status["errors"].append(f"Fatal error: {str(e)[:300]}")
    finally:
        db.close()
        validation_status["is_running"] = False
        validation_status["completed_at"] = datetime.now().isoformat()


# ─── API Endpoints ────────────────────────────────────────────

@router.get("/stats")
def get_validation_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get counts of annotated images eligible for validation."""
    total_annotated = db.query(sa_func.count(ImageModel.id)).filter(
        ImageModel.annotation_status == "completed",
        ImageModel.is_duplicate == False,  # noqa
    ).scalar()

    total_approved = db.query(sa_func.count(ImageModel.id)).filter(
        ImageModel.annotation_status == "completed",
        ImageModel.review_status == "approved",
        ImageModel.is_duplicate == False,  # noqa
    ).scalar()

    total_pending_review = db.query(sa_func.count(ImageModel.id)).filter(
        ImageModel.annotation_status == "completed",
        ImageModel.review_status == "pending",
        ImageModel.is_duplicate == False,  # noqa
    ).scalar()

    # Get folder breakdown
    folders = db.query(
        ImageModel.source_folder_id,
        sa_func.count(ImageModel.id),
    ).filter(
        ImageModel.annotation_status == "completed",
        ImageModel.is_duplicate == False,  # noqa
    ).group_by(ImageModel.source_folder_id).all()

    from app.models.drive_folder import DriveFolder
    folder_names = {f.folder_id: f.folder_name or f.folder_id[:16]
                    for f in db.query(DriveFolder).all()}

    folder_list = []
    for fid, count in folders:
        folder_list.append({
            "folder_id": fid or "__unknown__",
            "folder_name": folder_names.get(fid, fid[:16] if fid else "Unknown"),
            "annotated_count": count,
        })

    # Annotator breakdown
    annotators = db.query(
        User.id, User.username,
        sa_func.count(ImageModel.id),
    ).join(ImageModel, ImageModel.annotated_by == User.id).filter(
        ImageModel.annotation_status == "completed",
        ImageModel.is_duplicate == False,  # noqa
    ).group_by(User.id, User.username).all()

    annotator_list = [{"id": uid, "username": uname, "count": cnt}
                      for uid, uname, cnt in annotators]

    # Already validated count
    total_validated = db.query(sa_func.count(ImageModel.id)).filter(
        ImageModel.vlm_validated_at.isnot(None),
        ImageModel.is_duplicate == False,  # noqa
    ).scalar()

    return {
        "total_annotated": total_annotated,
        "total_approved": total_approved,
        "total_pending_review": total_pending_review,
        "total_validated": total_validated,
        "folders": sorted(folder_list, key=lambda x: x["folder_name"]),
        "annotators": sorted(annotator_list, key=lambda x: x["username"]),
    }


@router.post("/run")
def run_validation(
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Start validation of human annotations using Gemini VLM.

    Payload:
      - scope: "all" | "folder" | "annotator" | "custom"
      - folder_ids: [str] (if scope == "folder")
      - annotator_id: int (if scope == "annotator")
      - image_ids: [int] (if scope == "custom")
      - revalidate: bool (default false) — if true, re-run even on already-validated images
    """
    global validation_status

    if validation_status["is_running"]:
        raise HTTPException(status_code=409, detail="Validation is already running")

    scope = payload.get("scope", "all")
    revalidate = payload.get("revalidate", False)

    # Build query for annotated images
    query = db.query(ImageModel.id).filter(
        ImageModel.annotation_status == "completed",
        ImageModel.is_duplicate == False,  # noqa
    )

    # Skip already-validated images unless revalidate is requested
    if not revalidate:
        query = query.filter(ImageModel.vlm_validated_at.is_(None))

    if scope == "folder":
        folder_ids = payload.get("folder_ids", [])
        if folder_ids:
            query = query.filter(ImageModel.source_folder_id.in_(folder_ids))
    elif scope == "annotator":
        annotator_id = payload.get("annotator_id")
        if annotator_id:
            query = query.filter(ImageModel.annotated_by == annotator_id)
    elif scope == "custom":
        image_ids = payload.get("image_ids", [])
        if image_ids:
            query = query.filter(ImageModel.id.in_(image_ids))

    image_ids = [r[0] for r in query.order_by(ImageModel.id).all()]

    if not image_ids:
        raise HTTPException(status_code=400, detail="No unvalidated images found for the given scope. Use 'Re-validate' to run again on already-validated images.")

    # Start background thread
    thread = threading.Thread(target=_run_validation_background, args=(image_ids,), daemon=True)
    thread.start()

    return {
        "message": f"Validation started for {len(image_ids)} images",
        "total": len(image_ids),
    }


@router.post("/stop")
def stop_validation(
    _admin: User = Depends(require_admin),
):
    """Stop the running validation."""
    _stop_event.set()
    return {"message": "Stop signal sent"}


@router.get("/status")
def get_validation_status(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get current validation status and results."""
    results = validation_status.get("results", [])

    # If no in-memory results and not running, load from DB
    if not results and not validation_status["is_running"]:
        db_images = db.query(ImageModel).filter(
            ImageModel.vlm_validated_at.isnot(None),
        ).order_by(ImageModel.id).all()

        for img in db_images:
            val = img.vlm_validation or {}
            annotator_name = ""
            if img.annotated_by:
                ann_user = db.query(User).filter(User.id == img.annotated_by).first()
                if ann_user:
                    annotator_name = ann_user.username
            results.append({
                "image_id": img.id,
                "filename": img.filename,
                "source_folder_id": img.source_folder_id or "",
                "annotator": annotator_name,
                "aligned": val.get("aligned", True),
                "contradictions": val.get("contradictions", []),
                "category_details": val.get("category_details", {}),
            })

    # Compute summary
    total = len(results)
    aligned_count = sum(1 for r in results if r.get("aligned"))
    misaligned_count = total - aligned_count

    # Category-wise contradiction counts
    category_counts = {cat: 0 for cat in CATEGORIES}
    for r in results:
        for c in r.get("contradictions", []):
            cat_key = c.get("category_key", "")
            if cat_key in category_counts:
                category_counts[cat_key] += 1

    return {
        "is_running": validation_status["is_running"],
        "processed": validation_status["processed"],
        "total": validation_status["total"],
        "started_at": validation_status["started_at"],
        "completed_at": validation_status["completed_at"],
        "summary": {
            "total_validated": total,
            "aligned": aligned_count,
            "misaligned": misaligned_count,
            "accuracy_pct": round(aligned_count / total * 100, 1) if total > 0 else 0,
            "category_contradictions": category_counts,
        },
        "results": results,
        "errors": validation_status.get("errors", []),
    }


@router.post("/clear")
def clear_validation_results(
    _admin: User = Depends(require_admin),
):
    """Clear previous validation results."""
    global validation_status
    if validation_status["is_running"]:
        raise HTTPException(status_code=409, detail="Cannot clear while validation is running")

    validation_status = {
        "is_running": False,
        "processed": 0,
        "total": 0,
        "started_at": None,
        "completed_at": None,
        "results": [],
        "errors": [],
    }
    return {"message": "Results cleared"}
