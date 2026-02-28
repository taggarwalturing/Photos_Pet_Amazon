from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from typing import Optional
from app.database import get_db
from app.dependencies import require_annotator
from app.models.user import User
from app.models.image import Image
from app.models.category import Category
from app.models.option import Option
from app.models.annotation import Annotation, AnnotationSelection
from app.models.annotator_category import AnnotatorCategory
from app.models.image_assignment import AnnotatorImageAssignment
from app.models.settings import SystemSettings
from app.models.notification import Notification
from app.schemas.category import CategoryWithProgress
from app.schemas.annotation import AnnotationSave, AnnotationResponse, AnnotationTask


def _get_available_image_ids(db: Session, user_id: int) -> set[int]:
    """
    Get the set of image IDs available to this user.
    An image is available if:
    1. It has no annotations from anyone (unclaimed), OR
    2. It has at least one annotation from this user (claimed by this user)
    
    Images claimed by other users (have annotations from others but not this user) are excluded.
    """
    # Get all image IDs
    all_image_ids = set(row.id for row in db.query(Image.id).all())
    
    # Get image IDs that this user has annotated (claimed by this user)
    my_image_ids = set(
        row.image_id
        for row in db.query(Annotation.image_id)
        .filter(Annotation.annotator_id == user_id)
        .distinct()
        .all()
    )
    
    # Get image IDs that others have annotated (claimed by others)
    others_image_ids = set(
        row.image_id
        for row in db.query(Annotation.image_id)
        .filter(Annotation.annotator_id != user_id)
        .distinct()
        .all()
    )
    
    # Available = (all images) - (claimed by others but not by me)
    # In other words: my images + unclaimed images
    unclaimed_image_ids = all_image_ids - others_image_ids - my_image_ids
    available_image_ids = my_image_ids | unclaimed_image_ids
    
    return available_image_ids


def _get_assigned_image_ids(db: Session, user_id: int) -> set[int]:
    """Alias for backward compatibility - now returns available images."""
    return _get_available_image_ids(db, user_id)

router = APIRouter(prefix="/annotator", tags=["Annotator"])


def _get_setting(db: Session, key: str, default: str) -> str:
    """Get a setting value or return default if not found."""
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return setting.value if setting else default


def _get_max_annotation_time(db: Session) -> int:
    """Get max annotation time in seconds (default 120)."""
    return int(_get_setting(db, "max_annotation_time_seconds", "120"))


def _get_max_rework_time(db: Session) -> int:
    """Get max rework time in seconds (default 120)."""
    return int(_get_setting(db, "max_rework_time_seconds", "120"))


def _build_queue(db: Session, user_id: int, category_id: int) -> list[Image]:
    """
    Build the annotator's image queue for a category.

    The queue contains:
    1. Images this annotator has already touched (any status) — so they can go back
    2. Images NOT yet completed by ANY annotator for this category — the remaining work

    Images already completed by someone else (but not touched by this annotator)
    are excluded.

    Ordered by image.id for consistency.
    """
    all_images = db.query(Image).order_by(Image.id).all()

    # IDs of images this annotator has already annotated for this category
    my_annotation_image_ids = set(
        row.image_id
        for row in db.query(Annotation.image_id).filter(
            Annotation.annotator_id == user_id,
            Annotation.category_id == category_id,
        ).all()
    )

    # IDs of images completed by ANY annotator for this category
    completed_by_anyone_ids = set(
        row.image_id
        for row in db.query(Annotation.image_id).filter(
            Annotation.category_id == category_id,
            Annotation.status == "completed",
        ).all()
    )

    queue = []
    for img in all_images:
        if img.id in my_annotation_image_ids:
            # Annotator touched this — always include (for back navigation)
            queue.append(img)
        elif img.id not in completed_by_anyone_ids:
            # Not completed by anyone — still available
            queue.append(img)
        # else: completed by someone else, not touched by me — skip

    return queue


# ── Time Tracking Endpoint ─────────────────────────────────────────

