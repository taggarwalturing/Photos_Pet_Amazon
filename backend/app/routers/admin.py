import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.category import Category
from app.models.image import Image
from app.models.annotation import Annotation
from app.models.annotator_category import AnnotatorCategory
from app.models.image_assignment import AnnotatorImageAssignment
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
from pydantic import BaseModel


class AssignImagesRequest(BaseModel):
    count: int  # Number of images to assign

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── User Management ──────────────────────────────────────────────

@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.id).all()
    result = []
    for u in users:
        assigned_cat_ids = [ac.category_id for ac in u.assigned_categories]
        
        # Get assigned image count
        assigned_image_count = (
            db.query(AnnotatorImageAssignment)
            .filter(AnnotatorImageAssignment.user_id == u.id)
            .count()
        )
        
        # Get completed annotations count
        completed_annotations = (
            db.query(Annotation)
            .filter(
                Annotation.annotator_id == u.id,
                Annotation.status == "completed",
            )
            .count()
        )
        
        # Total needed = assigned_images * assigned_categories
        total_annotations_needed = assigned_image_count * len(assigned_cat_ids)
        
        # Get improper images marked by this user
        improper_marked_count = (
            db.query(Image)
            .filter(Image.marked_improper_by == u.id)
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
        ))
    return result


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


# ── Image Assignment ──────────────────────────────────────────────

