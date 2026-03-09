import json
import os
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, and_, func, cast, Date
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.category import Category
from app.models.image import Image
from app.models.annotation import Annotation
from app.models.annotator_category import AnnotatorCategory
from app.schemas.user import UserCreate, UserUpdate, UserResponse, AssignCategoriesRequest
from app.schemas.category import CategoryResponse
from app.models.annotation import AnnotationSelection
from app.models.option import Option
from app.models.settings import SystemSettings
from app.models.notification import Notification
from app.schemas.annotation import (
    ProgressResponse, ImageCompletionResponse,
    ReviewApproveRequest, ReviewUpdateRequest, ReviewAnnotationDetail,
    ReviewTableCell, ReviewTableRow, ReviewTableCategory, ReviewTableResponse,
)
from app.services.auth import hash_password
from app.utils.deliverable import check_and_deliver_image, update_biometric_if_delivered
from app.models.final_label import FinalLabel
from pydantic import BaseModel


router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Deliverable Images Helper ────────────────────────────────────
# Delegates to app.utils.deliverable for moving images to
# deliverable/ folder management


# ── User Management ──────────────────────────────────────────────

@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.id).all()
    # All annotators have access to ALL images
    total_images = db.query(Image).count()
    result = []
    for u in users:
        assigned_cat_ids = [ac.category_id for ac in u.assigned_categories]
        
        # All annotators see all images
        assigned_image_count = total_images if u.role == "annotator" and assigned_cat_ids else 0
        
        # Get completed annotations count
        completed_annotations = (
            db.query(Annotation)
            .filter(
                Annotation.annotator_id == u.id,
                Annotation.status == "completed",
            )
            .count()
        )
        
        # Total needed = all_images * assigned_categories
        total_annotations_needed = assigned_image_count * len(assigned_cat_ids)
        
        # Get improper images marked by this user
        improper_marked_count = (
            db.query(Image)
            .filter(Image.marked_improper_by == u.id)
            .count()
        )
        
        # Count images annotated today (distinct images with completed annotations updated today)
        today = date.today()
        today_image_count = (
            db.query(Annotation.image_id)
            .filter(
                Annotation.annotator_id == u.id,
                Annotation.status == "completed",
                cast(Annotation.updated_at, Date) == today,
            )
            .distinct()
            .count()
        )
        
        result.append(UserResponse(
            id=u.id,
            username=u.username,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
            assigned_category_ids=assigned_cat_ids,
            assigned_image_count=assigned_image_count,
            completed_annotations=completed_annotations,
            total_annotations_needed=total_annotations_needed,
            improper_marked_count=improper_marked_count,
            today_image_count=today_image_count,
        ))
    return result


@router.get("/users/daily-stats")
def get_daily_annotation_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Get daily annotation counts per annotator for the last N days.
    Returns how many distinct images each annotator completed per day.
    """
    start_date = date.today() - timedelta(days=days - 1)
    
    # Query: group by annotator_id and date, count distinct images
    rows = (
        db.query(
            Annotation.annotator_id,
            cast(Annotation.updated_at, Date).label("annotation_date"),
            func.count(func.distinct(Annotation.image_id)).label("image_count"),
        )
        .filter(
            Annotation.status == "completed",
            cast(Annotation.updated_at, Date) >= start_date,
        )
        .group_by(Annotation.annotator_id, cast(Annotation.updated_at, Date))
        .all()
    )
    
    # Get annotator usernames
    annotators = (
        db.query(User)
        .filter(User.role == "annotator")
        .all()
    )
    username_map = {u.id: u.username for u in annotators}
    
    # Build per-annotator daily stats
    stats = {}
    for annotator_id, annotation_date, image_count in rows:
        username = username_map.get(annotator_id, f"user_{annotator_id}")
        if username not in stats:
            stats[username] = {"annotator_id": annotator_id, "daily": {}}
        stats[username]["daily"][str(annotation_date)] = image_count
    
    # Build date range
    date_range = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        date_range.append(str(d))
    
    return {
        "date_range": date_range,
        "annotators": stats,
    }


@router.get("/annotator-stats")
def get_annotator_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Comprehensive daily stats per annotator:
      - annotated: distinct images with completed annotations per day
      - blurred: images blurred by annotator per day (manually_blurred_at)
      - restored: images restored by annotator per day (restored_at_annotator)
      - approved: annotator's annotations approved per day (reviewed_at)
    """
    start_date = date.today() - timedelta(days=days - 1)

    # ── All annotators ──
    annotators = db.query(User).filter(User.role == "annotator").all()
    id_to_name = {u.id: u.username for u in annotators}

    # Prepare result skeleton per annotator
    result = {}
    for u in annotators:
        result[u.username] = {
            "annotator_id": u.id,
            "annotated": {},   # date -> count
            "blurred": {},     # date -> count
            "restored": {},    # date -> count
            "approved": {},    # date -> count
            "totals": {"annotated": 0, "blurred": 0, "restored": 0, "approved": 0},
        }

    # ── 1. Annotated per day (distinct images completed) ──
    annotated_rows = (
        db.query(
            Annotation.annotator_id,
            cast(Annotation.updated_at, Date).label("d"),
            func.count(func.distinct(Annotation.image_id)).label("cnt"),
        )
        .filter(
            Annotation.status == "completed",
            cast(Annotation.updated_at, Date) >= start_date,
        )
        .group_by(Annotation.annotator_id, cast(Annotation.updated_at, Date))
        .all()
    )
    for annotator_id, d, cnt in annotated_rows:
        name = id_to_name.get(annotator_id)
        if name and name in result:
            result[name]["annotated"][str(d)] = cnt

    # ── 2. Blurred per day (images where manually_blurred_by = annotator) ──
    blurred_rows = (
        db.query(
            Image.manually_blurred_by,
            cast(Image.manually_blurred_at, Date).label("d"),
            func.count(Image.id).label("cnt"),
        )
        .filter(
            Image.manually_blurred_by.isnot(None),
            Image.manually_blurred_at.isnot(None),
            cast(Image.manually_blurred_at, Date) >= start_date,
        )
        .group_by(Image.manually_blurred_by, cast(Image.manually_blurred_at, Date))
        .all()
    )
    for user_id, d, cnt in blurred_rows:
        name = id_to_name.get(user_id)
        if name and name in result:
            result[name]["blurred"][str(d)] = cnt

    # ── 3. Restored per day (images where restored_by_annotator_id = annotator) ──
    restored_rows = (
        db.query(
            Image.restored_by_annotator_id,
            cast(Image.restored_at_annotator, Date).label("d"),
            func.count(Image.id).label("cnt"),
        )
        .filter(
            Image.restored_by_annotator_id.isnot(None),
            Image.restored_at_annotator.isnot(None),
            cast(Image.restored_at_annotator, Date) >= start_date,
        )
        .group_by(Image.restored_by_annotator_id, cast(Image.restored_at_annotator, Date))
        .all()
    )
    for user_id, d, cnt in restored_rows:
        name = id_to_name.get(user_id)
        if name and name in result:
            result[name]["restored"][str(d)] = cnt

    # ── 4. Approved per day (annotator's annotations that were approved, grouped by reviewed_at) ──
    approved_rows = (
        db.query(
            Annotation.annotator_id,
            cast(Annotation.reviewed_at, Date).label("d"),
            func.count(func.distinct(Annotation.image_id)).label("cnt"),
        )
        .filter(
            Annotation.review_status == "approved",
            Annotation.reviewed_at.isnot(None),
            cast(Annotation.reviewed_at, Date) >= start_date,
        )
        .group_by(Annotation.annotator_id, cast(Annotation.reviewed_at, Date))
        .all()
    )
    for annotator_id, d, cnt in approved_rows:
        name = id_to_name.get(annotator_id)
        if name and name in result:
            result[name]["approved"][str(d)] = cnt

    # ── Compute cumulative totals (all-time, not just the window) ──
    for u in annotators:
        name = u.username
        if name not in result:
            continue
        result[name]["totals"]["annotated"] = (
            db.query(func.count(func.distinct(Annotation.image_id)))
            .filter(Annotation.annotator_id == u.id, Annotation.status == "completed")
            .scalar() or 0
        )
        result[name]["totals"]["blurred"] = (
            db.query(func.count(Image.id))
            .filter(Image.manually_blurred_by == u.id)
            .scalar() or 0
        )
        result[name]["totals"]["restored"] = (
            db.query(func.count(Image.id))
            .filter(Image.restored_by_annotator_id == u.id)
            .scalar() or 0
        )
        result[name]["totals"]["approved"] = (
            db.query(func.count(func.distinct(Annotation.image_id)))
            .filter(Annotation.annotator_id == u.id, Annotation.review_status == "approved")
            .scalar() or 0
        )

    # Build date range
    date_range = [str(start_date + timedelta(days=i)) for i in range(days)]

    return {
        "date_range": date_range,
        "annotators": result,
    }


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        assigned_category_ids=[],
    )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        assigned_category_ids=[ac.category_id for ac in user.assigned_categories],
    )