@router.patch("/images/{image_id}/time")
def save_time_spent(
    image_id: int,
    payload: dict,  # {"time_spent_seconds": int}
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Lightweight endpoint to persist time_spent_seconds for an image.
    Updates all existing annotations for this user+image, or creates
    a placeholder annotation (status='in_progress') for the first
    assigned category if none exist yet.
    Called periodically (every 10s) and on page unload.
    """
    time_spent = payload.get("time_spent_seconds", 0)
    if not isinstance(time_spent, (int, float)) or time_spent < 0:
        return {"ok": True}  # silently ignore bad data

    time_spent = int(time_spent)

    # Get assigned categories
    assigned_cat_ids = [
        ac.category_id
        for ac in db.query(AnnotatorCategory)
        .filter(AnnotatorCategory.user_id == user.id)
        .all()
    ]
    if not assigned_cat_ids:
        return {"ok": True}

    # Update all existing annotations for this image+user
    existing = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == user.id,
            Annotation.category_id.in_(assigned_cat_ids),
        )
        .all()
    )

    if existing:
        for ann in existing:
            ann.time_spent_seconds = time_spent
    else:
        # No annotations yet — create an in_progress placeholder for the first category
        annotation = Annotation(
            image_id=image_id,
            annotator_id=user.id,
            category_id=assigned_cat_ids[0],
            status="in_progress",
            time_spent_seconds=time_spent,
        )
        db.add(annotation)

    db.commit()
    return {"ok": True}


# ── Image-First Workflow Endpoints ─────────────────────────────────

@router.get("/images")
def list_images_for_annotator(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    filter_status: Optional[str] = Query(None),  # all, pending, completed
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    List images assigned to this annotator with annotation status across assigned categories.
    For the image-first annotation workflow.
    """
    # Get assigned category IDs
    assigned_cat_ids = [
        ac.category_id
        for ac in db.query(AnnotatorCategory)
        .filter(AnnotatorCategory.user_id == user.id)
        .all()
    ]
    
    # Get available image IDs for this user (unclaimed or claimed by this user)
    available_image_ids = _get_available_image_ids(db, user.id)
    
    if not assigned_cat_ids:
        return {
            "images": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "assigned_categories": [],
            "assigned_image_count": len(available_image_ids),
        }
    
    # Get only available images (ordered by ID)
    all_images = (
        db.query(Image)
        .filter(Image.id.in_(available_image_ids))
        .order_by(Image.id)
        .all()
    )
    
    # Build image data with annotation status per category
    images_data = []
    for img in all_images:
        # Get annotations for this image by this user or completed by anyone
        my_annotations = (
            db.query(Annotation)
            .filter(
                Annotation.image_id == img.id,
                Annotation.annotator_id == user.id,
                Annotation.category_id.in_(assigned_cat_ids),
            )
            .all()
        )
        
        # Also check if completed by anyone else
        completed_by_anyone = (
            db.query(Annotation)
            .filter(
                Annotation.image_id == img.id,
                Annotation.category_id.in_(assigned_cat_ids),
                Annotation.status == "completed",
            )
            .all()
        )
        completed_cat_ids = {a.category_id for a in completed_by_anyone}
        
        # Build status per category and collect selected labels
        category_status = {}
        category_labels = {}  # category_id -> list of selected option labels
        for cat_id in assigned_cat_ids:
            my_ann = next((a for a in my_annotations if a.category_id == cat_id), None)
            if my_ann:
                category_status[str(cat_id)] = my_ann.status
                # Get selected option labels
                selections = (
                    db.query(AnnotationSelection)
                    .filter(AnnotationSelection.annotation_id == my_ann.id)
                    .all()
                )
                selected_option_ids = [s.option_id for s in selections]
                if selected_option_ids:
                    options = db.query(Option).filter(Option.id.in_(selected_option_ids)).all()
                    category_labels[str(cat_id)] = [o.label for o in options]
                else:
                    category_labels[str(cat_id)] = []
            elif cat_id in completed_cat_ids:
                category_status[str(cat_id)] = "completed_by_other"
                # Get labels from completed annotation
                completed_ann = next((a for a in completed_by_anyone if a.category_id == cat_id), None)
                if completed_ann:
                    selections = (
                        db.query(AnnotationSelection)
                        .filter(AnnotationSelection.annotation_id == completed_ann.id)
                        .all()
                    )
                    selected_option_ids = [s.option_id for s in selections]
                    if selected_option_ids:
                        options = db.query(Option).filter(Option.id.in_(selected_option_ids)).all()
                        category_labels[str(cat_id)] = [o.label for o in options]
                    else:
                        category_labels[str(cat_id)] = []
                else:
                    category_labels[str(cat_id)] = []
            else:
                category_status[str(cat_id)] = "pending"
                category_labels[str(cat_id)] = []
        
        # Determine overall status
        statuses = list(category_status.values())
        if all(s in ("completed", "completed_by_other") for s in statuses):
            overall_status = "completed"
        elif any(s == "completed" or s == "completed_by_other" for s in statuses):
            overall_status = "partial"
        else:
            overall_status = "pending"
        
        # Apply filter
        if filter_status == "pending" and overall_status != "pending":
            continue
        if filter_status == "completed" and overall_status != "completed":
            continue
        
        # Check if any annotation needs rework
        has_rework = any(
            a.review_status == "rework_requested" for a in my_annotations
        )
        
        # Check if any annotation is human-validated (locked)
        is_human_validated = any(
            a.human_validated for a in my_annotations
        )
        
        images_data.append({
            "id": img.id,
            "filename": img.filename,
            "url": img.url,
            "category_status": category_status,
            "category_labels": category_labels,  # Selected labels per category
            "overall_status": overall_status,
            "completed_count": sum(1 for s in statuses if s in ("completed", "completed_by_other")),
            "total_categories": len(assigned_cat_ids),
            "is_improper": img.is_improper,
            "improper_reason": img.improper_reason,
            "has_rework": has_rework,  # True if any annotation needs rework
            "is_human_validated": is_human_validated,  # True if validated by human (locked)
        })
    
    # Paginate
    total = len(images_data)
    start = (page - 1) * page_size
    paginated = images_data[start : start + page_size]
    
    # Get assigned categories with options
    categories = (
        db.query(Category)
        .filter(Category.id.in_(assigned_cat_ids))
        .options(joinedload(Category.options))
        .order_by(Category.display_order)
        .all()
    )
    
    return {
        "images": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "assigned_categories": [
            {
                "id": c.id,
                "name": c.name,
                "display_order": c.display_order,
                "options": [
                    {"id": o.id, "label": o.label, "is_typical": o.is_typical}
                    for o in sorted(c.options, key=lambda x: x.display_order)
                ],
            }
            for c in categories
        ],
        "assigned_image_count": len(available_image_ids),
    }


@router.get("/images/{image_id}")
def get_image_for_annotation(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Get a single image with all assigned categories and current annotations.
    For the image-first annotation workflow.
    Always allows viewing - returns is_locked and can_edit flags for UI control.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Verify this image is assigned to the user
    assigned_image_ids = _get_assigned_image_ids(db, user.id)
    if image_id not in assigned_image_ids:
        raise HTTPException(status_code=403, detail="This image is not assigned to you")
    
    # Get assigned categories
    assigned_cat_ids = [
        ac.category_id
        for ac in db.query(AnnotatorCategory)
        .filter(AnnotatorCategory.user_id == user.id)
        .all()
    ]
    
    if not assigned_cat_ids:
        raise HTTPException(status_code=403, detail="No categories assigned to you")
    
    categories = (
        db.query(Category)
        .filter(Category.id.in_(assigned_cat_ids))
        .options(joinedload(Category.options))
        .order_by(Category.display_order)
        .all()
    )
    
    # Get existing annotations for this image
    my_annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == user.id,
        )
        .all()
    )
    annotations_by_cat = {a.category_id: a for a in my_annotations}
    
    # Check what's completed by others
    completed_by_others = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.status == "completed",
            Annotation.annotator_id != user.id,
        )
        .all()
    )
    completed_by_others_cat_ids = {a.category_id for a in completed_by_others}
    
    # Build category data with annotations
    categories_data = []
    for cat in categories:
        my_ann = annotations_by_cat.get(cat.id)
        
        annotation_data = None
        if my_ann:
            sel_ids = [s.option_id for s in my_ann.selections]
            annotation_data = {
                "id": my_ann.id,
                "status": my_ann.status,
                "is_duplicate": my_ann.is_duplicate,
                "selected_option_ids": sel_ids,
                "time_spent_seconds": my_ann.time_spent_seconds,
            }
        
        categories_data.append({
            "id": cat.id,
            "name": cat.name,
            "display_order": cat.display_order,
            "options": [
                {"id": o.id, "label": o.label, "is_typical": o.is_typical}
                for o in sorted(cat.options, key=lambda x: x.display_order)
            ],
            "annotation": annotation_data,
            "completed_by_other": cat.id in completed_by_others_cat_ids and not my_ann,
        })
    
    # Get prev/next image IDs for navigation (within assigned images only)
    assigned_image_ids_sorted = sorted(assigned_image_ids)
    current_idx = assigned_image_ids_sorted.index(image_id) if image_id in assigned_image_ids_sorted else 0
    prev_id = assigned_image_ids_sorted[current_idx - 1] if current_idx > 0 else None
    next_id = assigned_image_ids_sorted[current_idx + 1] if current_idx < len(assigned_image_ids_sorted) - 1 else None
    
    # Check edit lock status
    # Only lock if annotations have been human-validated (not just model predictions)
    from app.models.edit_request import EditRequest
    human_validated_count = len([a for a in my_annotations if a.human_validated])
    is_locked = human_validated_count > 0
    
    # Check if any annotation is sent for rework - if so, allow editing without permission
    has_rework_request = any(
        a.review_status == "rework_requested" for a in my_annotations
    )
    
    pending_edit_request = None
    approved_edit_request = None
    can_edit = True
    is_rework = has_rework_request
    
    if is_locked and not has_rework_request:
        # Only check edit request if not sent for rework
        # Check for approved edit request
        approved_request = (
            db.query(EditRequest)
            .filter(
                EditRequest.user_id == user.id,
                EditRequest.image_id == image_id,
                EditRequest.status == "approved",
            )
            .first()
        )
        if approved_request:
            can_edit = True
            approved_edit_request = approved_request.id
        else:
            can_edit = False
            # Check for pending request
            pending_request = (
                db.query(EditRequest)
                .filter(
                    EditRequest.user_id == user.id,
                    EditRequest.image_id == image_id,
                    EditRequest.status == "pending",
                )
                .first()
            )
            if pending_request:
                pending_edit_request = pending_request.id
    elif has_rework_request:
        # Rework requested - always allow editing, mark as unlocked for UI
        can_edit = True
        is_locked = False
    
    return {
        "id": image.id,
        "filename": image.filename,
        "url": image.url,
        "categories": categories_data,
        "prev_image_id": prev_id,
        "next_image_id": next_id,
        "current_index": current_idx,
        "total_images": len(assigned_image_ids_sorted),
        "is_improper": image.is_improper,
        "improper_reason": image.improper_reason,
        "is_locked": is_locked,
        "can_edit": can_edit,
        "pending_edit_request": pending_edit_request,
        "approved_edit_request": approved_edit_request,
        "is_rework": is_rework,  # True if sent back for rework by admin
    }


