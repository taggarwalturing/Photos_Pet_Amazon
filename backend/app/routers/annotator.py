"""
Annotator router — simplified for 3-table schema.

Tables used : users, images, arbiter_predictions
Categories  : static JSON file (categories.json)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
from threading import Lock as ThreadLock
from pydantic import BaseModel
import os

from app.database import get_db
from app.dependencies import require_annotator, get_current_user
from app.models.user import User
from app.models.image import Image
from app.utils.categories import (
    get_categories,
    get_option_by_id,
    arbiter_label_to_option_label,
    enrich_annotations_with_labels,
)
from app.utils.blur import blur_image_regions


# ── In-memory soft-lock store ──────────────────────────────────────
# Tracks which annotator currently has an image open.
# Soft locks auto-expire after SOFT_LOCK_TTL seconds if not refreshed.
SOFT_LOCK_TTL = 30  # seconds — heartbeat should fire every 10s
_soft_locks: dict[int, dict] = {}  # image_id → {"user_id": int, "username": str, "ts": datetime}
_soft_lock_mu = ThreadLock()


def _acquire_soft_lock(image_id: int, user_id: int, username: str) -> bool:
    """Try to acquire a soft lock. Returns True if acquired or already held by this user."""
    now = datetime.now(timezone.utc)
    with _soft_lock_mu:
        existing = _soft_locks.get(image_id)
        if existing and existing["user_id"] != user_id:
            age = (now - existing["ts"]).total_seconds()
            if age < SOFT_LOCK_TTL:
                return False  # still held by someone else
        _soft_locks[image_id] = {"user_id": user_id, "username": username, "ts": now}
        return True


def _release_soft_lock(image_id: int, user_id: int):
    """Release a soft lock if held by this user."""
    with _soft_lock_mu:
        existing = _soft_locks.get(image_id)
        if existing and existing["user_id"] == user_id:
            del _soft_locks[image_id]


def _refresh_soft_lock(image_id: int, user_id: int) -> bool:
    """Refresh timestamp on a soft lock. Returns False if not held by this user."""
    now = datetime.now(timezone.utc)
    with _soft_lock_mu:
        existing = _soft_locks.get(image_id)
        if existing and existing["user_id"] == user_id:
            existing["ts"] = now
            return True
        return False


def _get_soft_lock_holder(image_id: int, exclude_user_id: int) -> Optional[dict]:
    """Return soft-lock holder info if held by someone other than exclude_user_id."""
    now = datetime.now(timezone.utc)
    with _soft_lock_mu:
        existing = _soft_locks.get(image_id)
        if existing and existing["user_id"] != exclude_user_id:
            age = (now - existing["ts"]).total_seconds()
            if age < SOFT_LOCK_TTL:
                return existing
            else:
                del _soft_locks[image_id]
    return None


def _get_all_soft_locks(exclude_user_id: int) -> dict[int, dict]:
    """Return all active soft locks held by users other than exclude_user_id."""
    now = datetime.now(timezone.utc)
    result = {}
    stale = []
    with _soft_lock_mu:
        for img_id, info in _soft_locks.items():
            age = (now - info["ts"]).total_seconds()
            if age >= SOFT_LOCK_TTL:
                stale.append(img_id)
            elif info["user_id"] != exclude_user_id:
                result[img_id] = info
        for img_id in stale:
            del _soft_locks[img_id]
    return result


# ── Helpers ────────────────────────────────────────────────────────

def _build_option_id_to_label() -> dict[int, str]:
    """Build a mapping from option ID → label text across all categories."""
    result = {}
    for cat in get_categories():
        for opt in cat.get("options", []):
            result[opt["id"]] = opt["label"]
    return result


def _is_hard_locked(image: Image, user_id: int) -> bool:
    """
    Check if an image is hard-locked by a different annotator.
    Once an image has been annotated by someone, it's permanently locked
    for all OTHER annotators — regardless of review_status or rework.
    """
    return (
        image.annotated_by is not None
        and image.annotated_by != user_id
    )


router = APIRouter(prefix="/annotator", tags=["Annotator"])


# ── Categories (static JSON) ──────────────────────────────────────

@router.get("/categories")
def list_categories(user: User = Depends(require_annotator)):
    """Return all categories with options from static JSON."""
    return {"categories": get_categories()}


# ── Image Listing ────────────────────────────────────────────────

@router.get("/images")
def list_images_for_annotator(
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, le=10000),  # 0 = return all
    filter_status: Optional[str] = Query(None),  # all, pending, completed
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    List images with annotation status for the annotator.
    Categories come from static JSON; annotations from Image.annotations JSON.
    """
    categories = get_categories()
    option_id_to_label = _build_option_id_to_label()

    # Get all non-duplicate, non-improper images (ordered by ID)
    all_images = (
        db.query(Image)
        .filter(Image.is_duplicate == False)  # noqa: E712
        .order_by(Image.id)
        .all()
    )
    
    # Get all active soft locks
    active_soft_locks = _get_all_soft_locks(exclude_user_id=user.id)

    images_data = []
    for img in all_images:
        annotations = img.annotations or {}
        arbiter_labels = img.arbiter_labels or {}

        # Determine per-category status and labels
        category_status = {}
        category_labels = {}
        category_label_source = {}

        for cat in categories:
            cat_key = cat["key"]
            cat_ann = annotations.get(cat_key, {})
            selected_ids = cat_ann.get("selected_option_ids", [])

            if selected_ids:
                # Human annotation exists
                category_status[cat_key] = "completed"
                category_labels[cat_key] = [
                    option_id_to_label.get(oid, f"option_{oid}") for oid in selected_ids
                ]
                category_label_source[cat_key] = "human"
            else:
                category_status[cat_key] = "pending"
                # Try AI prediction from arbiter_labels
                if cat_key in arbiter_labels:
                    pred_data = arbiter_labels[cat_key]
                    # Use stored label directly if available
                    opt_label = pred_data.get("label") if isinstance(pred_data, dict) else None
                    if not opt_label:
                        pred = (
                            pred_data.get("final") or pred_data.get("key")
                            if isinstance(pred_data, dict)
                            else str(pred_data) if pred_data else None
                        )
                        if pred:
                            opt_label = arbiter_label_to_option_label(pred)
                    if opt_label:
                        category_labels[cat_key] = [opt_label]
                        category_label_source[cat_key] = "ai"
                        continue
                category_labels[cat_key] = []

        # Overall annotation status
        statuses = list(category_status.values())
        if img.annotation_status == "completed" or all(s == "completed" for s in statuses):
            overall_status = "completed"
        elif any(s == "completed" for s in statuses):
            overall_status = "partial"
        else:
            overall_status = "pending"
        
        # Apply filter
        if filter_status == "pending" and overall_status != "pending":
            continue
        if filter_status == "completed" and overall_status != "completed":
            continue
        
        # Hard lock — another annotator already submitted annotations
        is_hard = _is_hard_locked(img, user.id)

        # Soft lock — another annotator currently has image open
        soft_holder = active_soft_locks.get(img.id)
        is_soft = soft_holder is not None

        lock_type = None
        held_by = ""
        if is_hard:
            lock_type = "completed"
        elif is_soft:
            lock_type = "in_progress"
            held_by = soft_holder.get("username", "")

        is_locked = is_hard or is_soft
        # Rework is only relevant to the original annotator
        has_rework = (
            img.review_status == "rework_requested"
            and img.annotated_by == user.id
        )
        
        # For other annotators: mask review details — they just see "completed"
        is_owner = (img.annotated_by == user.id)
        visible_review_status = img.review_status if is_owner else (
            "completed" if img.annotated_by else img.review_status
        )
        visible_annotation_status = img.annotation_status or "pending"
        if is_hard and not is_owner:
            visible_annotation_status = "completed"
        
        images_data.append({
            "id": img.id,
            "filename": img.filename,
            "url": img.url,
            "source_folder_id": img.source_folder_id,
            "annotation_status": visible_annotation_status,
            "review_status": visible_review_status,
            "category_status": category_status,
            "category_labels": category_labels,
            "category_label_source": category_label_source,
            "overall_status": "locked" if is_locked else overall_status,
            "completed_count": sum(1 for s in statuses if s == "completed"),
            "total_categories": len(categories),
            "is_improper": img.is_improper or False,
            "improper_reason": img.improper_reason,
            "has_rework": has_rework,
            "has_ai_labels": bool(arbiter_labels),
            "locked_by_other": is_locked,
            "lock_type": lock_type,       # "completed" | "in_progress" | null
            "held_by": held_by,           # username of soft-lock holder
        })
    
    # Paginate
    total = len(images_data)
    if page_size == 0:
        paginated = images_data
    else:
        start = (page - 1) * page_size
        paginated = images_data[start : start + page_size]
    
    return {
        "images": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "categories": categories,
        "assigned_categories": categories,  # alias for frontend compat
    }