@router.get("/users/{user_id}/images")
def get_user_image_assignments(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get all images assigned to a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    assignments = (
        db.query(AnnotatorImageAssignment)
        .filter(AnnotatorImageAssignment.user_id == user_id)
        .options(joinedload(AnnotatorImageAssignment.image))
        .order_by(AnnotatorImageAssignment.image_id)
        .all()
    )
    
    return {
        "user_id": user_id,
        "username": user.username,
        "assigned_count": len(assignments),
        "images": [
            {
                "id": a.image.id,
                "filename": a.image.filename,
                "url": a.image.url,
                "assigned_at": a.assigned_at,
            }
            for a in assignments
        ],
    }


@router.post("/users/{user_id}/images/assign")
def assign_images_to_user(
    user_id: int,
    payload: AssignImagesRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Assign N unassigned images to a user.
    Images are assigned in order (lowest ID first).
    No duplicate assignments - each image can only be assigned to one user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "annotator":
        raise HTTPException(status_code=400, detail="Can only assign images to annotators")
    
    if payload.count <= 0:
        raise HTTPException(status_code=400, detail="Count must be greater than 0")
    
    # Get IDs of already assigned images
    assigned_image_ids = set(
        row.image_id
        for row in db.query(AnnotatorImageAssignment.image_id).all()
    )
    
    # Get unassigned images (ordered by ID)
    all_images = db.query(Image).order_by(Image.id).all()
    unassigned_images = [img for img in all_images if img.id not in assigned_image_ids]
    
    if len(unassigned_images) == 0:
        raise HTTPException(status_code=400, detail="No unassigned images available")
    
    # Take the requested count (or fewer if not enough available)
    to_assign = unassigned_images[:payload.count]
    
    # Create assignments
    for img in to_assign:
        db.add(AnnotatorImageAssignment(user_id=user_id, image_id=img.id))
    
    db.commit()
    
    return {
        "message": f"Assigned {len(to_assign)} images to {user.username}",
        "assigned_count": len(to_assign),
        "requested_count": payload.count,
        "remaining_unassigned": len(unassigned_images) - len(to_assign),
    }


@router.delete("/users/{user_id}/images/unassign")
def unassign_all_images_from_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Remove all image assignments from a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    count = db.query(AnnotatorImageAssignment).filter(
        AnnotatorImageAssignment.user_id == user_id
    ).delete()
    db.commit()
    
    return {"message": f"Unassigned {count} images from {user.username}", "count": count}


@router.get("/images/assignments")
def get_all_image_assignments(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get assignment summary for all images."""
    total_images = db.query(Image).count()
    
    assignments = (
        db.query(AnnotatorImageAssignment)
        .options(joinedload(AnnotatorImageAssignment.user))
        .all()
    )
    
    # Group by user
    by_user = {}
    for a in assignments:
        if a.user_id not in by_user:
            by_user[a.user_id] = {
                "user_id": a.user_id,
                "username": a.user.username,
                "count": 0,
            }
        by_user[a.user_id]["count"] += 1
    
    return {
        "total_images": total_images,
        "assigned_count": len(assignments),
        "unassigned_count": total_images - len(assignments),
        "by_user": list(by_user.values()),
    }


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

    images = query.all()

    # Compute summary stats (unfiltered) for the filter badges
    total = db.query(Image).count()
    blurred_count = db.query(Image).filter(
        or_(
            Image.compliance_status.in_(["blurred", "processed", "obfuscated"]),
            Image.manually_blurred == True,
        )
    ).count()
    clean_count = db.query(Image).filter(
        Image.compliance_status == "clean",
        or_(Image.manually_blurred == False, Image.manually_blurred.is_(None)),
    ).count()
    manually_blurred_count = db.query(Image).filter(Image.manually_blurred == True).count()
    ai_count = db.query(Image).filter(Image.is_ai_generated == True).count()
    human_visible_count = db.query(Image).filter(Image.human_visible == True).count()
    improper_count = db.query(Image).filter(Image.is_improper == True).count()

    return {
        "summary": {
            "total": total,
            "blurred": blurred_count,
            "clean": clean_count,
            "manually_blurred": manually_blurred_count,
            "ai_generated": ai_count,
            "human_visible": human_visible_count,
            "improper": improper_count,
        },
        "total": len(images),
        "images": [
            {
                "id": img.id,
                "filename": img.filename,
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
            }
        for img in images
        ],
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
                image_url=img.url,
                image_filename=img.filename,
                annotations=entry["annotations"],
                is_blurred=_is_blurred,
                compliance_status=_compliance_status,
                is_using_processed=_is_using_processed,
                manually_blurred=_manually_blurred,
                reviewed_by_username=_reviewed_by,
                reviewed_at=_reviewed_at,
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

    return {
        "total_completed": total_images,
        "pending_review": pending_images,
        "approved": approved_images,
    }


@router.put("/review/{annotation_id}/approve")
def approve_annotation(
    annotation_id: int,
    payload: ReviewApproveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Approve an annotation as-is."""
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    annotation.status = "completed"  # Ensure status is completed when approved
    annotation.review_status = "approved"
    annotation.review_note = payload.review_note
    annotation.reviewed_by = admin.id
    annotation.reviewed_at = datetime.now(timezone.utc)
    db.commit()
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


# ── Annotation Log (Time Tracking Table) ─────────────────────────

@router.get("/annotation-log")
def get_annotation_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    annotator_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None),  # all, initial, rework, approved, pending
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Get a comprehensive lifecycle log of annotations.
    Each lifecycle event (initial annotation, rework) is shown as a separate row.
    Returns: image_name, annotator_name, categories, event_type (Initial/Rework), time_taken, reviewer_name, status
    """
    from sqlalchemy import func
    
    # Get distinct (image_id, annotator_id) pairs with completed annotations
    base_query = (
        db.query(
            Annotation.image_id,
            Annotation.annotator_id,
        )
        .filter(Annotation.status == "completed")
        .group_by(Annotation.image_id, Annotation.annotator_id)
    )
    
    if annotator_id:
        base_query = base_query.filter(Annotation.annotator_id == annotator_id)
    
    pairs = base_query.all()
    
    # Build lifecycle entries for each image+annotator pair
    all_entries = []
    
    for img_id, ann_id in pairs:
        # Get all annotations for this image+annotator pair
        annotations = (
            db.query(Annotation)
            .filter(
                Annotation.image_id == img_id,
                Annotation.annotator_id == ann_id,
                Annotation.status == "completed",
            )
            .options(
                joinedload(Annotation.image),
                joinedload(Annotation.annotator),
                joinedload(Annotation.category),
                joinedload(Annotation.reviewer),
            )
            .all()
        )
        
        if not annotations:
            continue
        
        first_ann = annotations[0]
        categories = [a.category.name for a in annotations]
        
        # Get time values
        initial_time = max(a.time_spent_seconds or 0 for a in annotations)
        rework_time = max(a.rework_time_seconds or 0 for a in annotations)
        has_rework = any(a.is_rework for a in annotations) or rework_time > 0
        
        # Determine current status
        all_approved = all(a.review_status == "approved" for a in annotations)
        any_rework_requested = any(a.review_status == "rework_requested" for a in annotations)
        any_rework_completed = any(a.review_status == "rework_completed" for a in annotations)
        
        # Get reviewer info
        reviewer = next((a.reviewer for a in annotations if a.reviewer), None)
        reviewed_at = next((a.reviewed_at for a in annotations if a.reviewed_at), None)
        
        # Build base entry data
        base_entry = {
            "image_id": img_id,
            "image_name": first_ann.image.filename,
            "image_url": first_ann.image.url,
            "annotator_id": ann_id,
            "annotator_name": first_ann.annotator.username,
            "categories": categories,
            "category_count": len(categories),
        }
        
        # Helper to check filter
        def should_include(event_type, status_val):
            if status_filter is None or status_filter == "all":
                return True
            if status_filter == "initial" and event_type == "Annotation":
                return True
            if status_filter == "rework" and event_type == "Rework":
                return True
            if status_filter == "approved" and event_type == "Approval":
                return True
            if status_filter == "pending" and status_val == "Pending Review":
                return True
            return False
        
        # ── Event 1: Initial Annotation (always exists) ──
        initial_entry = {
            **base_entry,
            "event_type": "Annotation",
            "time_taken_seconds": initial_time,
            "actor_name": first_ann.annotator.username,
            "actor_role": "annotator",
            "status": "Submitted",
            "created_at": min(a.created_at for a in annotations),
            "sort_key": min(a.created_at for a in annotations),
        }
        if should_include("Annotation", "Submitted"):
            all_entries.append(initial_entry)
        
        # ── Event 2: First Review (if reviewed - either sent for rework or approved directly) ──
        if has_rework and reviewer:
            # Reviewer sent it for rework
            review_sent_rework_entry = {
                **base_entry,
                "event_type": "Review",
                "time_taken_seconds": 0,  # Review doesn't have time
                "actor_name": reviewer.username,
                "actor_role": "reviewer",
                "status": "Sent for Rework",
                "created_at": reviewed_at or min(a.created_at for a in annotations),
                "sort_key": reviewed_at or min(a.created_at for a in annotations),
            }
            if should_include("Review", "Sent for Rework"):
                all_entries.append(review_sent_rework_entry)
        
        # ── Event 3: Rework Submission (only if rework was done) ──
        if has_rework and (rework_time > 0 or any_rework_completed or all_approved):
            rework_status = "Submitted"
            if any_rework_requested:
                rework_status = "Sent for Rework Again"
            
            rework_entry = {
                **base_entry,
                "event_type": "Rework",
                "time_taken_seconds": rework_time,
                "actor_name": first_ann.annotator.username,
                "actor_role": "annotator",
                "status": rework_status,
                "created_at": max(a.updated_at for a in annotations),
                "sort_key": max(a.updated_at for a in annotations),
            }
            if should_include("Rework", rework_status):
                all_entries.append(rework_entry)
        
        # ── Event 4: Approval (if approved by reviewer) ──
        if all_approved and reviewer:
            approval_entry = {
                **base_entry,
                "event_type": "Approval",
                "time_taken_seconds": 0,  # Approval doesn't have time
                "actor_name": reviewer.username,
                "actor_role": "reviewer",
                "status": "Approved",
                "created_at": reviewed_at or max(a.updated_at for a in annotations),
                "sort_key": reviewed_at or max(a.updated_at for a in annotations),
            }
            if should_include("Approval", "Approved"):
                all_entries.append(approval_entry)
        
        # ── Pending Review (if not yet reviewed) ──
        if not all_approved and not has_rework and not any_rework_requested:
            # Still pending initial review
            pending_entry = {
                **base_entry,
                "event_type": "Pending",
                "time_taken_seconds": 0,
                "actor_name": "-",
                "actor_role": "reviewer",
                "status": "Pending Review",
                "created_at": max(a.updated_at for a in annotations),
                "sort_key": max(a.updated_at for a in annotations),
            }
            if should_include("Pending", "Pending Review"):
                all_entries.append(pending_entry)
    
    # Sort by sort_key descending (most recent first)
    all_entries.sort(key=lambda x: x["sort_key"], reverse=True)
    
    # Paginate
    total = len(all_entries)
    start = (page - 1) * page_size
    paginated = all_entries[start : start + page_size]
    
    # Remove sort_key from response
    for entry in paginated:
        del entry["sort_key"]
    
    return {
        "annotations": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/annotation-log/summary")
def get_annotation_log_summary(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get summary statistics for the annotation log (grouped by image+annotator)."""
    from sqlalchemy import func, distinct
    
    # Total unique image+annotator pairs with completed annotations
    total_image_annotator_pairs = (
        db.query(func.count(distinct(func.concat(Annotation.image_id, '-', Annotation.annotator_id))))
        .filter(Annotation.status == "completed")
        .scalar() or 0
    )
    
    # Get all completed annotations for detailed stats
    completed_annotations = (
        db.query(Annotation)
        .filter(Annotation.status == "completed")
        .all()
    )
    
    # Group by image+annotator to calculate stats
    pairs_data = {}
    for a in completed_annotations:
        key = (a.image_id, a.annotator_id)
        if key not in pairs_data:
            pairs_data[key] = {
                'has_rework': False,
                'all_approved': True,
                'time_spent': 0,
                'rework_time': 0,
            }
        if a.is_rework:
            pairs_data[key]['has_rework'] = True
        if a.review_status != "approved":
            pairs_data[key]['all_approved'] = False
        pairs_data[key]['time_spent'] = max(pairs_data[key]['time_spent'], a.time_spent_seconds or 0)
        pairs_data[key]['rework_time'] = max(pairs_data[key]['rework_time'], a.rework_time_seconds or 0)
    
    total_reworks = sum(1 for p in pairs_data.values() if p['has_rework'])
    total_approved = sum(1 for p in pairs_data.values() if p['all_approved'])
    total_pending = sum(1 for p in pairs_data.values() if not p['all_approved'] and not p['has_rework'])
    
    # Calculate average times
    times_spent = [p['time_spent'] for p in pairs_data.values() if p['time_spent'] > 0]
    rework_times = [p['rework_time'] for p in pairs_data.values() if p['rework_time'] > 0]
    
    avg_annotation_time = sum(times_spent) / len(times_spent) if times_spent else 0
    avg_rework_time = sum(rework_times) / len(rework_times) if rework_times else 0
    
    return {
        "total_annotations": total_image_annotator_pairs,
        "total_reworks": total_reworks,
        "total_approved": total_approved,
        "total_pending": total_pending,
        "avg_annotation_time_seconds": round(avg_annotation_time),
        "avg_rework_time_seconds": round(avg_rework_time),
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

    backend_dir = Path(__file__).parent.parent.parent
    workspace = backend_dir / "master_pipeline" / "pipeline_workspace"

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

        ws_uq = ws_root / "02_unique_images"
        if ws_uq.is_dir():
            for f in ws_uq.iterdir():
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

        # Paths (search across all workspace roots)
        original_path = (
            _find_file_path("01_downloaded_from_drive", filename)
            or _find_file_path("02_unique_images", filename)
            or ""
        )

        # HEIC original path (in _heic_originals subfolder)
        heic_original_path = ""
        if heic_original:
            for ws_root in workspace_roots:
                heic_originals_dir = ws_root / "01_downloaded_from_drive" / "_heic_originals"
                result = _file_path_if_exists(heic_originals_dir, heic_original)
                if result:
                    heic_original_path = result
                    break

        processed_path = (
            _find_file_path("04_final_output", filename)
            or _find_file_path(os.path.join("03_biometric_processed", "blurred"), filename)
            or _find_file_path(os.path.join("03_biometric_processed", "clean"), filename)
            or ""
        )

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
            pipeline_blurred = _find_file_path(os.path.join("03_biometric_processed", "blurred"), filename) is not None

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
            "original_path": original_path,
            "processed_path": processed_path,
            "pipeline_blurred": pipeline_blurred,
            "manually_blurred": manually_blurred,
            "annotated_blur_path": annotated_blur_path,
            "compliance_status": (db_img.compliance_status or "unknown") if db_img else ("blurred" if pipeline_blurred else "unknown"),
            "human_faces_detected": db_img.human_faces_detected if db_img else 0,
            "in_database": db_img is not None,
            "is_ai_generated": db_img.is_ai_generated if db_img else None,
            "human_visible": db_img.human_visible if db_img else None,
            "heic_original": heic_original or "",
            "heic_original_path": heic_original_path if heic_original else "",
            "conversion_note": display_note,
            # DB-tracked format conversion columns
            "original_filename": (db_img.original_filename or "") if db_img else (heic_original or ""),
            "original_format": (db_img.original_format or "") if db_img else ("HEIC" if heic_original else ""),
            "source_drive_folder_id": source_folder_id,
            "image_drive_id": image_drive_id_val,
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