@router.put("/images/{image_id}/annotations")
def save_image_annotations(
    image_id: int,
    payload: dict,  # {category_id: {selected_option_ids: [], is_duplicate: bool}}
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Save annotations for multiple categories on a single image.
    Payload format: {"annotations": {category_id: {selected_option_ids: [], is_duplicate: bool | null}}}
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Block saving annotations for improper images
    if image.is_improper:
        raise HTTPException(status_code=400, detail="Cannot save annotations for improper images")
    
    # Verify this image is assigned to the user
    assigned_image_ids = _get_assigned_image_ids(db, user.id)
    if image_id not in assigned_image_ids:
        raise HTTPException(status_code=403, detail="This image is not assigned to you")
    
    # Get assigned categories for edit lock check
    assigned_cat_ids_list = [
        ac.category_id
        for ac in db.query(AnnotatorCategory)
        .filter(AnnotatorCategory.user_id == user.id)
        .all()
    ]
    
    # Check if image has human-validated annotations (locked)
    # Model predictions (human_validated=False) don't trigger the lock
    human_validated_count = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == user.id,
            Annotation.category_id.in_(assigned_cat_ids_list),
            Annotation.human_validated == True,
        )
        .count()
    )
    
    if human_validated_count > 0:
        # Check if any annotation is sent for rework - if so, allow editing
        has_rework_request = (
            db.query(Annotation)
            .filter(
                Annotation.image_id == image_id,
                Annotation.annotator_id == user.id,
                Annotation.review_status == "rework_requested",
            )
            .count()
        ) > 0
        
        if not has_rework_request:
            # Not a rework - check for approved edit request
            from app.models.edit_request import EditRequest
            approved_request = (
                db.query(EditRequest)
                .filter(
                    EditRequest.user_id == user.id,
                    EditRequest.image_id == image_id,
                    EditRequest.status == "approved",
                )
                .first()
            )
            if not approved_request:
                raise HTTPException(
                    status_code=403,
                    detail="This image is locked. Request edit permission from admin."
                )
            # Consume the approved request after saving (mark it as used)
            approved_request.status = "used"
    
    # Get assigned categories
    assigned_cat_ids = set(assigned_cat_ids_list)
    
    annotations_data = payload.get("annotations", {})
    time_spent_seconds = payload.get("time_spent_seconds", 0)
    is_rework_submission = payload.get("is_rework", False)
    
    # Cap time at max limit
    max_annotation_time = _get_max_annotation_time(db)
    max_rework_time = _get_max_rework_time(db)
    
    if is_rework_submission:
        capped_time = min(time_spent_seconds, max_rework_time)
    else:
        capped_time = min(time_spent_seconds, max_annotation_time)
    
    # Validate that all assigned categories have at least one option selected
    # Check for categories that are not completed by others
    completed_by_others = set(
        row.category_id
        for row in db.query(Annotation.category_id).filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id != user.id,
            Annotation.category_id.in_(assigned_cat_ids),
            Annotation.status == "completed",
        ).all()
    )
    
    missing_categories = []
    for cat_id in assigned_cat_ids:
        # Skip if already completed by another annotator
        if cat_id in completed_by_others:
            continue
        
        cat_id_str = str(cat_id)
        ann_data = annotations_data.get(cat_id_str, {})
        selected_ids = ann_data.get("selected_option_ids", [])
        
        if not selected_ids or len(selected_ids) == 0:
            cat = db.query(Category).filter(Category.id == cat_id).first()
            if cat:
                missing_categories.append(cat.name)
    
    if missing_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Please select an option for each category. Missing: {', '.join(missing_categories)}"
        )
    
    saved = []
    
    for cat_id_str, ann_data in annotations_data.items():
        cat_id = int(cat_id_str)
        
        if cat_id not in assigned_cat_ids:
            continue  # Skip categories not assigned
        
        selected_option_ids = ann_data.get("selected_option_ids", [])
        is_duplicate = ann_data.get("is_duplicate")
        
        # Upsert annotation
        annotation = (
            db.query(Annotation)
            .filter(
                Annotation.image_id == image_id,
                Annotation.annotator_id == user.id,
                Annotation.category_id == cat_id,
            )
            .first()
        )
        
        if annotation:
            # Check if this is a rework submission
            was_rework = annotation.is_rework or annotation.review_status == "rework_requested"
            
            annotation.is_duplicate = is_duplicate
            annotation.status = "completed"
            annotation.human_validated = True  # Mark as validated by human
            
            if was_rework:
                # This is a rework - store time in rework_time_seconds
                annotation.rework_time_seconds = capped_time
                annotation.review_status = "rework_completed"
            else:
                # Normal annotation
                annotation.time_spent_seconds = capped_time
            
            # Clear old selections
            db.query(AnnotationSelection).filter(
                AnnotationSelection.annotation_id == annotation.id
            ).delete()
        else:
            annotation = Annotation(
                image_id=image_id,
                annotator_id=user.id,
                category_id=cat_id,
                is_duplicate=is_duplicate,
                status="completed",
                time_spent_seconds=capped_time,
                human_validated=True,  # Mark as validated by human
            )
            db.add(annotation)
            db.flush()
        
        # Add selections
        for option_id in selected_option_ids:
            db.add(AnnotationSelection(annotation_id=annotation.id, option_id=option_id))
        
        saved.append(cat_id)
    
    db.commit()
    
    return {"message": "Annotations saved", "saved_categories": saved}


