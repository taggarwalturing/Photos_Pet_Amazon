"""
Admin endpoints for compliance image management
- Revert to original
- Re-process with OpenAI
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os
from pathlib import Path
import subprocess
import sys

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.image import Image
from app.models.annotation import Annotation

router = APIRouter(prefix="/admin/compliance/images", tags=["Compliance Management"])


class RevertRequest(BaseModel):
    reason: Optional[str] = None


class ReprocessRequest(BaseModel):
    use_openai: bool = True
    reason: Optional[str] = None


@router.post("/{image_id}/revert")
def revert_to_original(
    image_id: int,
    payload: RevertRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Revert image to original (unprocessed) version.
    Use this when the pipeline wrongly blurred an animal or made errors.
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if not image.original_url:
        raise HTTPException(
            status_code=400,
            detail="No original version available for this image"
        )
    
    # Switch to original
    image.url = image.original_url
    image.is_using_processed = False
    image.compliance_status = "reverted"
    
    # Log the action
    log_entry = f"\n[REVERTED by {admin.username}] Reason: {payload.reason or 'N/A'}"
    image.processing_log = (image.processing_log or "") + log_entry
    
    db.commit()
    
    return {
        "success": True,
        "message": "Image reverted to original version",
        "image_id": image_id,
        "now_using": "original",
        "reverted_by": admin.username
    }


@router.post("/{image_id}/reprocess")
async def reprocess_with_openai(
    image_id: int,
    payload: ReprocessRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Re-process image with OpenAI Vision API for enhanced face detection.
    Always uses OpenAI (no local pipeline option).
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Always use OpenAI for reprocessing
    try:
        result = await detect_and_blur_with_openai(image)
        
        image.processed_url = result['processed_url']
        image.url = result['processed_url']
        image.is_using_processed = True
        image.compliance_status = "reprocessed_openai"
        image.processing_method = "openai"
        image.human_faces_detected = result['faces_detected']
        
        log_entry = f"\n[REPROCESSED with OpenAI by {admin.username}] Faces: {result['faces_detected']}, Reason: {payload.reason or 'N/A'}"
        image.processing_log = (image.processing_log or "") + log_entry
        
        db.commit()
        
        return {
            "success": True,
            "message": "Image reprocessed with OpenAI",
            "image_id": image_id,
            "method": "openai",
            "faces_detected": result['faces_detected'],
            "reprocessed_by": admin.username
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI processing failed: {str(e)}"
        )


@router.get("/{image_id}/versions")
def get_image_versions(
    image_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Get both original and processed versions of an image
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    return {
        "image_id": image_id,
        "filename": image.filename,
        "current_url": image.url,
        "original_url": image.original_url,
        "processed_url": image.processed_url,
        "is_using_processed": image.is_using_processed,
        "processing_method": image.processing_method,
        "compliance_status": image.compliance_status,
        "human_faces_detected": image.human_faces_detected,
        "processing_log": image.processing_log
    }


# Helper functions

async def detect_and_blur_with_openai(image: Image) -> dict:
    """
    Use OpenAI Vision API to detect faces and blur them
    Downloads from Google Drive, processes, and uploads back
    """
    import base64
    import httpx
    from PIL import Image as PILImage, ImageFilter
    import io
    import re
    from app.config import settings
    from app.utils.gdrive_upload import upload_image_bytes_to_drive, find_or_create_folder
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    # Get OpenAI API key
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise Exception("OPENAI_API_KEY not configured")
    
    # Download the original image from Google Drive
    original_url = image.original_url or image.url
    gdrive_match = re.search(r'id=([a-zA-Z0-9_-]+)', original_url)
    if not gdrive_match:
        raise Exception("Invalid image URL - must be Google Drive URL")
    
    file_id = gdrive_match.group(1)
    
    # Download from Google Drive
    creds_dict = settings.google_service_account_credentials
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=credentials)
    
    request = service.files().get_media(fileId=file_id)
    image_data = io.BytesIO()
    downloader = httpx.get(
        f'https://www.googleapis.com/drive/v3/files/{file_id}?alt=media',
        headers={'Authorization': f'Bearer {credentials.token}'},
        timeout=60.0
    )
    image_data = downloader.content
    
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    # Call OpenAI Vision API to detect faces
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",  # Latest vision model
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Detect all human faces in this image. Return a JSON array of face bounding boxes in format: [{\"x\": x_coord, \"y\": y_coord, \"width\": width, \"height\": height}]. Only detect HUMAN faces, not animal faces. If no human faces, return empty array []."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            }
        )
    
    if response.status_code != 200:
        raise Exception(f"OpenAI API error: {response.text}")
    
    result = response.json()
    faces_data = result['choices'][0]['message']['content']
    
    # Parse face coordinates
    import json
    try:
        faces = json.loads(faces_data)
    except:
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```json\n(.+?)\n```', faces_data, re.DOTALL)
        if json_match:
            faces = json.loads(json_match.group(1))
        else:
            faces = []
    
    # Blur the faces
    if faces:
        pil_image = PILImage.open(io.BytesIO(image_data))
        
        for face in faces:
            # Extract face region and blur it
            x, y, w, h = face['x'], face['y'], face['width'], face['height']
            
            # Add padding
            padding = int(max(w, h) * 0.2)
            x1 = max(0, x - padding)
            y1 = max(0, y - padding)
            x2 = min(pil_image.width, x + w + padding)
            y2 = min(pil_image.height, y + h + padding)
            
            # Crop, blur, and paste back
            face_region = pil_image.crop((x1, y1, x2, y2))
            blurred_face = face_region.filter(ImageFilter.GaussianBlur(radius=20))
            pil_image.paste(blurred_face, (x1, y1))
        
        # Save to bytes
        output_buffer = io.BytesIO()
        pil_image.save(output_buffer, format='JPEG', quality=85)
        processed_bytes = output_buffer.getvalue()
        
        # Upload to Google Drive
        main_folder_id = settings.GOOGLE_DRIVE_FOLDER_ID
        processed_folder_id = find_or_create_folder("processed_images", main_folder_id)
        openai_folder_id = find_or_create_folder("openai_reprocessed", processed_folder_id)
        
        filename = f"openai_{image.filename}"
        upload_result = upload_image_bytes_to_drive(
            processed_bytes,
            openai_folder_id,
            filename,
            'image/jpeg'
        )
        
        return {
            'processed_url': upload_result['url'],
            'faces_detected': len(faces)
        }
    else:
        # No faces detected - return original
        return {
            'processed_url': original_url,
            'faces_detected': 0
        }