# ── Category Assignment ──────────────────────────────────────────

@router.put("/users/{user_id}/categories")
def assign_categories(
    user_id: int,
    payload: AssignCategoriesRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "annotator":
        raise HTTPException(status_code=400, detail="Can only assign categories to annotators")

    # Remove existing assignments
    db.query(AnnotatorCategory).filter(AnnotatorCategory.user_id == user_id).delete()

    # Add new assignments
    for cat_id in payload.category_ids:
        cat = db.query(Category).filter(Category.id == cat_id).first()
        if not cat:
            raise HTTPException(status_code=400, detail=f"Category {cat_id} not found")
        db.add(AnnotatorCategory(user_id=user_id, category_id=cat_id))

    db.commit()
    return {"message": "Categories assigned", "category_ids": payload.category_ids}


# ── Categories ────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    categories = (
        db.query(Category)
        .options(joinedload(Category.options))
        .order_by(Category.display_order)
        .all()
    )
    return categories


# ── Images ────────────────────────────────────────────────────────

@router.get("/images")
def list_images(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    status_filter: Optional[str] = Query(None, alias="filter"),
    search: Optional[str] = Query(None),
):
    query = db.query(Image).order_by(Image.id)

    # Apply search
    if search:
        query = query.filter(Image.filename.ilike(f"%{search}%"))

    # Apply filter
    if status_filter == "blurred":
        query = query.filter(
            or_(
                Image.compliance_status.in_(["blurred", "processed", "obfuscated"]),
                Image.manually_blurred == True,
            )
        )
    elif status_filter == "clean":
        query = query.filter(
            Image.compliance_status == "clean",
            or_(Image.manually_blurred == False, Image.manually_blurred.is_(None)),
        )
    elif status_filter == "manually_blurred":
        query = query.filter(Image.manually_blurred == True)
    elif status_filter == "ai_generated":
        query = query.filter(Image.is_ai_generated == True)
    elif status_filter == "human_visible":
        query = query.filter(Image.human_visible == True)
    elif status_filter == "improper":
        query = query.filter(Image.is_improper == True)
    elif status_filter == "delivered":
        query = query.filter(Image.deliverable_image_path.isnot(None))
    elif status_filter == "not_delivered":
        query = query.filter(Image.deliverable_image_path.is_(None))

    images = query.all()

    # Compute summary stats (unfiltered) in a SINGLE aggregate query (optimized from 8 → 1)
    from sqlalchemy import case
    summary_row = db.query(
        func.count().label("total"),
        func.sum(case(
            (or_(
                Image.compliance_status.in_(["blurred", "processed", "obfuscated"]),
                Image.manually_blurred == True,
            ), 1), else_=0
        )).label("blurred"),
        func.sum(case(
            (and_(
                Image.compliance_status == "clean",
                or_(Image.manually_blurred == False, Image.manually_blurred.is_(None)),
            ), 1), else_=0
        )).label("clean"),
        func.sum(case((Image.manually_blurred == True, 1), else_=0)).label("manually_blurred"),
        func.sum(case((Image.is_ai_generated == True, 1), else_=0)).label("ai_generated"),
        func.sum(case((Image.human_visible == True, 1), else_=0)).label("human_visible"),
        func.sum(case((Image.is_improper == True, 1), else_=0)).label("improper"),
        func.sum(case((Image.deliverable_image_path.isnot(None), 1), else_=0)).label("delivered"),
    ).one()

    # ── Batch-load label data for all images ──────────────────────
    from collections import defaultdict

    # Arbiter label mappings (same as annotator.py)
    _DB_CAT_TO_ARBITER = {
        "Lighting Variation": "lighting",
        "Angle & Perspective Variation": "viewpoint",
        "Environmental Context Variation": "environment",
        "Occlusion & Partial Visibility": "occlusion",
        "Activity & Motion": "activity",
        "Multi-Pet Disambiguation": "multipet",
    }
    _ARBITER_LABEL_TO_OPTION = {
        "dusk_dawn": "Dusk-dawn lighting",
        "harsh_sunlight": "Harsh outdoor sunlight with shadows",
        "low_light": "Low light conditions",
        "well_lit": "Well-lit conditions (typical)",
        "front_eye_level": "Front-facing at eye level (typical)",
        "ground_level": "Ground-level view",
        "no_head": "No head showing",
        "head_only": "Partial view (head only)",
        "top_down": "Top-down view",
        "car_carrier": "In car-carrier",
        "indoor": "Indoor setting (typical)",
        "outdoor_dirt": "Outdoor dirt road",
        "snow": "Snow environment",
        "vet_clinic": "Vet clinic",
        "yard_complex": "Yard with a complex background",
        "behind_furniture": "Behind furniture (face only)",
        "full_body": "Full-body, unobstructed (typical)",
        "under_blanket": "Partially hidden under a blanket",
        "peeking_box": "Peeking out of box-carrier",
        "toy_obscuring": "Toy obscuring part of body",
        "eating_drinking": "Eating-drinking",
        "jumping": "Jumping to catch toy",
        "playing": "Playing with another pet",
        "running": "Running with motion blur",
        "sitting_posed": "Sitting still-posed (typical)",
        "sleeping": "Sleeping-curled up",
        "pet_with_lookalike": "Pet with breed lookalike",
        "single_pet": "Single pet (typical)",
        "three_same": "Three pets of same breed",
        "two_similar": "Two similar-looking pets together",
        "None": "None of the Above",
    }

    # Load all categories
    all_categories = db.query(Category).options(joinedload(Category.options)).order_by(Category.display_order).all()
    cat_by_id = {c.id: c for c in all_categories}

    # Build option id → label lookup
    option_label_map = {}
    for cat in all_categories:
        for o in cat.options:
            option_label_map[o.id] = o.label

    # Batch load all completed annotations with selections
    image_ids = [img.id for img in images]
    all_annotations = (
        db.query(Annotation)
        .filter(Annotation.image_id.in_(image_ids), Annotation.status == "completed")
        .options(joinedload(Annotation.selections))
        .all()
    ) if image_ids else []

    # Index annotations by image_id
    anns_by_image = defaultdict(list)
    for ann in all_annotations:
        anns_by_image[ann.image_id].append(ann)

    # Build per-image label data
    def _build_labels(img):
        """Resolve labels: human annotations take priority, then AI predictions."""
        category_labels = {}   # cat_id → [label strings]
        label_source = {}      # cat_id → "human" | "ai" | "approved"
        annotation_status = {} # cat_id → status string

        # Human annotations
        img_anns = anns_by_image.get(img.id, [])
        for ann in img_anns:
            cat = cat_by_id.get(ann.category_id)
            if not cat:
                continue
            selected_labels = [option_label_map.get(s.option_id, "") for s in ann.selections]
            selected_labels = [l for l in selected_labels if l]
            if selected_labels:
                category_labels[str(ann.category_id)] = selected_labels
                if ann.review_status == "approved":
                    label_source[str(ann.category_id)] = "approved"
                    annotation_status[str(ann.category_id)] = "approved"
                elif ann.review_status == "rework_requested":
                    label_source[str(ann.category_id)] = "rework"
                    annotation_status[str(ann.category_id)] = "rework"
                else:
                    label_source[str(ann.category_id)] = "human"
                    annotation_status[str(ann.category_id)] = "completed"

        # AI predictions for remaining categories
        arbiter_labels = img.arbiter_labels or {}
        if arbiter_labels:
            for cat in all_categories:
                if str(cat.id) in category_labels:
                    continue  # Human label takes priority
                arb_key = _DB_CAT_TO_ARBITER.get(cat.name)
                if arb_key and arb_key in arbiter_labels:
                    pred_data = arbiter_labels[arb_key]
                    pred = pred_data.get("final", pred_data) if isinstance(pred_data, dict) else str(pred_data) if pred_data else None
                    if pred:
                        option_label = _ARBITER_LABEL_TO_OPTION.get(pred)
                        if option_label:
                            category_labels[str(cat.id)] = [option_label]
                            label_source[str(cat.id)] = "ai"
                            annotation_status[str(cat.id)] = "ai_predicted"

        return category_labels, label_source, annotation_status

    images_out = []
    for img in images:
        cat_labels, lbl_source, ann_status = _build_labels(img)
        images_out.append({
            "id": img.id,
            "filename": img.filename,
            "original_filename": img.original_filename,  # Original Drive name (human-readable)
            "url": img.url,
            "created_at": img.created_at,
            "compliance_status": img.compliance_status,
            "manually_blurred": img.manually_blurred or False,
            "is_ai_generated": img.is_ai_generated or False,
            "human_visible": img.human_visible,
            "is_improper": img.is_improper or False,
            "human_faces_detected": img.human_faces_detected or 0,
            "is_using_processed": img.is_using_processed if img.is_using_processed is not None else True,
            "is_blurred": (img.manually_blurred or False) or (
                (img.is_using_processed is not False) and
                (img.compliance_status or "") in ("blurred", "processed", "obfuscated")
            ),
            "source_drive_folder_id": img.source_drive_folder_id,
            "image_drive_id": img.image_drive_id,
            "is_blurred_annotator": img.is_blurred_annotator or False,
            "is_restore_annotator": img.is_restore_annotator or False,
            "deliverable_image_path": img.deliverable_image_path,
            "is_manually_modified": img.is_manually_modified,
            # Label data
            "category_labels": cat_labels,
            "category_label_source": lbl_source,
            "annotation_status": ann_status,
        })

    return {
        "summary": {
            "total": summary_row.total or 0,
            "blurred": summary_row.blurred or 0,
            "clean": summary_row.clean or 0,
            "manually_blurred": summary_row.manually_blurred or 0,
            "ai_generated": summary_row.ai_generated or 0,
            "human_visible": summary_row.human_visible or 0,
            "improper": summary_row.improper or 0,
            "delivered": summary_row.delivered or 0,
        },
        "total": len(images_out),
        "categories": [
            {"id": c.id, "name": c.name}
            for c in all_categories
        ],
        "images": images_out,
    }


