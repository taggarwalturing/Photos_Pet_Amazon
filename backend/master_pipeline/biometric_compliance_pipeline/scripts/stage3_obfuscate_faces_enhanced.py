#!/usr/bin/env python3
"""
Stage 3: Enhanced Face Obfuscation Module
==========================================
Uses EgoBlur-style context-preserving anonymization for professional results.

Methods available:
- egoblur: Context-preserving blur (recommended for production)
- gaussian: Standard Gaussian blur (fast, compliance-focused)
- pixelate: Mosaic effect
- solid: Maximum privacy with solid color overlay
"""

import cv2
import json
import numpy as np
from pathlib import Path
from tqdm import tqdm
import shutil

# Register HEIF/HEIC support for Pillow
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass  # HEIF support optional


def load_config():
    """Load configuration from settings.env"""
    config = {}
    env_file = Path(__file__).parent.parent / 'config' / 'settings.env'
    
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.split('#')[0].strip()
                config[key] = value
    
    return config


def load_face_detector(model_name='buffalo_sc', det_size=640):
    """Load InsightFace for verification."""
    try:
        import insightface
        from insightface.app import FaceAnalysis
    except ImportError:
        print("❌ Error: insightface not installed")
        print("   Please install: pip install insightface onnxruntime")
        exit(1)
    
    app = FaceAnalysis(name=model_name, providers=['CPUExecutionProvider'])
    app.prepare(ctx_id=0, det_size=(det_size, det_size))
    return app


