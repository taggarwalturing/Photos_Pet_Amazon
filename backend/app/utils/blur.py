import io
import cv2
import numpy as np
from roi_blur import blur_boxes


def blur_image_regions(image_bytes: bytes, regions: list[dict], ksize: int = 51, sigma: float = 40.0) -> bytes:
    """
    Apply Gaussian blur to specified rectangular regions of an image using roi-blur.

    Args:
        image_bytes: Raw bytes of the source image.
        regions: List of dicts with normalized (0.0-1.0) coordinates:
                 {"x": float, "y": float, "width": float, "height": float}
        ksize: Blur kernel size (positive odd integer).
        sigma: Blur strength/sigma parameter.

    Returns:
        JPEG bytes of the image with blurred regions.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    h, w = img.shape[:2]

    boxes = []
    for region in regions:
        rx = int(region["x"] * w)
        ry = int(region["y"] * h)
        rw = int(region["width"] * w)
        rh = int(region["height"] * h)

        rx = max(0, min(rx, w))
        ry = max(0, min(ry, h))
        rw = max(0, min(rw, w - rx))
        rh = max(0, min(rh, h - ry))

        if rw > 0 and rh > 0:
            boxes.append((rx, ry, rw, rh))

    if not boxes:
        raise ValueError("No valid regions to blur")

    result = blur_boxes(img, boxes, ksize=ksize, sigma=sigma)

    _, buf = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()