# ── Lock Endpoints ────────────────────────────────────────────────

@router.get("/images/{image_id}/lock-status")
def check_image_lock_status(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Lightweight check: is this image locked by another annotator?"""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Hard lock
    if _is_hard_locked(image, user.id):
        return {"image_id": image_id, "locked_by_other": True, "lock_type": "completed"}

    # Soft lock
    holder = _get_soft_lock_holder(image_id, exclude_user_id=user.id)
    if holder:
        return {
            "image_id": image_id,
            "locked_by_other": True,
            "lock_type": "in_progress",
            "held_by": holder.get("username", ""),
        }

    return {"image_id": image_id, "locked_by_other": False, "lock_type": None}


@router.post("/images/{image_id}/acquire-lock")
async def acquire_image_lock(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Acquire a soft lock when annotator opens an image. Broadcasts via WS."""
    from app.ws_manager import lock_manager

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if _is_hard_locked(image, user.id):
        raise HTTPException(status_code=409, detail="Image already annotated by another annotator")

    acquired = _acquire_soft_lock(image_id, user.id, user.username)
    if not acquired:
        holder = _get_soft_lock_holder(image_id, exclude_user_id=user.id)
        held_by = holder.get("username", "another annotator") if holder else "another annotator"
        raise HTTPException(
            status_code=409,
            detail=f"Image is currently being worked on by {held_by}",
        )

    await lock_manager.broadcast(
        {"type": "lock", "image_id": image_id, "lock_type": "in_progress", "held_by": user.username},
        exclude_user_id=user.id,
    )

    return {"ok": True, "image_id": image_id, "lock_type": "soft"}


@router.post("/images/{image_id}/release-lock")
async def release_image_lock(
    image_id: int,
    user: User = Depends(require_annotator),
):
    """Release a soft lock when annotator navigates away without saving."""
    from app.ws_manager import lock_manager

    _release_soft_lock(image_id, user.id)
    await lock_manager.broadcast(
        {"type": "unlock", "image_id": image_id},
        exclude_user_id=user.id,
    )
    return {"ok": True}


@router.post("/images/{image_id}/heartbeat")
def heartbeat_image_lock(
    image_id: int,
    user: User = Depends(require_annotator),
):
    """Keep a soft lock alive. Frontend should call every ~10s."""
    refreshed = _refresh_soft_lock(image_id, user.id)
    if not refreshed:
        acquired = _acquire_soft_lock(image_id, user.id, user.username)
        if not acquired:
            return {"ok": False, "message": "Lock lost — image taken by another annotator"}
    return {"ok": True}


# ── Single Image for Annotation ───────────────────────────────────

@router.get("/images/{image_id}")
def get_image_for_annotation(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Get a single image with all categories and current annotations.
    Categories come from static JSON; AI suggestions from Image.arbiter_labels.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    categories = get_categories()
    existing_annotations = image.annotations or {}
    arbiter_labels = image.arbiter_labels or {}

    # Build categories data with current annotations and AI suggestions
    categories_data = []
    for cat in categories:
        cat_key = cat["key"]
        cat_ann = existing_annotations.get(cat_key, {})
        selected_ids = cat_ann.get("selected_option_ids", [])
        
        annotation_data = None
        if selected_ids:
            annotation_data = {
                "status": "completed",
                "selected_option_ids": selected_ids,
            }

        # AI suggestion from arbiter labels
        ai_suggestion = None
        if cat_key in arbiter_labels:
            pred_data = arbiter_labels[cat_key]
            # Use stored label directly if available
            opt_label = pred_data.get("label") if isinstance(pred_data, dict) else None
            pred_key = None
            if not opt_label:
                pred_key = (
                    pred_data.get("final") or pred_data.get("key")
                    if isinstance(pred_data, dict)
                    else str(pred_data) if pred_data else None
                )
                if pred_key:
                    opt_label = arbiter_label_to_option_label(pred_key)
            if opt_label:
                # Find the matching option ID
                for opt in cat.get("options", []):
                    if opt["label"] == opt_label:
                        ai_suggestion = {
                            "option_id": opt["id"],
                            "label": opt["label"],
                            "arbiter_key": pred_key or (pred_data.get("final") or pred_data.get("key") if isinstance(pred_data, dict) else pred_data),
                        }
                        break

        categories_data.append({
            "id": cat["id"],
            "name": cat["name"],
            "key": cat_key,
            "display_order": cat["display_order"],
            "options": cat["options"],
            "annotation": annotation_data,
            "ai_suggestion": ai_suggestion,
        })

    # Navigation (non-duplicate images)
    all_image_ids = [
        row.id for row in
        db.query(Image.id)
        .filter(Image.is_duplicate == False)  # noqa: E712
        .order_by(Image.id)
        .all()
    ]
    current_idx = all_image_ids.index(image_id) if image_id in all_image_ids else 0
    prev_id = all_image_ids[current_idx - 1] if current_idx > 0 else None
    next_id = all_image_ids[current_idx + 1] if current_idx < len(all_image_ids) - 1 else None

    # Lock / rework status
    is_hard = _is_hard_locked(image, user.id)
    is_owner = (image.annotated_by == user.id)
    has_rework = image.review_status == "rework_requested"
    is_own_rework = has_rework and is_owner

    can_edit = True
    is_locked = False
    if is_hard:
        # Another annotator owns this image — permanently locked
        can_edit = False
        is_locked = True

    is_blurred = (image.manually_blurred or False) or (
        (image.is_using_processed is not False)
        and image.compliance_status in ("blurred", "processed", "obfuscated")
    )
    
    return {
        "id": image.id,
        "filename": image.filename,
        "url": image.url,
        "source_folder_id": image.source_folder_id,
        "categories": categories_data,
        "prev_image_id": prev_id,
        "next_image_id": next_id,
        "current_index": current_idx,
        "total_images": len(all_image_ids),
        "is_improper": image.is_improper or False,
        "improper_reason": image.improper_reason,
        "is_locked": is_locked,
        "can_edit": can_edit,
        "is_rework": is_own_rework,  # Only true for the original annotator
        "is_ai_generated": image.is_ai_generated or False,
        "human_visible": image.human_visible,
        "manually_blurred": image.manually_blurred or False,
        "is_blurred": is_blurred,
        "is_using_processed": image.is_using_processed if image.is_using_processed is not None else True,
        "compliance_status": image.compliance_status,
        "has_original": bool(image.gcs_input_path),
        "annotation_status": "completed" if (is_hard and not is_owner) else (image.annotation_status or "pending"),
        "review_status": image.review_status if is_owner else None,  # Hide review details from non-owners
        "annotated_by": image.annotated_by,
    }


# ── Save Annotations ─────────────────────────────────────────────

@router.put("/images/{image_id}/annotations")
async def save_image_annotations(
    image_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Save annotations for all categories on a single image.

    Payload format::

        {
            "annotations": {
                "lighting": {"selected_option_ids": [4]},
                "viewpoint": {"selected_option_ids": [6]},
                ...
            },
            "is_rework": false
        }
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if image.is_improper:
        raise HTTPException(status_code=400, detail="Cannot save annotations for improper images")
    
    # ── CRITICAL: Only ONE annotator may annotate each image ──
    if _is_hard_locked(image, user.id):
        # Exception: allow if this is the original annotator's rework
        is_own_rework = (
            image.review_status == "rework_requested"
            and image.annotated_by == user.id
        )
        if not is_own_rework:
            raise HTTPException(
                status_code=409,
                detail="This image has already been annotated by another annotator.",
            )

    # ── CRITICAL: Rework belongs to the original annotator only ──
    if image.review_status == "rework_requested" and image.annotated_by != user.id:
                raise HTTPException(
                    status_code=403,
            detail="This rework is assigned to a different annotator.",
                )
    
    is_rework = payload.get("is_rework", False)
    annotations_data = payload.get("annotations", {})

    # Validate all categories have at least one option selected
    categories = get_categories()
    missing = []
    for cat in categories:
        cat_key = cat["key"]
        cat_ann = annotations_data.get(cat_key, {})
        selected_ids = cat_ann.get("selected_option_ids", [])
        if not selected_ids:
            missing.append(cat["name"])

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Please select an option for each category. Missing: {', '.join(missing)}",
        )

    # Enrich annotations with human-readable labels
    annotations_data = enrich_annotations_with_labels(annotations_data)

    # ── Append to annotation_history before overwriting ──
    now = datetime.now(timezone.utc)
    history = list(image.annotation_history or [])
    history.append({
        "ts": now.isoformat(),
        "by": user.id,
        "username": user.username,
        "role": "annotator",
        "action": "rework" if is_rework else "annotate",
        "annotations": annotations_data,
    })
    image.annotation_history = history

    # Update image
    image.annotations = annotations_data
    image.annotated_by = user.id
    image.annotated_at = now
    image.annotation_status = "completed"

    # Handle rework
    if is_rework and image.review_status == "rework_requested":
        image.review_status = "rework_completed"
    elif image.review_status is None:
        image.review_status = "pending"

    # Optional flags
    if payload.get("is_ai_generated") is not None:
        image.is_ai_generated = payload["is_ai_generated"]
        image.marked_ai_by = user.id
        image.marked_ai_at = datetime.now(timezone.utc)
    if payload.get("human_visible") is not None:
        image.human_visible = payload["human_visible"]
        image.human_visible_marked_by = user.id
        image.human_visible_marked_at = datetime.now(timezone.utc)
    if payload.get("is_duplicate") is not None:
        image.is_duplicate = payload["is_duplicate"]
    
    db.commit()
    
    # Release soft lock — hard lock is now in place
    _release_soft_lock(image_id, user.id)

    # Broadcast hard lock to all other annotators
    from app.ws_manager import lock_manager
    await lock_manager.broadcast(
        {"type": "lock", "image_id": image_id, "lock_type": "completed", "held_by": user.username},
        exclude_user_id=user.id,
    )

    return {
        "message": "Annotations saved",
        "image_id": image_id,
        "annotation_status": image.annotation_status,
    }


# ── Mark Image as Improper ─────────────────────────────────────────

class MarkImproperRequest(BaseModel):
    reason: str


@router.post("/images/{image_id}/mark-improper")
def mark_image_as_improper(
    image_id: int,
    payload: MarkImproperRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Mark an image as improper — flagged for admin review."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if image.is_improper:
        raise HTTPException(status_code=400, detail="Image already marked as improper")

    image.is_improper = True
    image.improper_reason = payload.reason
    image.marked_improper_by = user.id
    image.marked_improper_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "message": "Image marked as improper",
        "image_id": image_id,
        "reason": payload.reason,
    }


# ── AI-Generated Image Detection ────────────────────────────────

class AIDetectionRequest(BaseModel):
    is_ai_generated: bool
    confidence: Optional[int] = None  # 0-100


@router.put("/images/{image_id}/ai-detection")
def mark_ai_generated(
    image_id: int,
    request: AIDetectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Mark an image as AI-generated or real."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    image.is_ai_generated = request.is_ai_generated
    image.ai_detection_confidence = request.confidence
    image.marked_ai_by = user.id
    image.marked_ai_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "message": "AI detection status updated",
        "image_id": image_id,
        "is_ai_generated": request.is_ai_generated,
    }


@router.get("/images/{image_id}/ai-detection")
def get_ai_detection(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Get AI detection status for an image."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
        return {
        "image_id": image_id,
        "is_ai_generated": image.is_ai_generated,
        "ai_detection_confidence": image.ai_detection_confidence,
        "marked_ai_by": image.marked_ai_by,
        "marked_ai_at": image.marked_ai_at.isoformat() if image.marked_ai_at else None,
    }


# ── Human Visibility Detection ────────────────────────────────────

class HumanVisibilityRequest(BaseModel):
    human_visible: bool


@router.put("/images/{image_id}/human-visibility")
def mark_human_visibility(
    image_id: int,
    request: HumanVisibilityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Mark whether a human is visible in the image."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    image.human_visible = request.human_visible
    image.human_visible_marked_by = user.id
    image.human_visible_marked_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "message": "Human visibility status updated",
        "image_id": image_id,
        "human_visible": image.human_visible,
    }


@router.get("/images/{image_id}/human-visibility")
def get_human_visibility(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Get human visibility status for an image."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    return {
        "image_id": image_id,
        "human_visible": image.human_visible,
        "human_visible_marked_by": image.human_visible_marked_by,
        "human_visible_marked_at": (
            image.human_visible_marked_at.isoformat()
            if image.human_visible_marked_at else None
        ),
    }


# ── Bounding Box Blur ────────────────────────────────────────────

class BlurRegionSchema(BaseModel):
    x: float
    y: float
    width: float
    height: float


class BlurRegionsRequest(BaseModel):
    regions: list[BlurRegionSchema]


@router.post("/images/{image_id}/blur-regions")
def blur_image_regions_endpoint(
    image_id: int,
    payload: BlurRegionsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Draw bounding-box blur regions on an image and save the blurred copy."""
    from app.utils.deliverable import update_biometric_if_delivered
    import httpx as _httpx

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if not payload.regions:
        raise HTTPException(status_code=400, detail="No regions provided")

    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "image_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Try to get image bytes from cache or proxy
    cached_path = os.path.join(cache_dir, f"{image_id}.jpg")
    if os.path.exists(cached_path):
        with open(cached_path, "rb") as f:
            image_bytes = f.read()
    else:
        proxy_url = f"http://localhost:8000/api/images/proxy/{image_id}"
        try:
            resp = _httpx.get(proxy_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            image_bytes = resp.content
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

    regions = [r.model_dump() for r in payload.regions]
    blurred_bytes = blur_image_regions(image_bytes, regions)

    blurred_filename = f"{image_id}_blurred.jpg"
    blurred_path = os.path.join(cache_dir, blurred_filename)
    with open(blurred_path, "wb") as f:
        f.write(blurred_bytes)
    with open(cached_path, "wb") as f:
        f.write(blurred_bytes)

    # Update DB
    image.blur_regions = regions
    image.manually_blurred = True
    image.manually_blurred_by = user.id
    image.manually_blurred_at = datetime.now(timezone.utc)
    image.processed_url = f"file://image_cache/{blurred_filename}"
    image.is_using_processed = True
    image.processing_method = "manual"
    image.is_manually_modified = True

    if user.role == "annotator":
        image.is_blurred_annotator = True

    db.commit()

    # If image was already delivered, re-copy with latest version
    update_biometric_if_delivered(image.id, db)

    return {
        "status": "ok",
        "image_id": image_id,
        "regions_applied": len(regions),
    }


@router.get("/images/{image_id}/blur-regions")
def get_blur_regions(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Return saved blur regions for an image."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    regions = image.blur_regions or []
    return [
        {"x": r.get("x", 0), "y": r.get("y", 0), "width": r.get("width", 0), "height": r.get("height", 0)}
        for r in regions
    ]


# ── Deprecated Endpoints (backward compatibility) ─────────────────

@router.patch("/images/{image_id}/time")
def save_time_spent(
    image_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Deprecated — time tracking per image is no longer used."""
    return {"ok": True}


@router.get("/settings/time-limits")
def get_time_limits(
    db: Session = Depends(get_db),
    _user: User = Depends(require_annotator),
):
    """Deprecated — time tracking is no longer used."""
    return {"max_annotation_time_seconds": 0}