# ── Category-First Workflow Endpoints (legacy) ─────────────────────

@router.get("/categories", response_model=list[CategoryWithProgress])
def my_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """List categories assigned to the current annotator, with progress."""
    assignments = (
        db.query(AnnotatorCategory)
        .filter(AnnotatorCategory.user_id == user.id)
        .options(joinedload(AnnotatorCategory.category))
        .all()
    )
    total_images = db.query(Image).count()
    result = []
    for a in assignments:
        # Count images completed by ANYONE for this category
        completed_by_anyone = (
            db.query(Annotation.image_id)
            .filter(
                Annotation.category_id == a.category_id,
                Annotation.status == "completed",
            )
            .distinct()
            .count()
        )
        # Count images this annotator personally completed
        my_completed = (
            db.query(Annotation)
            .filter(
                Annotation.annotator_id == user.id,
                Annotation.category_id == a.category_id,
                Annotation.status == "completed",
            )
            .count()
        )
        my_skipped = (
            db.query(Annotation)
            .filter(
                Annotation.annotator_id == user.id,
                Annotation.category_id == a.category_id,
                Annotation.status == "skipped",
            )
            .count()
        )
        # Remaining = total - completed by anyone
        remaining = total_images - completed_by_anyone
        result.append(CategoryWithProgress(
            id=a.category.id,
            name=a.category.name,
            display_order=a.category.display_order,
            total_images=total_images,
            completed_images=completed_by_anyone,
            skipped_images=my_skipped,
        ))
    result.sort(key=lambda c: c.display_order)
    return result


