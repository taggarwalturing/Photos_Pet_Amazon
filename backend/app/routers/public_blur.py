import io
import json
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from app.utils.blur import blur_image_regions

router = APIRouter(prefix="/public", tags=["Public Blur"])


@router.post("/blur")
async def public_blur(
    file: UploadFile = File(...),
    regions: str = Form(...),
):
    """
    Public (no-auth) endpoint: upload an image and blur specified regions.
    Returns the blurred image as a downloadable JPEG.

    - file: uploaded image
    - regions: JSON string, e.g. [{"x":0.1,"y":0.2,"width":0.3,"height":0.4}]
    """
    try:
        region_list = json.loads(regions)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in regions field")

    if not isinstance(region_list, list) or not region_list:
        raise HTTPException(status_code=400, detail="regions must be a non-empty array")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    try:
        blurred = blur_image_regions(image_bytes, region_list)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to process image: {e}")

    safe_name = "".join(c if c.isascii() and c.isprintable() else "_" for c in (file.filename or "image"))
    return StreamingResponse(
        io.BytesIO(blurred),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'attachment; filename="blurred_{safe_name}.jpg"',
        },
    )