# ── Single image status (for admin lightbox) ─────────────────────

@router.get("/images/{image_id}/status")
def get_image_status(
    image_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Return blur-related status flags for a single image (admin-accessible)."""
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    _manually_blurred = img.manually_blurred or False
    _is_using_processed = img.is_using_processed if img.is_using_processed is not None else True
    _compliance_status = img.compliance_status or None
    _is_blurred = _manually_blurred or (
        (img.is_using_processed is not False) and
        (_compliance_status or "") in ("blurred", "processed", "obfuscated")
    )

    return {
        "id": img.id,
        "is_blurred": _is_blurred,
        "compliance_status": _compliance_status,
        "is_using_processed": _is_using_processed,
        "manually_blurred": _manually_blurred,
        "is_blurred_annotator": img.is_blurred_annotator or False,
        "is_restore_annotator": img.is_restore_annotator or False,
        "deliverable_image_path": img.deliverable_image_path,
        "is_manually_modified": img.is_manually_modified,
    }


# ── Progress ──────────────────────────────────────────────────────

@router.get("/progress", response_model=list[ProgressResponse])
def get_progress(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    total_images = db.query(Image).count()
    assignments = (
        db.query(AnnotatorCategory)
        .options(
            joinedload(AnnotatorCategory.user),
            joinedload(AnnotatorCategory.category),
        )
        .all()
    )
    result = []
    for assignment in assignments:
        completed = (
            db.query(Annotation)
            .filter(
                Annotation.annotator_id == assignment.user_id,
                Annotation.category_id == assignment.category_id,
                Annotation.status == "completed",
            )
            .count()
        )
        skipped = (
            db.query(Annotation)
            .filter(
                Annotation.annotator_id == assignment.user_id,
                Annotation.category_id == assignment.category_id,
                Annotation.status == "skipped",
            )
            .count()
        )
        in_prog = (
            db.query(Annotation)
            .filter(
                Annotation.annotator_id == assignment.user_id,
                Annotation.category_id == assignment.category_id,
                Annotation.status == "in_progress",
            )
            .count()
        )
        result.append(ProgressResponse(
            category_id=assignment.category_id,
            category_name=assignment.category.name,
            annotator_id=assignment.user_id,
            annotator_username=assignment.user.username,
            total_images=total_images,
            completed=completed,
            skipped=skipped,
            in_progress=in_prog,
            pending=total_images - completed - skipped - in_prog,
        ))
    return result


# ── Image Completion Status ───────────────────────────────────────

@router.get("/images/completion", response_model=list[ImageCompletionResponse])
def get_image_completion(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Per-image completion status.
    An image is fully complete when ALL categories have a 'completed'
    annotation for that image (by any annotator).
    """
    images = db.query(Image).order_by(Image.id).all()
    categories = db.query(Category).order_by(Category.display_order).all()

    # Build a set of category IDs that are currently assigned to someone
    assigned_cat_ids = set(
        row.category_id
        for row in db.query(AnnotatorCategory.category_id).distinct().all()
    )

    # Total = ALL categories, not just assigned ones
    total_cats = len(categories)

    result = []
    for img in images:
        # Get all annotations for this image
        annotations = (
            db.query(Annotation)
            .filter(Annotation.image_id == img.id)
            .all()
        )

        # Build per-category status (for ALL categories)
        cat_details = []
        completed_cats = 0
        for cat in categories:
            cat_annotations = [a for a in annotations if a.category_id == cat.id]

            if not cat_annotations:
                # No annotation exists — check if category is even assigned
                status = "pending" if cat.id in assigned_cat_ids else "unassigned"
                cat_details.append({
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "status": status,
                    "annotator_username": None,
                })
            else:
                # Prefer completed, then in_progress, then skipped
                best = None
                for a in cat_annotations:
                    if a.status == "completed":
                        best = a
                        break
                if not best:
                    best = cat_annotations[0]

                if best.status == "completed":
                    completed_cats += 1

                annotator = db.query(User).filter(User.id == best.annotator_id).first()
                cat_details.append({
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "status": best.status,
                    "annotator_username": annotator.username if annotator else None,
                })

        result.append(ImageCompletionResponse(
            image_id=img.id,
            image_filename=img.filename,
            image_url=img.url,
            total_categories=total_cats,
            completed_categories=completed_cats,
            category_details=cat_details,
            is_fully_complete=(completed_cats >= total_cats and total_cats > 0),
        ))

    return result


# ── Review ────────────────────────────────────────────────────────

@router.get("/review", response_model=list[ReviewAnnotationDetail])
def list_annotations_for_review(
    category_id: Optional[int] = Query(None),
    annotator_id: Optional[int] = Query(None),
    review_status: Optional[str] = Query(None),  # pending, approved
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    List completed annotations for admin review.
    Filterable by category, annotator, and review status.
    """
    query = (
        db.query(Annotation)
        .filter(Annotation.status == "completed")
        .options(
            joinedload(Annotation.image),
            joinedload(Annotation.annotator),
            joinedload(Annotation.category).joinedload(Category.options),
            joinedload(Annotation.selections),
            joinedload(Annotation.reviewer),
        )
    )

    if category_id is not None:
        query = query.filter(Annotation.category_id == category_id)
    if annotator_id is not None:
        query = query.filter(Annotation.annotator_id == annotator_id)
    if review_status == "pending":
        # Pending includes: no review yet, sent for rework, OR rework completed (waiting for re-review)
        query = query.filter(
            (Annotation.review_status.is_(None)) | 
            (Annotation.review_status == "rework_requested") |
            (Annotation.review_status == "rework_completed")
        )
    elif review_status == "approved":
        query = query.filter(Annotation.review_status == "approved")

    annotations = (
        query.order_by(Annotation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    result = []
    for a in annotations:
        selected_options = []
        for sel in a.selections:
            opt = db.query(Option).filter(Option.id == sel.option_id).first()
            if opt:
                selected_options.append({"id": opt.id, "label": opt.label})

        # All options in this category (for admin editing)
        all_options = [
            {"id": o.id, "label": o.label, "is_typical": o.is_typical}
            for o in sorted(a.category.options, key=lambda x: x.display_order)
        ]

        result.append(ReviewAnnotationDetail(
            id=a.id,
            image_id=a.image_id,
            image_url=a.image.url,
            image_filename=a.image.filename,
            annotator_id=a.annotator_id,
            annotator_username=a.annotator.username,
            category_id=a.category_id,
            category_name=a.category.name,
            is_duplicate=a.is_duplicate,
            status=a.status,
            review_status=a.review_status,
            review_note=a.review_note,
            reviewed_by_username=a.reviewer.username if a.reviewer else None,
            reviewed_at=a.reviewed_at,
            selected_options=selected_options,
            all_options=all_options,
            time_spent_seconds=a.time_spent_seconds,
            rework_time_seconds=a.rework_time_seconds or 0,
            is_rework=a.is_rework or False,
            created_at=a.created_at,
            updated_at=a.updated_at,
        ))

    return result


@router.get("/review/table", response_model=ReviewTableResponse)
def review_table(
    annotator_id: Optional[int] = Query(None),
    review_status: Optional[str] = Query(None),  # pending, approved
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Spreadsheet-style view: images as rows, categories as columns.
    Returns annotations grouped by image with image-level pagination.
    """
    # Base query: completed annotations OR in_progress with rework_requested
    from sqlalchemy import or_, and_
    base_q = db.query(Annotation).filter(
        or_(
            Annotation.status == "completed",
            and_(Annotation.status == "in_progress", Annotation.review_status == "rework_requested")
        )
    )
    if annotator_id is not None:
        base_q = base_q.filter(Annotation.annotator_id == annotator_id)
    if review_status == "pending":
        # Pending includes: no review yet, sent for rework, OR rework completed (waiting for re-review)
        base_q = base_q.filter(
            or_(
                Annotation.review_status.is_(None), 
                Annotation.review_status == "rework_requested",
                Annotation.review_status == "rework_completed"
            )
        )
    elif review_status == "approved":
        base_q = base_q.filter(Annotation.review_status == "approved")

    # Get distinct image IDs that have matching annotations, ordered by image_id
    image_ids_q = (
        base_q
        .with_entities(Annotation.image_id)
        .distinct()
        .order_by(Annotation.image_id)
    )
    all_image_ids = [row[0] for row in image_ids_q.all()]
    total_images = len(all_image_ids)

    # Paginate at image level
    start = (page - 1) * page_size
    page_image_ids = all_image_ids[start : start + page_size]

    # Fetch all annotations for this page of images (with eager loads)
    # Include completed OR in_progress with rework_requested
    annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id.in_(page_image_ids),
            or_(
                Annotation.status == "completed",
                and_(Annotation.status == "in_progress", Annotation.review_status == "rework_requested")
            )
        )
        .options(
            joinedload(Annotation.image),
            joinedload(Annotation.annotator),
            joinedload(Annotation.reviewer),
            joinedload(Annotation.category).joinedload(Category.options),
            joinedload(Annotation.selections),
        )
        .order_by(Annotation.image_id)
        .all()
    )

    # Apply filters again on the full set for this page
    # (we fetched ALL annotations for the images, need to re-apply annotator/status filters)
    filtered_annotations = annotations
    if annotator_id is not None:
        filtered_annotations = [a for a in filtered_annotations if a.annotator_id == annotator_id]
    if review_status == "pending":
        # Pending includes: no review yet, sent for rework, OR rework completed (waiting for re-review)
        filtered_annotations = [a for a in filtered_annotations if a.review_status is None or a.review_status in ("rework_requested", "rework_completed")]
    elif review_status == "approved":
        filtered_annotations = [a for a in filtered_annotations if a.review_status == "approved"]

    # Group by image
    from collections import defaultdict
    image_map = {}  # image_id -> {image obj, annotations by category}
    for a in filtered_annotations:
        if a.image_id not in image_map:
            image_map[a.image_id] = {
                "image": a.image,
                "annotations": {},
            }

        # Build selected options
        selected_options = []
        for sel in a.selections:
            opt = db.query(Option).filter(Option.id == sel.option_id).first()
            if opt:
                selected_options.append({"id": opt.id, "label": opt.label})

        # All options in this category
        all_options = [
            {"id": o.id, "label": o.label, "is_typical": o.is_typical}
            for o in sorted(a.category.options, key=lambda x: x.display_order)
        ]

        image_map[a.image_id]["annotations"][str(a.category_id)] = ReviewTableCell(
            annotation_id=a.id,
            selected_options=selected_options,
            all_options=all_options,
            annotator_username=a.annotator.username,
            is_duplicate=a.is_duplicate,
            review_status=a.review_status,
            reviewed_by_username=a.reviewer.username if a.reviewer else None,
            reviewed_at=a.reviewed_at,
            time_spent_seconds=a.time_spent_seconds,
            rework_time_seconds=a.rework_time_seconds or 0,
            is_rework=a.is_rework or False,
        )

    # Build rows in the order of page_image_ids
    rows = []
    for img_id in page_image_ids:
        if img_id in image_map:
            entry = image_map[img_id]
            img = entry["image"]
            # Compute is_blurred the same way the annotator endpoint does
            _manually_blurred = img.manually_blurred or False
            _is_using_processed = img.is_using_processed
            _compliance_status = img.compliance_status
            _is_blurred = _manually_blurred or (
                _compliance_status == 'blurred' and _is_using_processed is not False
            )

            # Determine image-level reviewer: most recently reviewed annotation
            _reviewed_by = None
            _reviewed_at = None
            for cell in entry["annotations"].values():
                if cell.reviewed_at and (not _reviewed_at or cell.reviewed_at > _reviewed_at):
                    _reviewed_at = cell.reviewed_at
                    _reviewed_by = cell.reviewed_by_username

            rows.append(ReviewTableRow(
                image_id=img_id,
                image_drive_id=img.image_drive_id,
                image_url=img.url,
                image_filename=img.filename,
                annotations=entry["annotations"],
                is_blurred=_is_blurred,
                compliance_status=_compliance_status,
                is_using_processed=_is_using_processed,
                manually_blurred=_manually_blurred,
                reviewed_by_username=_reviewed_by,
                reviewed_at=_reviewed_at,
                is_blurred_annotator=img.is_blurred_annotator or False,
                is_restore_annotator=img.is_restore_annotator or False,
                deliverable_image_path=img.deliverable_image_path,
                is_manually_modified=img.is_manually_modified,
            ))

    # All categories for column headers
    categories = db.query(Category).order_by(Category.display_order).all()
    cat_list = [ReviewTableCategory(id=c.id, name=c.name) for c in categories]

    return ReviewTableResponse(
        images=rows,
        categories=cat_list,
        total_images=total_images,
        page=page,
        page_size=page_size,
    )