@router.get("/categories/{category_id}/queue-size")
def get_queue_size(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Get the size of this annotator's queue for a category."""
    assignment = (
        db.query(AnnotatorCategory)
        .filter(
            AnnotatorCategory.user_id == user.id,
            AnnotatorCategory.category_id == category_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=403, detail="Category not assigned to you")
    queue = _build_queue(db, user.id, category_id)
    return {"queue_size": len(queue)}


@router.get("/categories/{category_id}/resume-index")
def resume_index(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Return the queue index where the annotator should resume work."""
    assignment = (
        db.query(AnnotatorCategory)
        .filter(
            AnnotatorCategory.user_id == user.id,
            AnnotatorCategory.category_id == category_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=403, detail="Category not assigned to you")

    queue = _build_queue(db, user.id, category_id)
    if not queue:
        return {"index": 0, "queue_size": 0}

    my_completed_ids = set(
        row.image_id
        for row in db.query(Annotation.image_id).filter(
            Annotation.annotator_id == user.id,
            Annotation.category_id == category_id,
            Annotation.status == "completed",
        ).all()
    )

    for i, img in enumerate(queue):
        if img.id not in my_completed_ids:
            return {"index": i, "queue_size": len(queue)}

    return {"index": len(queue) - 1, "queue_size": len(queue)}


@router.get("/categories/{category_id}/task/{queue_index}", response_model=AnnotationTask)
def get_annotation_task(
    category_id: int,
    queue_index: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Get a specific image (by queue index) for annotation in a given category.
    The queue only contains images available to this annotator (shared queue model).
    """
    # Verify assignment
    assignment = (
        db.query(AnnotatorCategory)
        .filter(
            AnnotatorCategory.user_id == user.id,
            AnnotatorCategory.category_id == category_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=403, detail="Category not assigned to you")

    # Build queue
    queue = _build_queue(db, user.id, category_id)
    total = len(queue)

    if total == 0:
        raise HTTPException(status_code=404, detail="No images available — all completed")

    if queue_index < 0 or queue_index >= total:
        raise HTTPException(status_code=404, detail="Queue index out of range")

    image = queue[queue_index]

    # Get category with options
    category = (
        db.query(Category)
        .options(joinedload(Category.options))
        .filter(Category.id == category_id)
        .first()
    )

    # Get existing annotation (this annotator's own)
    annotation = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image.id,
            Annotation.annotator_id == user.id,
            Annotation.category_id == category_id,
        )
        .first()
    )

    current = None
    if annotation:
        sel_ids = [s.option_id for s in annotation.selections]
        current = AnnotationResponse(
            id=annotation.id,
            image_id=annotation.image_id,
            annotator_id=annotation.annotator_id,
            category_id=annotation.category_id,
            is_duplicate=annotation.is_duplicate,
            status=annotation.status,
            review_status=annotation.review_status,
            review_note=annotation.review_note,
            selected_option_ids=sel_ids,
            time_spent_seconds=annotation.time_spent_seconds,
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
        )

    return AnnotationTask(
        image_id=image.id,
        image_url=image.url,
        image_filename=image.filename,
        category_id=category.id,
        category_name=category.name,
        options=[
            {"id": o.id, "label": o.label, "is_typical": o.is_typical}
            for o in category.options
        ],
        current_annotation=current,
        image_index=queue_index,
        total_images=total,
    )


@router.put("/categories/{category_id}/images/{image_id}/annotate", response_model=AnnotationResponse)
def save_annotation(
    category_id: int,
    image_id: int,
    payload: AnnotationSave,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Save or update an annotation for a specific image + category."""
    # Verify assignment
    assignment = (
        db.query(AnnotatorCategory)
        .filter(
            AnnotatorCategory.user_id == user.id,
            AnnotatorCategory.category_id == category_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=403, detail="Category not assigned to you")

    # Verify image exists
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Block saving annotations for improper images
    if image.is_improper:
        raise HTTPException(status_code=400, detail="Cannot save annotations for improper images")
    
    # Upsert annotation
    annotation = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == user.id,
            Annotation.category_id == category_id,
        )
        .first()
    )

    if annotation:
        # Guard: never downgrade a completed annotation to skipped
        if annotation.status == "completed" and payload.status == "skipped":
            # Return the existing annotation unchanged
            option_ids = [
                s.option_id
                for s in db.query(AnnotationSelection)
                .filter(AnnotationSelection.annotation_id == annotation.id)
                .all()
            ]
            return AnnotationResponse(
                id=annotation.id,
                image_id=annotation.image_id,
                annotator_id=annotation.annotator_id,
                category_id=annotation.category_id,
                is_duplicate=annotation.is_duplicate,
                status=annotation.status,
                review_status=annotation.review_status,
                review_note=annotation.review_note,
                reviewed_by=annotation.reviewed_by,
                reviewed_at=annotation.reviewed_at,
                selected_option_ids=option_ids,
                time_spent_seconds=annotation.time_spent_seconds,
                created_at=annotation.created_at,
                updated_at=annotation.updated_at,
            )

        annotation.is_duplicate = payload.is_duplicate
        annotation.status = payload.status
        annotation.time_spent_seconds = payload.time_spent_seconds
        # Clear old selections
        db.query(AnnotationSelection).filter(
            AnnotationSelection.annotation_id == annotation.id
        ).delete()
    else:
        annotation = Annotation(
            image_id=image_id,
            annotator_id=user.id,
            category_id=category_id,
            is_duplicate=payload.is_duplicate,
            status=payload.status,
            time_spent_seconds=payload.time_spent_seconds,
        )
        db.add(annotation)
        db.flush()  # get annotation.id

    # Add selections
    for option_id in payload.selected_option_ids:
        db.add(AnnotationSelection(annotation_id=annotation.id, option_id=option_id))

    db.commit()
    db.refresh(annotation)

    return AnnotationResponse(
        id=annotation.id,
        image_id=annotation.image_id,
        annotator_id=annotation.annotator_id,
        category_id=annotation.category_id,
        is_duplicate=annotation.is_duplicate,
        status=annotation.status,
        selected_option_ids=[s.option_id for s in annotation.selections],
        time_spent_seconds=annotation.time_spent_seconds,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


# ── Mark Image as Improper ─────────────────────────────────────────

from pydantic import BaseModel
from datetime import datetime as dt_datetime

class MarkImproperRequest(BaseModel):
    reason: str


@router.post("/images/{image_id}/mark-improper")
def mark_image_as_improper(
    image_id: int,
    payload: MarkImproperRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Mark an image as improper. The image will be flagged for admin review
    and no annotations can be saved for it.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Block saving annotations for improper images
    if image.is_improper:
        raise HTTPException(status_code=400, detail="Cannot save annotations for improper images")
    
    # Verify this image is assigned to the user
    assigned_image_ids = _get_assigned_image_ids(db, user.id)
    if image_id not in assigned_image_ids:
        raise HTTPException(status_code=403, detail="This image is not assigned to you")
    
    # Get assigned categories for edit lock check
    assigned_cat_ids_list = [
        ac.category_id
        for ac in db.query(AnnotatorCategory)
        .filter(AnnotatorCategory.user_id == user.id)
        .all()
    ]
    
    # Check if image has human-validated annotations (locked)
    # Model predictions (human_validated=False) don't trigger the lock
    human_validated_count = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == user.id,
            Annotation.category_id.in_(assigned_cat_ids_list),
            Annotation.human_validated == True,
        )
        .count()
    )
    
    if human_validated_count > 0:
        # Check if any annotation is sent for rework - if so, allow editing
        has_rework_request = (
            db.query(Annotation)
            .filter(
                Annotation.image_id == image_id,
                Annotation.annotator_id == user.id,
                Annotation.review_status == "rework_requested",
            )
            .count()
        ) > 0
        
        if not has_rework_request:
            # Not a rework - check for approved edit request
            from app.models.edit_request import EditRequest
            approved_request = (
                db.query(EditRequest)
                .filter(
                    EditRequest.user_id == user.id,
                    EditRequest.image_id == image_id,
                    EditRequest.status == "approved",
                )
                .first()
            )
            if not approved_request:
                raise HTTPException(
                    status_code=403,
                    detail="This image is locked. Request edit permission from admin."
                )
            # Consume the approved request after saving (mark it as used)
            approved_request.status = "used"
    
    # Verify this image is assigned to the user (already checked above)
    # assigned_image_ids = _get_assigned_image_ids(db, user.id)
    # if image_id not in assigned_image_ids:
    #     raise HTTPException(status_code=403, detail="This image is not assigned to you")
    assigned_image_ids = _get_assigned_image_ids(db, user.id)
    if image_id not in assigned_image_ids:
        raise HTTPException(status_code=403, detail="This image is not assigned to you")
    
    # Mark as improper
    image.is_improper = True
    image.improper_reason = payload.reason
    image.marked_improper_by = user.id
    image.marked_improper_at = dt_datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Image marked as improper",
        "image_id": image_id,
        "reason": payload.reason,
    }


# ── Edit Request Endpoints ─────────────────────────────────────────

from app.models.edit_request import EditRequest

class EditRequestCreate(BaseModel):
    reason: str


@router.post("/images/{image_id}/request-edit")
def request_edit_permission(
    image_id: int,
    payload: EditRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Request permission to edit annotations on a completed image.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Verify this image is assigned to the user
    assigned_image_ids = _get_assigned_image_ids(db, user.id)
    if image_id not in assigned_image_ids:
        raise HTTPException(status_code=403, detail="This image is not assigned to you")
    
    # Check if there's already a pending request
    existing_request = (
        db.query(EditRequest)
        .filter(
            EditRequest.user_id == user.id,
            EditRequest.image_id == image_id,
            EditRequest.status == "pending",
        )
        .first()
    )
    if existing_request:
        raise HTTPException(status_code=400, detail="You already have a pending edit request for this image")
    
    # Create new request
    edit_request = EditRequest(
        user_id=user.id,
        image_id=image_id,
        reason=payload.reason,
        status="pending",
    )
    db.add(edit_request)
    db.commit()
    
    return {
        "message": "Edit request submitted",
        "request_id": edit_request.id,
    }


@router.get("/images/{image_id}/edit-status")
def get_edit_status(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """
    Check if the annotator can edit annotations on this image.
    Returns: can_edit (bool), pending_request (bool), approved_request_id (int or null)
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Get assigned categories for this user
    assigned_cat_ids = [
        ac.category_id
        for ac in db.query(AnnotatorCategory)
        .filter(AnnotatorCategory.user_id == user.id)
        .all()
    ]
    
    # Check if image has any completed annotations by this user
    completed_annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == user.id,
            Annotation.category_id.in_(assigned_cat_ids),
            Annotation.status == "completed",
        )
        .count()
    )
    
    # If no completed annotations, can always edit
    if completed_annotations == 0:
        return {
            "can_edit": True,
            "is_locked": False,
            "pending_request": False,
            "approved_request_id": None,
            "is_rework": False,
        }
    
    # Check if any annotations are human-validated
    human_validated_count = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.category_id.in_(assigned_cat_ids),
            Annotation.annotator_id == user.id,
            Annotation.human_validated == True,
        )
        .count()
    )
    
    # If no human-validated annotations, can still edit (model predictions only)
    if human_validated_count == 0:
        return {
            "can_edit": True,
            "is_locked": False,
            "pending_request": False,
            "approved_request_id": None,
            "is_rework": False,
        }
    
    # Check if any annotation is sent for rework - if so, allow editing
    has_rework_request = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == user.id,
            Annotation.review_status == "rework_requested",
        )
        .count()
    ) > 0
    
    if has_rework_request:
        return {
            "can_edit": True,
            "is_locked": False,
            "pending_request": False,
            "approved_request_id": None,
            "is_rework": True,
        }
    
    # Check for approved edit request
    approved_request = (
        db.query(EditRequest)
        .filter(
            EditRequest.user_id == user.id,
            EditRequest.image_id == image_id,
            EditRequest.status == "approved",
        )
        .order_by(EditRequest.reviewed_at.desc())
        .first()
    )
    
    if approved_request:
        return {
            "can_edit": True,
            "is_locked": False,
            "pending_request": False,
            "approved_request_id": approved_request.id,
            "is_rework": False,
        }
    
    # Check for pending request
    pending_request = (
        db.query(EditRequest)
        .filter(
            EditRequest.user_id == user.id,
            EditRequest.image_id == image_id,
            EditRequest.status == "pending",
        )
        .first()
    )
    
    return {
        "can_edit": False,
        "is_locked": True,
        "pending_request": pending_request is not None,
        "pending_request_id": pending_request.id if pending_request else None,
        "approved_request_id": None,
        "is_rework": False,
    }