def load_animal_detector():
    """Load YOLO for cat/dog detection."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ Error: ultralytics not installed")
        print("   Please install: pip install ultralytics")
        exit(1)
    
    # YOLOv8 has classes: cat (15), dog (16)
    model = YOLO('yolov8n.pt')  # Nano model for speed
    return model


class EgoBlurAnonymizer:
    """EgoBlur-style context-preserving anonymization."""
    
    @staticmethod
    def apply(image: np.ndarray, mask: np.ndarray, intensity: float = 1.0) -> np.ndarray:
        """
        Apply EgoBlur-style anonymization to face region.
        
        Features:
        - Adaptive kernel sizing based on face size
        - Multi-pass blur (Gaussian + Bilateral)
        - Soft mask blending for seamless edges
        - Context preservation (background stays sharp)
        
        Args:
            image: Input image
            mask: Binary mask of face region
            intensity: Blur intensity (1.0 = default, higher = more blur)
        
        Returns:
            Anonymized image
        """
        result = image.copy()
        
        mask_area = np.sum(mask > 127)
        if mask_area == 0:
            return result
        
        # Adaptive kernel sizing
        face_size = np.sqrt(mask_area)
        base_kernel = max(31, int(face_size * 0.15 * intensity))
        base_kernel = base_kernel if base_kernel % 2 == 1 else base_kernel + 1
        
        # Create soft mask with feathered edges
        soft_mask = cv2.GaussianBlur(mask.astype(np.float32), (21, 21), 10) / 255.0
        
        # Multi-pass blur for context preservation
        blurred = cv2.GaussianBlur(image, (base_kernel, base_kernel), base_kernel // 3)
        blurred = cv2.bilateralFilter(blurred, 15, 80, 80)  # Edge-aware
        
        # Additional smoothing pass
        kernel_small = max(15, base_kernel // 2)
        kernel_small = kernel_small if kernel_small % 2 == 1 else kernel_small + 1
        blurred = cv2.GaussianBlur(blurred, (kernel_small, kernel_small), kernel_small // 4)
        
        # Blend with soft mask
        for c in range(3):
            result[:, :, c] = (
                blurred[:, :, c] * soft_mask + 
                image[:, :, c] * (1 - soft_mask)
            ).astype(np.uint8)
        
        return result


class GaussianAnonymizer:
    """Standard Gaussian blur anonymization (compliance-focused)."""
    
    @staticmethod
    def apply(image: np.ndarray, mask: np.ndarray, kernel_size: int = 99, sigma: float = 30) -> np.ndarray:
        """
        Apply strong Gaussian blur for regulatory compliance.
        
        Args:
            image: Input image
            mask: Binary mask of face region
            kernel_size: Blur kernel size (larger = more blur)
            sigma: Gaussian sigma value
        
        Returns:
            Anonymized image
        """
        result = image.copy()
        
        kernel_size = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
        soft_mask = cv2.GaussianBlur(mask.astype(np.float32), (15, 15), 7) / 255.0
        
        blurred = cv2.GaussianBlur(image, (kernel_size, kernel_size), sigma)
        
        for c in range(3):
            result[:, :, c] = (
                blurred[:, :, c] * soft_mask + 
                image[:, :, c] * (1 - soft_mask)
            ).astype(np.uint8)
        
        return result


class PixelateAnonymizer:
    """Pixelation/mosaic anonymization."""
    
    @staticmethod
    def apply(image: np.ndarray, mask: np.ndarray, pixel_size: int = 12) -> np.ndarray:
        """Apply pixelation effect to face region."""
        result = image.copy()
        
        coords = np.where(mask > 127)
        if len(coords[0]) == 0:
            return result
        
        y_min, y_max = coords[0].min(), coords[0].max()
        x_min, x_max = coords[1].min(), coords[1].max()
        
        region = image[y_min:y_max, x_min:x_max]
        region_h, region_w = region.shape[:2]
        
        if region_h < pixel_size or region_w < pixel_size:
            return GaussianAnonymizer.apply(image, mask)
        
        small = cv2.resize(region, (region_w // pixel_size, region_h // pixel_size), 
                          interpolation=cv2.INTER_LINEAR)
        pixelated = cv2.resize(small, (region_w, region_h), 
                              interpolation=cv2.INTER_NEAREST)
        
        local_mask = mask[y_min:y_max, x_min:x_max].astype(np.float32) / 255.0
        local_mask = cv2.GaussianBlur(local_mask, (11, 11), 5)
        
        for c in range(3):
            result[y_min:y_max, x_min:x_max, c] = (
                pixelated[:, :, c] * local_mask + 
                region[:, :, c] * (1 - local_mask)
            ).astype(np.uint8)
        
        return result


class SolidAnonymizer:
    """Solid color overlay anonymization (maximum privacy)."""
    
    @staticmethod
    def apply(image: np.ndarray, mask: np.ndarray, color=(128, 128, 128)) -> np.ndarray:
        """Apply solid color overlay to face region."""
        result = image.copy()
        
        soft_mask = cv2.GaussianBlur(mask.astype(np.float32), (21, 21), 10) / 255.0
        overlay = np.full_like(image, color)
        
        for c in range(3):
            result[:, :, c] = (
                overlay[:, :, c] * soft_mask + 
                image[:, :, c] * (1 - soft_mask)
            ).astype(np.uint8)
        
        return result


def create_face_mask(image, bbox, padding_ratio=0.3):
    """Create elliptical mask for face region."""
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    
    x, y, fw, fh = bbox
    
    # Add padding
    pad_w = int(fw * padding_ratio)
    pad_h = int(fh * padding_ratio)
    
    center_x = x + fw // 2
    center_y = y + fh // 2
    
    # Ellipse for natural face shape
    axes = ((fw + pad_w) // 2, int((fh + pad_h) * 0.55))
    
    cv2.ellipse(mask, (center_x, center_y), axes, 0, 0, 360, 255, -1)
    
    # Smooth edges
    mask = cv2.GaussianBlur(mask, (15, 15), 7)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    
    return mask


def check_overlap_with_animals(face_bbox, animal_boxes, iou_threshold=0.3):
    """
    Check if a face bbox overlaps significantly with any animal bounding box.
    
    Args:
        face_bbox: (x1, y1, x2, y2) face bounding box
        animal_boxes: List of (x1, y1, x2, y2) animal bounding boxes
        iou_threshold: Minimum IoU to consider overlap
    
    Returns:
        True if face overlaps with an animal, False otherwise
    """
    if not animal_boxes:
        return False
    
    fx1, fy1, fx2, fy2 = face_bbox
    
    for ax1, ay1, ax2, ay2 in animal_boxes:
        # Calculate intersection
        ix1 = max(fx1, ax1)
        iy1 = max(fy1, ay1)
        ix2 = min(fx2, ax2)
        iy2 = min(fy2, ay2)
        
        if ix2 > ix1 and iy2 > iy1:
            intersection = (ix2 - ix1) * (iy2 - iy1)
            face_area = (fx2 - fx1) * (fy2 - fy1)
            
            # Calculate IoU (intersection over face area)
            iou = intersection / face_area if face_area > 0 else 0
            
            if iou > iou_threshold:
                return True
    
    return False


def obfuscate_image(img_path, output_dir, app, anonymizer, method_name, animal_detector=None, **kwargs):
    """Obfuscate all faces in an image, excluding animal faces."""
    # Try to load image with OpenCV
    img = cv2.imread(str(img_path))
    
    # If OpenCV fails, try with PIL (handles HEIC/HEIF and other formats)
    if img is None:
        try:
            from PIL import Image
            pil_img = Image.open(img_path)
            # Convert to RGB if needed
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            # Convert PIL to OpenCV format (BGR)
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            # Image loading failed completely
            return {
                'action': 'failed',
                'error': f'Failed to load image: {str(e)}',
                'face_count': 0
            }
    
    h, w = img.shape[:2]
    
    # Detect animals (cats and dogs) if animal filter is enabled
    animal_boxes = []
    if animal_detector is not None and kwargs.get('filter_animals', True):
        try:
            results = animal_detector(img, verbose=False)
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    # COCO classes: cat=15, dog=16
                    if cls in [15, 16] and conf > 0.5:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        animal_boxes.append((x1, y1, x2, y2))
        except Exception as e:
            print(f"⚠️  Animal detection failed: {e}")
    
    # Detect faces for verification
    try:
        faces = app.get(img)
    except:
        faces = []
    
    if not faces:
        # No faces - but we still need to save/convert if needed
        output_name = img_path.name
        if img_path.suffix.lower() in {'.heic', '.heif', '.avif'}:
            output_name = img_path.stem + '.jpg'
        
        return {
            'action': 'no_face',
            'face_count': 0,
            'verification': 'skipped',
            'animals_detected': len(animal_boxes),
            'output_name': output_name
        }
    
    result = img.copy()
    obfuscated_count = 0
    skipped_count = 0
    
    # Obfuscate each face (except those overlapping with animals)
    for face in faces:
        if not hasattr(face, 'bbox'):
            continue
        
        x1, y1, x2, y2 = map(int, face.bbox)
        
        # Check if this face overlaps with any detected animal
        if check_overlap_with_animals((x1, y1, x2, y2), animal_boxes, 
                                      iou_threshold=kwargs.get('animal_iou_threshold', 0.3)):
            skipped_count += 1
            continue  # Skip obfuscating this face (it's likely an animal)
        
        bbox = (x1, y1, x2 - x1, y2 - y1)
        
        # Create mask
        mask = create_face_mask(img, bbox, padding_ratio=kwargs.get('padding_ratio', 0.3))
        
        # Apply anonymization
        if method_name == 'egoblur':
            result = anonymizer.apply(result, mask, intensity=kwargs.get('intensity', 1.0))
        elif method_name == 'gaussian':
            result = anonymizer.apply(result, mask, 
                                     kernel_size=kwargs.get('kernel_size', 99),
                                     sigma=kwargs.get('sigma', 30))
        elif method_name == 'pixelate':
            result = anonymizer.apply(result, mask, pixel_size=kwargs.get('pixel_size', 12))
        elif method_name == 'solid':
            result = anonymizer.apply(result, mask, color=kwargs.get('color', (128, 128, 128)))
        
        obfuscated_count += 1
    
    # Re-verify: check if faces still detectable
    try:
        verify_faces = app.get(result)
        max_confidence = max([f.det_score for f in verify_faces], default=0) if verify_faces else 0
        verification_threshold = kwargs.get('verification_threshold', 0.3)
        
        if max_confidence > verification_threshold:
            verification = 'failed'
            action = 'qa_required'
        else:
            verification = 'passed'
            action = 'obfuscated'
    except:
        verification = 'error'
        action = 'qa_required'
    
    # Save output - convert unsupported formats to JPG
    # OpenCV can't write HEIC/HEIF/AVIF, so convert these to JPG
    output_name = img_path.name
    if img_path.suffix.lower() in {'.heic', '.heif', '.avif'}:
        output_name = img_path.stem + '.jpg'
    
    output_path = Path(output_dir) / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), result)
    
    return {
        'action': action,
        'face_count': len(faces),
        'faces_obfuscated': obfuscated_count,
        'faces_skipped_animal': skipped_count,
        'animals_detected': len(animal_boxes),
        'verification': verification,
        'max_confidence_after': float(max_confidence) if 'max_confidence' in locals() else 0,
        'output_name': output_name  # Track the actual output filename
    }


def run_obfuscation(input_dir, obfuscated_dir, qa_dir, output_file, config):
    """Run face obfuscation on all images."""
    print("=" * 60)
    print("STAGE 3: ENHANCED FACE OBFUSCATION")
    print("=" * 60)
    
    # Load detector for verification
    print("\n🔄 Loading face detector for verification...")
    model_name = config.get('FACE_DETECTOR_MODEL', 'buffalo_sc')
    det_size = int(config.get('DETECTION_SIZE', 640))
    app = load_face_detector(model_name, det_size)
    
    # Load animal detector if enabled
    filter_animals = config.get('FILTER_ANIMAL_FACES', 'True').lower() == 'true'
    animal_detector = None
    if filter_animals:
        print("🐾 Loading YOLO for cat/dog detection...")
        animal_detector = load_animal_detector()
        print("✓ Animal filter enabled (will skip cat/dog faces)")
    else:
        print("⚠️  Animal filter disabled")
    
    # Get anonymization method
    method_name = config.get('ANONYMIZATION_METHOD', 'gaussian').lower()
    
    # Initialize anonymizer
    if method_name == 'egoblur':
        anonymizer = EgoBlurAnonymizer()
        print(f"✓ Anonymization: EgoBlur (context-preserving)")
    elif method_name == 'pixelate':
        anonymizer = PixelateAnonymizer()
        print(f"✓ Anonymization: Pixelate (mosaic)")
    elif method_name == 'solid':
        anonymizer = SolidAnonymizer()
        print(f"✓ Anonymization: Solid overlay (maximum privacy)")
    else:  # gaussian (default for compliance)
        anonymizer = GaussianAnonymizer()
        print(f"✓ Anonymization: Gaussian blur (compliance-focused)")
    
    # Get parameters
    kwargs = {
        'intensity': float(config.get('EGOBLUR_INTENSITY', 1.0)),
        'kernel_size': int(config.get('BLUR_KERNEL_SIZE', 99)),
        'sigma': float(config.get('BLUR_SIGMA', 30)),
        'pixel_size': int(config.get('PIXELATE_SIZE', 12)),
        'padding_ratio': float(config.get('FACE_PADDING_RATIO', 0.3)),
        'verification_threshold': float(config.get('VERIFICATION_THRESHOLD', 0.3)),
        'filter_animals': filter_animals,
        'animal_iou_threshold': float(config.get('ANIMAL_IOU_THRESHOLD', 0.3))
    }
    
    # Get images
    input_path = Path(input_dir)
    images = list(input_path.glob('**/*'))
    images = [p for p in images if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.heic', '.heif'}]
    
    print(f"\n📂 Processing {len(images)} images...\n")
    
    # Process images
    results = []
    stats = {'obfuscated': 0, 'no_face': 0, 'verification_failed': 0, 'qa_required': 0, 'clean': 0, 'failed': 0, 'skipped': 0}
    
    obfuscated_path = Path(obfuscated_dir)
    qa_path = Path(qa_dir)
    
    # Clean path: use relative to pipeline base directory if not absolute
    clean_dir_config = config.get('CLEAN_DIR', 'data/clean')
    if Path(clean_dir_config).is_absolute():
        clean_path = Path(clean_dir_config)
    else:
        # Relative to biometric pipeline base directory
        base_dir = Path(__file__).parent.parent
        clean_path = base_dir / clean_dir_config
    
    obfuscated_path.mkdir(parents=True, exist_ok=True)
    qa_path.mkdir(parents=True, exist_ok=True)
    clean_path.mkdir(parents=True, exist_ok=True)
    
    failed_images = []  # Track failed images for logging
    
    for img_path in tqdm(images, desc='Obfuscating'):
        result = obfuscate_image(img_path, obfuscated_path, app, anonymizer, method_name, 
                                animal_detector=animal_detector, **kwargs)
        
        if result is None:
            # This should never happen now, but keep as safety
            stats['skipped'] += 1
            failed_images.append(str(img_path))
            continue
        
        # Handle failed images
        if result['action'] == 'failed':
            stats['failed'] += 1
            failed_images.append(f"{img_path.name}: {result.get('error', 'Unknown error')}")
            result['image'] = img_path.name
            results.append(result)
            continue
        
        # Route based on action
        output_name = result.get('output_name', img_path.name)  # Get converted filename if available
        
        if result['action'] == 'obfuscated':
            # Successfully obfuscated image stays in obfuscated_path (temp folder)
            # Master pipeline will copy it to the final blurred folder
            pass
        elif result['action'] == 'qa_required':
            # Copy obfuscated image to QA folder for manual review
            shutil.copy(obfuscated_path / output_name, qa_path / output_name)
        elif result['action'] == 'no_face':
            # Save/convert original image to clean folder (no faces detected)
            # Handle format conversion for unsupported formats
            if img_path.suffix.lower() in {'.heic', '.heif', '.avif'}:
                # Need to convert - load and save as JPG
                img = cv2.imread(str(img_path))
                if img is None:
                    # Try PIL for HEIC/HEIF
                    try:
                        from PIL import Image
                        pil_img = Image.open(img_path)
                        if pil_img.mode != 'RGB':
                            pil_img = pil_img.convert('RGB')
                        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                    except:
                        pass
                
                if img is not None:
                    cv2.imwrite(str(clean_path / output_name), img)
                else:
                    # Fallback: copy as-is if conversion fails
                    shutil.copy(img_path, clean_path / output_name)
            else:
                # Standard formats - just copy
                shutil.copy(img_path, clean_path / output_name)
            stats['clean'] += 1
        
        result['image'] = img_path.name
        results.append(result)
        
        if result['action'] == 'obfuscated':
            stats['obfuscated'] += 1
        elif result['action'] == 'no_face':
            stats['no_face'] += 1
        elif result['action'] == 'qa_required':
            stats['qa_required'] += 1
        
        if result.get('verification') == 'failed':
            stats['verification_failed'] += 1
    
    # Save results
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump({
            'pipeline_version': config.get('PIPELINE_VERSION', '2.0'),
            'anonymization_method': method_name,
            'total_images': len(images),
            'statistics': stats,
            'results': results
        }, f, indent=2)
    
    # Summary
    print("\n" + "=" * 60)
    print("OBFUSCATION SUMMARY")
    print("=" * 60)
    print(f"\n📊 Total images processed: {len(images)}")
    print(f"✅ Successfully obfuscated: {stats['obfuscated']}")
    print(f"✨ Clean images (no faces): {stats['clean']}")
    print(f"🐾 No faces detected: {stats['no_face']}")
    print(f"⚠️  Verification failed: {stats['verification_failed']}")
    print(f"📋 QA review required: {stats['qa_required']}")
    print(f"❌ Failed to process: {stats['failed']}")
    print(f"⏭️  Skipped: {stats['skipped']}")
    
    total_accounted = stats['obfuscated'] + stats['clean'] + stats['qa_required'] + stats['failed'] + stats['skipped']
    if total_accounted != len(images):
        print(f"\n⚠️  WARNING: Mismatch detected!")
        print(f"   Input: {len(images)} images")
        print(f"   Accounted: {total_accounted} images")
        print(f"   Missing: {len(images) - total_accounted} images")
    
    print(f"\n📁 Obfuscated images: {obfuscated_path}")
    print(f"📁 Clean images (ready to use): {clean_path}")
    print(f"📁 QA review queue: {qa_path}")
    print(f"📄 Results saved to: {output_path}")
    
    # Log failed images if any
    if failed_images:
        failed_log = Path(output_path).parent / 'failed_images.log'
        with open(failed_log, 'w') as f:
            f.write("FAILED IMAGES LOG\n")
            f.write("=" * 60 + "\n\n")
            for img in failed_images:
                f.write(f"{img}\n")
        print(f"⚠️  Failed images logged to: {failed_log}")


if __name__ == '__main__':
    import argparse
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Stage 3: Enhanced Face Obfuscation')
    parser.add_argument('--input', '-i', required=False,
                        help='Input directory with images')
    parser.add_argument('--output', '-o', required=False,
                        help='Output directory for obfuscated images')
    parser.add_argument('--qa-dir', required=False,
                        help='QA review directory')
    
    args = parser.parse_args()
    
    config = load_config()
    
    base_dir = Path(__file__).parent.parent
    
    # Use command-line arguments if provided, otherwise use defaults
    input_dir = Path(args.input) if args.input else base_dir / 'data' / 'input'
    obfuscated_dir = Path(args.output) if args.output else base_dir / 'data' / 'obfuscated'
    qa_dir = Path(args.qa_dir) if args.qa_dir else base_dir / 'data' / 'qa_review'
    output_file = base_dir / 'results' / 'obfuscation_results.json'
    
    run_obfuscation(input_dir, obfuscated_dir, qa_dir, output_file, config)