@router.get("/review/stats")
def review_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get image-level review statistics."""
    from sqlalchemy import or_, and_, func
    from collections import defaultdict

    # Get all annotations that are completed or in rework
    annotations = db.query(
        Annotation.image_id,
        Annotation.review_status,
        Annotation.status,
    ).filter(
        or_(
            Annotation.status == "completed",
            and_(Annotation.status == "in_progress", Annotation.review_status == "rework_requested")
        )
    ).all()

    # Group by image_id
    image_annotations = defaultdict(list)
    for ann in annotations:
        image_annotations[ann.image_id].append(ann)

    total_images = len(image_annotations)
    approved_images = 0
    pending_images = 0

    for img_id, anns in image_annotations.items():
        all_approved = all(a.review_status == "approved" for a in anns)
        if all_approved:
            approved_images += 1
        else:
            pending_images += 1

    # Deliverable stats
    delivered = db.query(Image).filter(Image.deliverable_image_path.isnot(None)).count()
    delivered_modified = db.query(Image).filter(
        Image.deliverable_image_path.isnot(None),
        Image.is_manually_modified == True,
    ).count()
    delivered_original = db.query(Image).filter(
        Image.deliverable_image_path.isnot(None),
        Image.is_manually_modified == False,
    ).count()

    return {
        "total_completed": total_images,
        "pending_review": pending_images,
        "approved": approved_images,
        "delivered": delivered,
        "delivered_modified": delivered_modified,
        "delivered_original": delivered_original,
    }


@router.get("/deliverable/stats")
def deliverable_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get deliverable image statistics grouped by folder_id."""
    delivered_images = (
        db.query(Image)
        .filter(Image.deliverable_image_path.isnot(None))
        .all()
    )

    # Group by folder_id
    folder_stats = {}
    for img in delivered_images:
        fid = img.source_drive_folder_id or "unknown"
        if fid not in folder_stats:
            folder_stats[fid] = {"folder_id": fid, "total": 0, "modified": 0, "original": 0}
        folder_stats[fid]["total"] += 1
        if img.is_manually_modified:
            folder_stats[fid]["modified"] += 1
        else:
            folder_stats[fid]["original"] += 1

    total_delivered = len(delivered_images)
    total_images = db.query(Image).count()

    return {
        "total_images": total_images,
        "total_delivered": total_delivered,
        "total_pending": total_images - total_delivered,
        "by_folder": list(folder_stats.values()),
    }