@router.get("/edit-requests")
def list_my_edit_requests(
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """List all edit requests made by this annotator."""
    requests = (
        db.query(EditRequest)
        .filter(EditRequest.user_id == user.id)
        .order_by(EditRequest.created_at.desc())
        .all()
    )
    
    result = []
    for r in requests:
        image = db.query(Image).filter(Image.id == r.image_id).first()
        result.append({
            "id": r.id,
            "image_id": r.image_id,
            "image_filename": image.filename if image else None,
            "image_url": image.url if image else None,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at,
            "review_note": r.review_note,
            "reviewed_at": r.reviewed_at,
        })
    
    return result


# ── Notifications ────────────────────────────────────────────────

@router.get("/notifications")
def list_notifications(
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """List notifications for this annotator."""
    query = db.query(Notification).filter(Notification.user_id == user.id)
    
    if unread_only:
        query = query.filter(Notification.is_read == False)
    
    notifications = query.order_by(Notification.created_at.desc()).limit(50).all()
    
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "image_id": n.image_id,
            "is_read": n.is_read,
            "created_at": n.created_at,
        }
        for n in notifications
    ]


@router.get("/notifications/unread-count")
def get_unread_notification_count(
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Get count of unread notifications."""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read == False)
        .count()
    )
    return {"count": count}


@router.put("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Mark a notification as read."""
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    db.commit()
    return {"message": "Notification marked as read"}


@router.put("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    user: User = Depends(require_annotator),
):
    """Mark all notifications as read."""
    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}


# ── Settings (read-only for annotators) ──────────────────────────

@router.get("/settings/time-limits")
def get_time_limits(
    db: Session = Depends(get_db),
    _user: User = Depends(require_annotator),
):
    """Get time limit settings for countdown timer."""
    return {
        "max_annotation_time_seconds": _get_max_annotation_time(db),
        "max_rework_time_seconds": _get_max_rework_time(db),
    }


# ── AI-Generated Image Detection ────────────────────────────────

from pydantic import BaseModel as PydanticBaseModel
from datetime import datetime as dt

class AIDetectionRequest(PydanticBaseModel):
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
    
    # Update AI detection fields
    image.is_ai_generated = request.is_ai_generated
    image.ai_detection_confidence = request.confidence
    image.marked_ai_by = user.id
    image.marked_ai_at = dt.now()
    
    db.commit()
    
    return {
        "message": "AI detection status updated",
        "image_id": image_id,
        "is_ai_generated": request.is_ai_generated
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
        "marked_ai_at": image.marked_ai_at.isoformat() if image.marked_ai_at else None
    }