@router.put("/review/{annotation_id}/approve")
def approve_annotation(
    annotation_id: int,
    payload: ReviewApproveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Approve an annotation as-is. If all annotations for the image are approved, copy to deliverable."""
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    annotation.status = "completed"  # Ensure status is completed when approved
    annotation.review_status = "approved"
    annotation.review_note = payload.review_note
    annotation.reviewed_by = admin.id
    annotation.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    # Check if all annotations for this image are now approved → copy to deliverable
    check_and_deliver_image(annotation.image_id, db)

    return {"message": "Annotation approved", "annotation_id": annotation_id}


@router.put("/review/{annotation_id}/update")
def update_and_approve_annotation(
    annotation_id: int,
    payload: ReviewUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin edits the selections and approves the annotation."""
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Update selections
    db.query(AnnotationSelection).filter(
        AnnotationSelection.annotation_id == annotation.id
    ).delete()
    for option_id in payload.selected_option_ids:
        db.add(AnnotationSelection(annotation_id=annotation.id, option_id=option_id))

    # Update duplicate flag if provided
    if payload.is_duplicate is not None:
        annotation.is_duplicate = payload.is_duplicate

    # Mark as approved
    annotation.status = "completed"  # Ensure status is completed when approved
    annotation.review_status = "approved"
    annotation.review_note = payload.review_note or "Edited by admin"
    annotation.reviewed_by = admin.id
    annotation.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    # Check if all annotations for this image are now approved → copy to deliverable
    check_and_deliver_image(annotation.image_id, db)

    return {"message": "Annotation updated and approved", "annotation_id": annotation_id}


# ── Improper Images ───────────────────────────────────────────────

@router.get("/images/improper")
def list_improper_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all images marked as improper by annotators."""
    query = (
        db.query(Image)
        .filter(Image.is_improper == True)
        .order_by(Image.marked_improper_at.desc())
    )
    
    total = query.count()
    images = query.offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for img in images:
        marker = None
        if img.marked_improper_by:
            marker = db.query(User).filter(User.id == img.marked_improper_by).first()
        
        result.append({
            "id": img.id,
            "filename": img.filename,
            "url": img.url,
            "is_improper": img.is_improper,
            "improper_reason": img.improper_reason,
            "marked_improper_by": marker.username if marker else None,
            "marked_improper_by_id": img.marked_improper_by,
            "marked_improper_at": img.marked_improper_at,
        })
    
    return {
        "images": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/images/improper/count")
def get_improper_images_count(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get count of improper images."""
    count = db.query(Image).filter(Image.is_improper == True).count()
    return {"count": count}


@router.put("/images/{image_id}/revoke-improper")
def revoke_improper_status(
    image_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin revokes improper status - marks image as proper again."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if not image.is_improper:
        raise HTTPException(status_code=400, detail="Image is not marked as improper")
    
    image.is_improper = False
    image.improper_reason = None
    image.marked_improper_by = None
    image.marked_improper_at = None
    
    db.commit()
    
    return {
        "message": "Image marked as proper again",
        "image_id": image_id,
    }


# ── Edit Requests ─────────────────────────────────────────────────

from app.models.edit_request import EditRequest


@router.get("/edit-requests")
def list_edit_requests(
    status_filter: Optional[str] = Query(None),  # pending, approved, rejected
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all edit requests."""
    query = db.query(EditRequest).order_by(EditRequest.created_at.desc())
    
    if status_filter:
        query = query.filter(EditRequest.status == status_filter)
    
    total = query.count()
    requests = query.offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for r in requests:
        user = db.query(User).filter(User.id == r.user_id).first()
        image = db.query(Image).filter(Image.id == r.image_id).first()
        reviewer = db.query(User).filter(User.id == r.reviewed_by).first() if r.reviewed_by else None
        
        result.append({
            "id": r.id,
            "user_id": r.user_id,
            "username": user.username if user else None,
            "image_id": r.image_id,
            "image_filename": image.filename if image else None,
            "image_url": image.url if image else None,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at,
            "reviewed_by": reviewer.username if reviewer else None,
            "reviewed_at": r.reviewed_at,
            "review_note": r.review_note,
        })
    
    return {
        "requests": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/edit-requests/count")
def get_edit_requests_count(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get count of pending edit requests."""
    pending = db.query(EditRequest).filter(EditRequest.status == "pending").count()
    approved = db.query(EditRequest).filter(EditRequest.status == "approved").count()
    rejected = db.query(EditRequest).filter(EditRequest.status == "rejected").count()
    return {
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "total": pending + approved + rejected,
    }


@router.put("/edit-requests/{request_id}/approve")
def approve_edit_request(
    request_id: int,
    review_note: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Approve an edit request."""
    edit_request = db.query(EditRequest).filter(EditRequest.id == request_id).first()
    if not edit_request:
        raise HTTPException(status_code=404, detail="Edit request not found")
    
    if edit_request.status != "pending":
        raise HTTPException(status_code=400, detail="Request is not pending")
    
    edit_request.status = "approved"
    edit_request.reviewed_by = admin.id
    edit_request.reviewed_at = datetime.now(timezone.utc)
    edit_request.review_note = review_note
    
    db.commit()
    
    return {"message": "Edit request approved", "request_id": request_id}


@router.put("/edit-requests/{request_id}/reject")
def reject_edit_request(
    request_id: int,
    review_note: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Reject an edit request."""
    edit_request = db.query(EditRequest).filter(EditRequest.id == request_id).first()
    if not edit_request:
        raise HTTPException(status_code=404, detail="Edit request not found")
    
    if edit_request.status != "pending":
        raise HTTPException(status_code=400, detail="Request is not pending")
    
    edit_request.status = "rejected"
    edit_request.reviewed_by = admin.id
    edit_request.reviewed_at = datetime.now(timezone.utc)
    edit_request.review_note = review_note
    
    db.commit()
    
    return {"message": "Edit request rejected", "request_id": request_id}


# ── Settings Management ──────────────────────────────────────────

class SettingsResponse(BaseModel):
    max_annotation_time_seconds: int
    max_rework_time_seconds: int


class SettingsUpdateRequest(BaseModel):
    max_annotation_time_seconds: Optional[int] = None
    max_rework_time_seconds: Optional[int] = None


def _get_setting(db: Session, key: str, default: str) -> str:
    """Get a setting value or return default if not found."""
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return setting.value if setting else default


def _set_setting(db: Session, key: str, value: str):
    """Set a setting value, creating if not exists."""
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = SystemSettings(key=key, value=value)
        db.add(setting)
    db.commit()


@router.get("/settings", response_model=SettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get system settings for annotation time limits."""
    return SettingsResponse(
        max_annotation_time_seconds=int(_get_setting(db, "max_annotation_time_seconds", "120")),
        max_rework_time_seconds=int(_get_setting(db, "max_rework_time_seconds", "120")),
    )


@router.put("/settings")
def update_settings(
    payload: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update system settings for annotation time limits."""
    if payload.max_annotation_time_seconds is not None:
        if payload.max_annotation_time_seconds < 10:
            raise HTTPException(status_code=400, detail="Max annotation time must be at least 10 seconds")
        _set_setting(db, "max_annotation_time_seconds", str(payload.max_annotation_time_seconds))
    
    if payload.max_rework_time_seconds is not None:
        if payload.max_rework_time_seconds < 10:
            raise HTTPException(status_code=400, detail="Max rework time must be at least 10 seconds")
        _set_setting(db, "max_rework_time_seconds", str(payload.max_rework_time_seconds))
    
    return {
        "message": "Settings updated",
        "max_annotation_time_seconds": int(_get_setting(db, "max_annotation_time_seconds", "120")),
        "max_rework_time_seconds": int(_get_setting(db, "max_rework_time_seconds", "120")),
    }




# ── Send for Rework ──────────────────────────────────────────────

class ReworkRequest(BaseModel):
    reason: str


class ImageReworkRequest(BaseModel):
    reason: str
    annotator_id: int


@router.post("/images/{image_id}/rework")
def send_image_for_rework(
    image_id: int,
    payload: ImageReworkRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Send ALL annotations for an image (by a specific annotator) back for rework.
    This resets ALL annotation statuses to 'in_progress', creates ONE notification for the annotator,
    and tracks that this is a rework.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Get ALL annotations for this image by this annotator (regardless of current status)
    annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == image_id,
            Annotation.annotator_id == payload.annotator_id,
        )
        .all()
    )
    
    if not annotations:
        raise HTTPException(status_code=400, detail="No completed annotations found for this image by this annotator")
    
    now = datetime.now(timezone.utc)
    
    # Reset ALL annotation statuses for this image
    for annotation in annotations:
        annotation.status = "in_progress"
        annotation.review_status = "rework_requested"
        annotation.review_note = payload.reason
        annotation.reviewed_by = admin.id
        annotation.reviewed_at = now
        annotation.is_rework = True
        annotation.rework_time_seconds = 0  # Reset rework time
    
    # Create ONE notification for the annotator
    notification = Notification(
        user_id=payload.annotator_id,
        type="rework_request",
        title="Rework Required",
        message=f"Image '{image.filename}' needs rework ({len(annotations)} categories). Reason: {payload.reason}",
        image_id=image_id,
    )
    db.add(notification)
    
    db.commit()
    
    return {
        "message": f"Image sent for rework ({len(annotations)} categories)",
        "image_id": image_id,
        "annotator_id": payload.annotator_id,
        "categories_affected": len(annotations),
    }


# Keep old endpoint for backwards compatibility but redirect to image-level
@router.post("/annotations/{annotation_id}/rework")
def send_annotation_for_rework(
    annotation_id: int,
    payload: ReworkRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Send ALL annotations for the same image (by the same annotator) back for rework.
    Takes a single annotation_id but affects ALL categories for that image.
    """
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    # Get ALL annotations for this image by this annotator (regardless of current status)
    all_annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id == annotation.image_id,
            Annotation.annotator_id == annotation.annotator_id,
        )
        .all()
    )
    
    if not all_annotations:
        raise HTTPException(status_code=400, detail="No annotations found for this image")
    
    now = datetime.now(timezone.utc)
    
    # Reset ALL annotation statuses for this image
    for ann in all_annotations:
        ann.status = "in_progress"
        ann.review_status = "rework_requested"
        ann.review_note = payload.reason
        ann.reviewed_by = admin.id
        ann.reviewed_at = now
        ann.is_rework = True
        ann.rework_time_seconds = 0  # Reset rework time
    
    # Get image info for the notification
    image = db.query(Image).filter(Image.id == annotation.image_id).first()
    
    # Create ONE notification for the annotator
    notification = Notification(
        user_id=annotation.annotator_id,
        type="rework_request",
        title="Rework Required",
        message=f"Image '{image.filename}' needs rework ({len(all_annotations)} categories). Reason: {payload.reason}",
        image_id=annotation.image_id,
    )
    db.add(notification)
    
    db.commit()
    
    return {
        "message": f"Image sent for rework ({len(all_annotations)} categories)",
        "image_id": annotation.image_id,
        "annotator_id": annotation.annotator_id,
        "categories_affected": len(all_annotations),
    }


# ─── Auto-Processor Endpoints ─────────────────────────────────────

@router.get('/auto-processor/status')
def get_auto_processor_status(
    admin: User = Depends(require_admin)
):
    """Get status of the auto-processor"""
    from app.background_tasks import auto_processor
    
    return {
        'is_running': auto_processor.is_running,
        'last_run': auto_processor.last_run.isoformat() if auto_processor.last_run else None,
        'processed_count': auto_processor.processed_count,
        'failed_count': auto_processor.failed_count,
    }


@router.post('/auto-processor/trigger')
async def trigger_auto_processor(
    admin: User = Depends(require_admin)
):
    """Manually trigger the auto-processor"""
    from app.background_tasks import auto_processor
    
    if auto_processor.is_running:
        raise HTTPException(
            status_code=400,
            detail='Auto-processor is already running'
        )
    
    # Run in background
    import asyncio
    asyncio.create_task(auto_processor.run_processing_cycle())
    
    return {'message': 'Auto-processor triggered successfully'}


# ── Photo Registry (All Downloaded Photos Status) ──────────────────

@router.get("/photo-registry")
def get_photo_registry(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str = Query("", description="Search by filename"),
    status_filter: str = Query("all", description="all|unique|duplicate|blurred|clean|manually_blurred"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Comprehensive photo registry showing ALL downloaded images with:
    - unique/duplicate status + parent image name
    - original path and processed path
    - pipeline blur status, manual blur status + annotated_blur path
    """
    import os
    from pathlib import Path

    from app.utils import get_pipeline_workspace
    workspace = get_pipeline_workspace()

    # ── Discover all workspace roots (per-folder + legacy) ──
    workspace_roots = []
    folders_dir = workspace / "folders"
    if folders_dir.is_dir():
        for fd in sorted(folders_dir.iterdir()):
            if fd.is_dir():
                workspace_roots.append(fd)
    workspace_roots.append(workspace)  # legacy flat workspace as fallback

    # ── 1. Build duplicate map from cluster folders ──
    duplicate_map = {}      # duplicate_filename → original_filename
    for ws_root in workspace_roots:
        # Load duplicate info from deduplication_stats.json (DB-driven approach)
        dedup_stats_path = ws_root / "deduplication_stats.json"
        if dedup_stats_path.exists():
            try:
                import json as _json
                with open(dedup_stats_path, 'r') as f:
                    dedup_stats = _json.load(f)
                dm = dedup_stats.get('duplicate_map', {})
                duplicate_map.update(dm)
            except Exception:
                pass

        # Legacy: scan cluster folders if they exist
        clusters_dir = ws_root / "02_duplicate_clusters"
        if clusters_dir.is_dir():
            for cluster_folder in sorted(clusters_dir.iterdir()):
                if not cluster_folder.is_dir():
                    continue
                original = None
                dupes = []
                for f in cluster_folder.iterdir():
                    if f.name.startswith("ORIGINAL_"):
                        original = f.name.replace("ORIGINAL_", "", 1)
                    elif f.name.startswith("duplicate_"):
                        dupes.append(f.name.replace("duplicate_", "", 1))
                if original:
                    for d in dupes:
                        duplicate_map[d] = original

    # ── 2. Build file-existence lookups (search all workspace roots) ──
    def _file_path_if_exists(directory, filename):
        """Return relative path if file exists with content, else None."""
        fpath = directory / filename
        if fpath.is_file() and fpath.stat().st_size > 0:
            return str(fpath.relative_to(backend_dir))
        return None

    def _find_file_path(sub_dir_name, filename):
        """Search all workspace roots for a file in a given subdirectory."""
        for ws_root in workspace_roots:
            result = _file_path_if_exists(ws_root / sub_dir_name, filename)
            if result:
                return result
        return None

    # ── 3. Collect all downloaded filenames (across all workspaces) ──
    all_disk_files = set()            # every filename on disk (JPG/PNG only, HEIC already converted)

    image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')

    for ws_root in workspace_roots:
        ws_dl = ws_root / "01_downloaded_from_drive"
        if ws_dl.is_dir():
            for f in ws_dl.iterdir():
                if f.is_dir() or f.name.startswith('_'):
                    continue
                if f.is_file() and f.suffix.lower() in image_exts:
                    all_disk_files.add(f.name)

        ws_del = ws_root / "deliverable"
        if ws_del.is_dir():
            for f in ws_del.iterdir():
                if f.is_dir() or f.name.startswith('_'):
                    continue
                if f.is_file() and f.suffix.lower() in image_exts:
                    all_disk_files.add(f.name)

    for dup_name in duplicate_map:
        all_disk_files.add(dup_name)

    # ── 4. Get DB image data (keyed by filename) ──
    db_images = db.query(Image).all()
    db_by_filename = {}
    for img in db_images:
        db_by_filename[img.filename] = img

    # ── 4b. Load HEIC conversion manifest (created by pipeline, search all workspaces) ──
    heic_manifest = {}
    for ws_root in workspace_roots:
        ws_dl = ws_root / "01_downloaded_from_drive"
        manifest_path = ws_dl / "_heic_conversions.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r') as f:
                    folder_manifest = json.load(f)
                    heic_manifest.update(folder_manifest)
            except Exception:
                pass

    # Build reverse map: jpg_name → heic_original_name
    jpg_to_heic_map = {}
    for jpg_name, info in heic_manifest.items():
        jpg_to_heic_map[jpg_name] = info.get('original_filename', '')

    # Also check DB original_filename column as fallback
    for img in db_images:
        if img.original_filename and img.filename not in jpg_to_heic_map:
            jpg_to_heic_map[img.filename] = img.original_filename

    # Build the canonical set of filenames
    all_filenames = set(all_disk_files)
    for img in db_images:
        all_filenames.add(img.filename)

    # ── 4c. Pre-load Drive metadata (needed for registry fallback) ──
    drive_metadata = {"total_in_drive": 0, "unique_filenames": 0, "duplicate_filename_count": 0, "duplicate_filenames": {}, "scanned_at": ""}
    
    # Track all filenames across folders for cross-folder duplicate detection
    # filename → [{"folder_id": str, "drive_file_id": str}]
    global_filename_map = {}  # filename → list of {folder_id, drive_file_id}
    within_folder_dups = []   # [{filename, folder_id, count}]
    
    # Check per-folder workspaces first
    _folders_dir = workspace / "folders"
    _per_folder_found = False
    if _folders_dir.exists():
        for folder_dir in sorted(_folders_dir.iterdir()):
            if not folder_dir.is_dir():
                continue
            meta_path = folder_dir / "drive_metadata.json"
            if meta_path.exists():
                try:
                    with open(meta_path, 'r') as f:
                        meta = json.load(f)
                    folder_id = folder_dir.name
                    drive_metadata["total_in_drive"] += meta.get("total_in_drive", 0)
                    drive_metadata["unique_filenames"] += meta.get("unique_filenames", 0)
                    drive_metadata["duplicate_filename_count"] += meta.get("duplicate_filename_count", 0)
                    
                    # Track within-folder duplicates
                    for dn, dc in meta.get("duplicate_filenames", {}).items():
                        drive_metadata["duplicate_filenames"][dn] = drive_metadata["duplicate_filenames"].get(dn, 0) + dc
                        within_folder_dups.append({"filename": dn, "folder_id": folder_id, "count": dc})
                    
                    # Track all filenames for cross-folder detection
                    f2d = meta.get("filename_to_drive_id", {})
                    for fname, drive_file_id in f2d.items():
                        if fname not in global_filename_map:
                            global_filename_map[fname] = []
                        global_filename_map[fname].append({"folder_id": folder_id, "drive_file_id": drive_file_id})
                    
                    if meta.get("scanned_at", "") > drive_metadata["scanned_at"]:
                        drive_metadata["scanned_at"] = meta["scanned_at"]
                    _per_folder_found = True
                except Exception:
                    pass
    
    # Fallback: legacy root workspace
    if not _per_folder_found:
        legacy_path = workspace / "drive_metadata.json"
        if legacy_path.exists():
            try:
                with open(legacy_path, 'r') as f:
                    drive_metadata = json.load(f)
                # Also build global_filename_map from legacy metadata
                f2d = drive_metadata.get("filename_to_drive_id", {})
                fid = drive_metadata.get("folder_id", "")
                for fname, did in f2d.items():
                    if fname not in global_filename_map:
                        global_filename_map[fname] = []
                    global_filename_map[fname].append({"folder_id": fid, "drive_file_id": did})
            except Exception:
                pass

    # DB fallback: if no metadata files found, use drive_folders table + images count
    if drive_metadata["total_in_drive"] == 0:
        try:
            from app.models.drive_folder import DriveFolder
            db_folders = db.query(DriveFolder).all()
            for df in db_folders:
                drive_metadata["total_in_drive"] += (df.total_in_drive or 0)
                drive_metadata["unique_filenames"] += (df.downloaded_count or 0)
            # If drive_folders also has 0, use image count as last resort
            if drive_metadata["total_in_drive"] == 0:
                drive_metadata["total_in_drive"] = len(db_images)
            if drive_metadata["unique_filenames"] == 0:
                drive_metadata["unique_filenames"] = len(db_images)
        except Exception:
            drive_metadata["total_in_drive"] = len(db_images)
            drive_metadata["unique_filenames"] = len(db_images)
    
    # Build cross-folder duplicates: filenames that appear in 2+ different folders
    cross_folder_dups = []
    for fname, entries in global_filename_map.items():
        if len(entries) > 1:
            cross_folder_dups.append({
                "filename": fname,
                "folders": [e["folder_id"] for e in entries],
                "drive_file_ids": [e["drive_file_id"] for e in entries],
            })
    cross_folder_dups.sort(key=lambda x: x["filename"])

    # ── 5. Build registry entries ──
    registry = []
    for filename in sorted(all_filenames):
        is_duplicate = filename in duplicate_map
        parent_image = duplicate_map.get(filename, "")
        db_img = db_by_filename.get(filename)
        heic_original = jpg_to_heic_map.get(filename)  # e.g. "IMG_0906.HEIC" if this was converted


        # Blur status
        pipeline_blurred = False
        manually_blurred = False
        annotated_blur_path = ""

        if db_img:
            pipeline_blurred = db_img.compliance_status in ("blurred", "processed", "obfuscated")
            manually_blurred = db_img.manually_blurred or False
            if manually_blurred and db_img.annotated_blur_url:
                annotated_blur_path = db_img.annotated_blur_url
        else:
            pipeline_blurred = bool(db_img and db_img.is_programmatically_blurred)

        if not annotated_blur_path:
            for ws_root in workspace_roots:
                ws_annotated = ws_root / "annotated_blur"
                if ws_annotated.is_dir():
                    for af in ws_annotated.iterdir():
                        if filename in af.name:
                            annotated_blur_path = str(af.relative_to(backend_dir))
                            break
                if annotated_blur_path:
                    break

        # Display filename — show HEIC conversion note if applicable
        display_note = f"(converted from {heic_original})" if heic_original else ""

        # Resolve Drive metadata: prefer DB, fallback to drive_metadata.json via global_filename_map
        source_folder_id = ""
        image_drive_id_val = ""
        if db_img:
            source_folder_id = db_img.source_drive_folder_id or ""
            image_drive_id_val = db_img.image_drive_id or ""

        # Fallback: look up from global_filename_map (populated from drive_metadata.json)
        if not source_folder_id or not image_drive_id_val:
            # Try direct filename first, then HEIC original name
            lookup_names = [filename]
            if heic_original:
                lookup_names.append(heic_original)
            for lookup_name in lookup_names:
                map_entries = global_filename_map.get(lookup_name, [])
                if map_entries:
                    if not source_folder_id:
                        source_folder_id = map_entries[0].get("folder_id", "")
                    if not image_drive_id_val:
                        image_drive_id_val = map_entries[0].get("drive_file_id", "")
                    break

        entry = {
            "filename": filename,
            "db_id": db_img.id if db_img else None,
            "is_unique": not is_duplicate,
            "is_duplicate": is_duplicate,
            "parent_image": parent_image,
            "pipeline_blurred": pipeline_blurred,
            "manually_blurred": manually_blurred,
            "annotated_blur_path": annotated_blur_path,
            "compliance_status": (db_img.compliance_status or "unknown") if db_img else ("blurred" if pipeline_blurred else "unknown"),
            "human_faces_detected": db_img.human_faces_detected if db_img else 0,
            "in_database": db_img is not None,
            "is_ai_generated": db_img.is_ai_generated if db_img else None,
            "human_visible": db_img.human_visible if db_img else None,
            "heic_original": heic_original or "",
            "conversion_note": display_note,
            # DB-tracked format conversion columns
            "original_filename": (db_img.original_filename or "") if db_img else (heic_original or ""),
            "original_format": (db_img.original_format or "") if db_img else ("HEIC" if heic_original else ""),
            "source_drive_folder_id": source_folder_id,
            "image_drive_id": image_drive_id_val,
            # Annotator blur/restore tracking
            "is_blurred_annotator": (db_img.is_blurred_annotator or False) if db_img else False,
            "is_restore_annotator": (db_img.is_restore_annotator or False) if db_img else False,
            # Deliverable image tracking
            "deliverable_image_path": db_img.deliverable_image_path if db_img else None,
            "is_manually_modified": db_img.is_manually_modified if db_img else None,
            # GCS stage info
            "gcs_folder": (db_img.gcs_folder or "input") if db_img else "input",
        }
        registry.append(entry)

    # ── 6. Summary stats (computed BEFORE filtering so they stay constant) ──
    # total_downloaded = sum of unique filenames per folder (reflects actual downloads, not deduped across folders)
    total_downloaded_actual = drive_metadata.get("unique_filenames", 0) or len(registry)
    cross_folder_overlap = len(cross_folder_dups)  # filenames shared across folders (counted once in registry)

    summary = {
        "total_in_drive": drive_metadata.get("total_in_drive", 0),
        "drive_unique_filenames": drive_metadata.get("unique_filenames", 0),
        "drive_duplicate_filenames": drive_metadata.get("duplicate_filename_count", 0),
        "drive_duplicate_details": drive_metadata.get("duplicate_filenames", {}),
        "drive_scanned_at": drive_metadata.get("scanned_at", ""),
        # Structured duplicate info: within-folder and cross-folder
        "within_folder_duplicates": within_folder_dups,       # [{filename, folder_id, count}]
        "cross_folder_duplicates": cross_folder_dups,         # [{filename, folders: [fid1, fid2], drive_file_ids: [...]}]
        "cross_folder_overlap": cross_folder_overlap,
        "total_downloaded": total_downloaded_actual,
        "total_downloaded_unique_names": len(registry),       # distinct filenames on disk (cross-folder dups counted once)
        "total_unique": sum(1 for r in registry if r["is_unique"]),
        "total_duplicate": sum(1 for r in registry if r["is_duplicate"]),
        "total_pipeline_blurred": sum(1 for r in registry if r["pipeline_blurred"]),
        "total_manually_blurred": sum(1 for r in registry if r["manually_blurred"]),
        "total_in_database": sum(1 for r in registry if r["in_database"]),
        "total_clean": sum(1 for r in registry if not r["pipeline_blurred"] and not r["manually_blurred"] and not r["is_duplicate"]),
        "total_delivered": sum(1 for r in registry if r["deliverable_image_path"]),
    }

    # ── 8. Apply filters ──
    if search:
        search_lower = search.lower()
        registry = [r for r in registry if search_lower in r["filename"].lower()]

    if status_filter == "unique":
        registry = [r for r in registry if r["is_unique"]]
    elif status_filter == "duplicate":
        registry = [r for r in registry if r["is_duplicate"]]
    elif status_filter == "blurred":
        registry = [r for r in registry if r["pipeline_blurred"]]
    elif status_filter == "clean":
        registry = [r for r in registry if not r["pipeline_blurred"] and not r["manually_blurred"] and not r["is_duplicate"]]
    elif status_filter == "manually_blurred":
        registry = [r for r in registry if r["manually_blurred"]]

    total = len(registry)

    # ── 9. Paginate ──
    start = (page - 1) * per_page
    end = start + per_page
    page_data = registry[start:end]

    return {
        "summary": summary,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "data": page_data,
    }


# ── Photo Registry Excel Export ──────────────────────────────────

@router.get("/photo-registry/export")
def export_photo_registry_excel(
    search: str = Query("", description="Search by filename"),
    status_filter: str = Query("all", description="all|unique|duplicate|blurred|clean|manually_blurred"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Export the Photo Registry as an Excel (.xlsx) file.
    Applies the same search/filter as the UI but returns ALL matching rows (no pagination).
    Includes GCS paths so external programs can process the images.
    """
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    # Reuse the same registry-building logic from get_photo_registry
    # but without pagination
    registry_response = get_photo_registry(
        page=1,
        per_page=100_000,  # effectively no limit
        search=search,
        status_filter=status_filter,
        db=db,
        _admin=_admin,
    )
    rows = registry_response["data"]
    summary = registry_response["summary"]

    # Resolve GCS bucket name for path construction
    bucket_name = os.getenv("GCS_BUCKET_NAME", "amazon-photo-pets")

    # Build GCS deliverable path for each row
    for row in rows:
        folder_id = row.get("source_drive_folder_id", "")
        filename = row.get("filename", "")
        gcs_folder = "input"  # default

        # Check DB for actual gcs_folder
        db_img = db.query(Image).filter(Image.filename == filename).first() if filename else None
        if db_img and db_img.gcs_folder:
            gcs_folder = db_img.gcs_folder

        if folder_id and filename:
            row["gcs_deliverable_path"] = f"gs://{bucket_name}/{gcs_folder}/{folder_id}/{filename}"
        else:
            row["gcs_deliverable_path"] = ""

    # Create Excel workbook
    wb = Workbook()

    # ── Sheet 1: Summary ──
    ws_summary = wb.active
    ws_summary.title = "Summary"
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    summary_data = [
        ("Metric", "Value"),
        ("Total in GCS", summary.get("total_in_drive", 0)),
        ("Downloaded", summary.get("total_downloaded", 0)),
        ("Unique (After Dedup)", summary.get("total_unique", 0)),
        ("Content Duplicates", summary.get("total_duplicate", 0)),
        ("Pipeline Blurred", summary.get("total_pipeline_blurred", 0)),
        ("Manual Blur", summary.get("total_manually_blurred", 0)),
        ("Clean", summary.get("total_clean", 0)),
        ("Delivered", summary.get("total_delivered", 0)),
        ("In Database", summary.get("total_in_database", 0)),
    ]
    for r_idx, (metric, value) in enumerate(summary_data, 1):
        cell_a = ws_summary.cell(row=r_idx, column=1, value=metric)
        cell_b = ws_summary.cell(row=r_idx, column=2, value=value)
        cell_a.border = thin_border
        cell_b.border = thin_border
        if r_idx == 1:
            cell_a.font = header_font
            cell_a.fill = header_fill
            cell_b.font = header_font
            cell_b.fill = header_fill
    ws_summary.column_dimensions["A"].width = 25
    ws_summary.column_dimensions["B"].width = 15

    # ── Sheet 2: Images ──
    ws_images = wb.create_sheet("Images")
    columns = [
        ("Filename", 30),
        ("Original Filename", 30),
        ("Image ID (Drive/GCS)", 35),
        ("Folder ID", 35),
        ("Status", 12),
        ("Compliance", 14),
        ("Pipeline Blurred", 14),
        ("Manually Blurred", 14),
        ("Is Duplicate", 12),
        ("Parent Image", 25),
        ("GCS Deliverable Path", 55),
        ("Deliverable Status", 18),
        ("Original Format", 14),
        ("In Database", 12),
    ]

    for c_idx, (col_name, width) in enumerate(columns, 1):
        cell = ws_images.cell(row=1, column=c_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border
        ws_images.column_dimensions[chr(64 + c_idx) if c_idx <= 26 else f"A{chr(64 + c_idx - 26)}"].width = width

    # Set column widths for columns > 26 (AA, AB, ...)
    from openpyxl.utils import get_column_letter
    for c_idx, (_, width) in enumerate(columns, 1):
        ws_images.column_dimensions[get_column_letter(c_idx)].width = width

    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    amber_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    red_fill = PatternFill(start_color="FCE4EC", end_color="FCE4EC", fill_type="solid")

    for r_idx, row in enumerate(rows, 2):
        is_dup = row.get("is_duplicate", False)
        is_blurred = row.get("pipeline_blurred", False)

        vals = [
            row.get("filename", ""),
            row.get("original_filename", ""),
            row.get("image_drive_id", ""),
            row.get("source_drive_folder_id", ""),
            "Duplicate" if is_dup else "Unique",
            row.get("compliance_status", ""),
            "Yes" if is_blurred else "No",
            "Yes" if row.get("manually_blurred") else "No",
            "Yes" if is_dup else "No",
            row.get("parent_image", ""),
            row.get("gcs_deliverable_path", ""),
            "Delivered" if row.get("deliverable_image_path") else "Pending",
            row.get("original_format", ""),
            "Yes" if row.get("in_database") else "No",
        ]

        row_fill = amber_fill if is_dup else (red_fill if is_blurred else green_fill)
        for c_idx, val in enumerate(vals, 1):
            cell = ws_images.cell(row=r_idx, column=c_idx, value=val)
            cell.border = thin_border
            cell.fill = row_fill
            cell.alignment = Alignment(vertical="center")

    # Freeze the header row
    ws_images.freeze_panes = "A2"

    # Auto-filter
    ws_images.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"

    # Write to bytes
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename_out = f"photo_registry_{status_filter}_{len(rows)}_images.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename_out}"},
    )


# ── Final Labels ────────────────────────────────────────────────

@router.get("/final-labels")
def get_final_labels(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Get the final_labels table — one row per image with reviewer-approved
    labels for each category, plus reviewer and annotator names.
    """
    query = (
        db.query(FinalLabel)
        .join(Image, Image.id == FinalLabel.image_id)
    )

    if search:
        query = query.filter(
            or_(
                Image.filename.ilike(f"%{search}%"),
                Image.image_drive_id.ilike(f"%{search}%"),
            )
        )

    total = query.count()
    rows = (
        query.order_by(FinalLabel.approved_at.desc().nullslast(), FinalLabel.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    result = []
    for fl in rows:
        img = db.query(Image).filter(Image.id == fl.image_id).first()
        result.append({
            "image_id": fl.image_id,
            "image_drive_id": img.image_drive_id if img else None,
            "filename": img.filename if img else None,
            "image_path": img.image_path if img else None,
            "lighting_variation": fl.lighting_variation,
            "angle_perspective_variation": fl.angle_perspective_variation,
            "environmental_context_variation": fl.environmental_context_variation,
            "occlusion_partial_visibility": fl.occlusion_partial_visibility,
            "activity_motion": fl.activity_motion,
            "multi_pet_disambiguation": fl.multi_pet_disambiguation,
            "reviewer_name": fl.reviewer_name,
            "annotator_name": fl.annotator_name,
            "approved_at": fl.approved_at,
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": result,
    }


@router.post("/final-labels/rebuild")
def rebuild_final_labels(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Rebuild the entire final_labels table from approved annotations.
    Also backfills is_manually_modified, is_programmatically_blurred,
    is_duplicate, parent_image, and image_path on the images table.
    """
    from app.utils.deliverable import populate_final_label, PIPELINE_WORKSPACE

    # 1. Find all images that have ALL annotations approved
    all_images = db.query(Image).all()
    populated = 0
    backfilled = 0

    for img in all_images:
        completed_annotations = (
            db.query(Annotation)
            .filter(
                Annotation.image_id == img.id,
                Annotation.status == "completed",
            )
            .all()
        )

        if completed_annotations and all(a.review_status == "approved" for a in completed_annotations):
            populate_final_label(img.id, db)
            populated += 1

        # 2. Backfill image status columns
        # is_manually_modified: True if annotator/reviewer blurred or restored the image
        img.is_manually_modified = bool(
            img.is_blurred_annotator or img.is_restore_annotator or img.manually_blurred
        )

        # is_programmatically_blurred: True if pipeline blurred (biometric compliance)
        img.is_programmatically_blurred = bool(
            img.compliance_status in ("blurred", "processed", "obfuscated")
            and not img.manually_blurred
        )

        # image_path: resolve current file path
        folder_id = img.source_drive_folder_id or "unknown"
        for sub in ["deliverable", "01_downloaded_from_drive"]:
            candidate = PIPELINE_WORKSPACE / "folders" / folder_id / sub / img.filename
            if candidate.exists():
                img.image_path = str(candidate)
                break

        backfilled += 1

    db.commit()

    return {
        "message": f"Rebuilt final_labels for {populated} images, backfilled {backfilled} image records",
        "final_labels_count": populated,
        "images_backfilled": backfilled,
    }



