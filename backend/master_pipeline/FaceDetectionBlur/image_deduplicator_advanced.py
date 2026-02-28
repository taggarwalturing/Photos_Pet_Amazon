#!/usr/bin/env python3
"""
Advanced Image Deduplicator - Scene/Session Based Detection
============================================================
Detects images from the SAME SCENE/SESSION even if:
- Person has different poses
- Person is looking in different directions
- Person is visible in one but not another
- Same background but different foreground activity

Methods used:
1. Background comparison (masks out humans)
2. Structural feature matching (ORB/edges)
3. Color histogram of background
4. Traditional perceptual hashing

Usage:
    python image_deduplicator_advanced.py --input input/ --output output/
    
    # Adjust similarity threshold (lower = stricter)
    python image_deduplicator_advanced.py --input input/ --output output/ --threshold 0.6
"""

import cv2
import numpy as np
import hashlib
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field
import shutil
import warnings
warnings.filterwarnings('ignore')

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
    # Enable AVIF support
    try:
        import pillow_avif
    except ImportError:
        pass
except ImportError:
    PIL_AVAILABLE = False


def load_image(filepath: Path) -> Optional[np.ndarray]:
    """Load image with support for AVIF and other formats."""
    # Try OpenCV first (faster for standard formats)
    img = cv2.imread(str(filepath))
    if img is not None:
        return img
    
    # Fallback to PIL for AVIF and other formats
    if PIL_AVAILABLE:
        try:
            pil_img = Image.open(filepath)
            # Convert to RGB if needed
            if pil_img.mode in ('RGBA', 'LA', 'P'):
                pil_img = pil_img.convert('RGB')
            elif pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            # Convert to numpy array (RGB)
            img_array = np.array(pil_img)
            # Convert RGB to BGR for OpenCV
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            return img_bgr
        except Exception:
            return None
    
    return None


@dataclass
class ImageInfo:
    """Store image information and features."""
    path: Path
    filename: str
    md5_hash: str = ""
    phash: str = ""
    background_hist: Optional[np.ndarray] = None
    edge_features: Optional[np.ndarray] = None
    orb_descriptors: Optional[np.ndarray] = None
    file_size: int = 0
    dimensions: Tuple[int, int] = (0, 0)
    has_human: bool = False
    is_duplicate: bool = False
    duplicate_of: str = ""
    similarity_score: float = 0.0
    match_reason: str = ""


class SceneDetector:
    """Detect same scene/session images."""
    
    def __init__(self):
        # Load YOLO for human segmentation
        if YOLO_AVAILABLE:
            self.yolo_seg = YOLO('yolov8n-seg.pt')
            print("✓ YOLOv8-seg loaded for human segmentation")
        else:
            self.yolo_seg = None
            print("⚠ YOLO not available - background extraction disabled")
        
        # ORB feature detector
        self.orb = cv2.ORB_create(nfeatures=500)
        
        # Feature matcher
        self.bf_matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        
        # COCO class for person
        self.PERSON_CLASS = 0
    
    def get_human_mask(self, image: np.ndarray) -> Tuple[np.ndarray, bool]:
        """
        Get mask of human regions in image.
        Returns: (mask, has_human)
        """
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        has_human = False
        
        if self.yolo_seg is None:
            return mask, has_human
        
        results = self.yolo_seg(image, verbose=False, conf=0.3)
        
        for result in results:
            if result.masks is None:
                continue
            
            for seg_mask, box in zip(result.masks.data, result.boxes):
                cls = int(box.cls[0])
                
                if cls == self.PERSON_CLASS:
                    has_human = True
                    mask_np = seg_mask.cpu().numpy()
                    mask_resized = cv2.resize(mask_np, (w, h))
                    mask_binary = (mask_resized > 0.5).astype(np.uint8) * 255
                    
                    # Dilate mask to ensure full coverage
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (30, 30))
                    mask_binary = cv2.dilate(mask_binary, kernel)
                    
                    mask = cv2.bitwise_or(mask, mask_binary)
        
        return mask, has_human
    
    def extract_background(self, image: np.ndarray, human_mask: np.ndarray) -> np.ndarray:
        """Extract background by masking out humans."""
        # Invert mask to get background
        background_mask = cv2.bitwise_not(human_mask)
        
        # Apply mask
        background = cv2.bitwise_and(image, image, mask=background_mask)
        
        return background, background_mask
    
    def compute_color_histogram(self, image: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        """Compute normalized color histogram."""
        # Convert to HSV for better color representation
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Compute histogram
        hist = cv2.calcHist(
            [hsv], [0, 1, 2], mask,
            [16, 16, 16],  # bins for H, S, V
            [0, 180, 0, 256, 0, 256]
        )
        
        # Normalize
        hist = cv2.normalize(hist, hist).flatten()
        
        return hist
    
    def compute_edge_signature(self, image: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        """Compute edge-based signature of the image."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply mask if provided
        if mask is not None:
            gray = cv2.bitwise_and(gray, gray, mask=mask)
        
        # Detect edges
        edges = cv2.Canny(gray, 50, 150)
        
        # Resize to fixed size for comparison
        edges_resized = cv2.resize(edges, (64, 64))
        
        return edges_resized.flatten().astype(np.float32)
    
    def compute_orb_features(self, image: np.ndarray, mask: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
        """Compute ORB features for structural matching."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply mask if provided
        if mask is not None:
            gray = cv2.bitwise_and(gray, gray, mask=mask)
        
        # Detect and compute ORB features
        keypoints, descriptors = self.orb.detectAndCompute(gray, mask)
        
        return descriptors
    
    def compute_phash(self, image: np.ndarray, size: int = 16) -> str:
        """Compute perceptual hash."""
        resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray_float = np.float32(gray)
        dct = cv2.dct(gray_float)
        dct_low = dct[:8, :8]
        med = np.median(dct_low.flatten()[1:])
        hash_bits = (dct_low.flatten() > med).astype(int)
        return ''.join(map(str, hash_bits))
    
    def compare_histograms(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        """Compare two histograms. Returns similarity (0-1)."""
        if hist1 is None or hist2 is None:
            return 0.0
        return cv2.compareHist(hist1.astype(np.float32), hist2.astype(np.float32), cv2.HISTCMP_CORREL)
    
    def compare_edges(self, edge1: np.ndarray, edge2: np.ndarray) -> float:
        """Compare edge signatures. Returns similarity (0-1)."""
        if edge1 is None or edge2 is None:
            return 0.0
        
        # Normalize
        edge1_norm = edge1 / (np.linalg.norm(edge1) + 1e-6)
        edge2_norm = edge2 / (np.linalg.norm(edge2) + 1e-6)
        
        # Cosine similarity
        return float(np.dot(edge1_norm, edge2_norm))
    
    def compare_orb_features(self, desc1: np.ndarray, desc2: np.ndarray) -> float:
        """Compare ORB descriptors. Returns similarity (0-1)."""
        if desc1 is None or desc2 is None:
            return 0.0
        
        if len(desc1) == 0 or len(desc2) == 0:
            return 0.0
        
        try:
            matches = self.bf_matcher.match(desc1, desc2)
            
            # Calculate match ratio
            max_matches = min(len(desc1), len(desc2))
            if max_matches == 0:
                return 0.0
            
            # Good matches have low distance
            good_matches = [m for m in matches if m.distance < 50]
            
            return len(good_matches) / max_matches
        except:
            return 0.0
    
    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """Compute Hamming distance."""
        if len(hash1) != len(hash2):
            return 64
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


class AdvancedDeduplicator:
    """Advanced deduplication with scene detection."""
    
    def __init__(self, similarity_threshold: float = 0.6):
        """
        Initialize deduplicator.
        
        Args:
            similarity_threshold: Minimum similarity score (0-1) to consider as duplicate
                                  0.5 = lenient (catches more)
                                  0.6 = moderate (default)
                                  0.7 = strict (fewer matches)
        """
        self.threshold = similarity_threshold
        self.detector = SceneDetector()
        self.images: List[ImageInfo] = []
        self.duplicate_groups: Dict[str, List[ImageInfo]] = defaultdict(list)
    
    def compute_md5(self, filepath: Path) -> str:
        """Compute MD5 hash."""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def analyze_image(self, filepath: Path) -> ImageInfo:
        """Analyze single image and extract all features."""
        info = ImageInfo(
            path=filepath,
            filename=filepath.name,
            file_size=filepath.stat().st_size
        )
        
        # MD5 hash
        info.md5_hash = self.compute_md5(filepath)
        
        # Load image (supports AVIF and other formats)
        image = load_image(filepath)
        if image is None:
            return info
        
        info.dimensions = (image.shape[1], image.shape[0])
        
        # Get human mask
        human_mask, has_human = self.detector.get_human_mask(image)
        info.has_human = has_human
        
        # Extract background
        background, bg_mask = self.detector.extract_background(image, human_mask)
        
        # Compute features on BACKGROUND (ignoring humans)
        info.background_hist = self.detector.compute_color_histogram(image, bg_mask)
        info.edge_features = self.detector.compute_edge_signature(image, bg_mask)
        info.orb_descriptors = self.detector.compute_orb_features(image, bg_mask)
        
        # Also compute pHash on full image (for exact duplicates)
        info.phash = self.detector.compute_phash(image)
        
        return info
    
    def scan_images(self, input_dir: Path) -> List[ImageInfo]:
        """Scan directory and analyze all images."""
        exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif', '.tiff', '.tif', '.avif'}
        image_files = [f for f in input_dir.iterdir() if f.suffix.lower() in exts]
        
        print(f"📷 Found {len(image_files)} images")
        print(f"🔧 Analyzing images (extracting background features)...")
        
        images = []
        iterator = tqdm(image_files, desc="Analyzing") if TQDM_AVAILABLE else image_files
        
        for filepath in iterator:
            try:
                info = self.analyze_image(filepath)
                images.append(info)
            except Exception as e:
                print(f"⚠ Error processing {filepath.name}: {e}")
        
        self.images = images
        
        # Summary
        humans_count = sum(1 for img in images if img.has_human)
        print(f"   - Images with humans detected: {humans_count}/{len(images)}")
        
        return images
    
    def compute_similarity(self, img1: ImageInfo, img2: ImageInfo) -> Tuple[float, str]:
        """
        Compute overall similarity between two images.
        Returns: (similarity_score, match_reason)
        """
        scores = {}
        
        # 1. Check exact duplicate first (MD5)
        if img1.md5_hash == img2.md5_hash:
            return 1.0, "Exact duplicate (MD5)"
        
        # 2. Check perceptual hash (catches resized/compressed)
        phash_dist = self.detector.hamming_distance(img1.phash, img2.phash)
        phash_sim = 1.0 - (phash_dist / 64.0)
        scores['phash'] = phash_sim
        
        if phash_dist <= 5:
            return phash_sim, "Perceptual match (same image, different format)"
        
        # 3. Compare background histogram
        hist_sim = self.detector.compare_histograms(img1.background_hist, img2.background_hist)
        scores['histogram'] = max(0, hist_sim)  # Can be negative
        
        # 4. Compare edge structure
        edge_sim = self.detector.compare_edges(img1.edge_features, img2.edge_features)
        scores['edges'] = edge_sim
        
        # 5. Compare ORB features
        orb_sim = self.detector.compare_orb_features(img1.orb_descriptors, img2.orb_descriptors)
        scores['orb'] = orb_sim
        
        # Weighted combination for scene matching
        # Higher weight on background features
        weights = {
            'phash': 0.15,      # Low weight - we want to catch different poses
            'histogram': 0.35,  # High weight - background color
            'edges': 0.30,      # High weight - background structure
            'orb': 0.20         # Medium weight - structural features
        }
        
        final_score = sum(scores[k] * weights[k] for k in weights)
        
        # Determine match reason
        if final_score >= self.threshold:
            reasons = []
            if scores['histogram'] > 0.7:
                reasons.append("similar background colors")
            if scores['edges'] > 0.5:
                reasons.append("similar scene structure")
            if scores['orb'] > 0.3:
                reasons.append("matching background features")
            
            reason = "Same scene: " + ", ".join(reasons) if reasons else "Scene similarity"
            return final_score, reason
        
        return final_score, ""
    
    def find_duplicates(self) -> Dict[str, List[ImageInfo]]:
        """Find duplicate/similar scene images using DIRECT pairs only (no transitive grouping)."""
        print(f"🔍 Finding scene duplicates (threshold={self.threshold})...")
        
        n = len(self.images)
        
        # Store all matching pairs with their similarity
        matching_pairs = []  # [(img1, img2, similarity, reason), ...]
        
        # Compare all pairs
        total_comparisons = n * (n - 1) // 2
        print(f"   Comparing {n} images ({total_comparisons} pairs)...")
        
        if TQDM_AVAILABLE:
            pbar = tqdm(total=total_comparisons, desc="Comparing")
        
        for i in range(n):
            for j in range(i + 1, n):
                img1, img2 = self.images[i], self.images[j]
                
                similarity, reason = self.compute_similarity(img1, img2)
                
                if similarity >= self.threshold:
                    matching_pairs.append((img1, img2, similarity, reason))
                
                if TQDM_AVAILABLE:
                    pbar.update(1)
        
        if TQDM_AVAILABLE:
            pbar.close()
        
        print(f"   Found {len(matching_pairs)} matching pairs")
        
        # Sort pairs by similarity (highest first) to prioritize best matches
        matching_pairs.sort(key=lambda x: x[2], reverse=True)
        
        # Track which images have been assigned as duplicates
        assigned_duplicates = set()
        
        # Helper to get sort key from filename (numeric part)
        def get_sort_key(img):
            import re
            nums = re.findall(r'\d+', img.filename)
            # Return a tuple: (is_numeric, value) for consistent sorting
            # This ensures we can always compare - numbers sort before strings
            if nums:
                return (0, int(nums[0]))  # Numeric: priority 0
            else:
                return (1, img.filename)  # String: priority 1
        
        # FIRST: Sort pairs by original's filename (lower number first) to ensure
        # lower-numbered images become originals before higher-numbered ones try to
        matching_pairs.sort(key=lambda x: (
            min(get_sort_key(x[0]), get_sort_key(x[1])),  # Primary: lower filename in pair
            -x[2]  # Secondary: higher similarity
        ))
        
        # Process pairs - for each pair, determine original by filename (lower = original)
        for img1, img2, similarity, reason in matching_pairs:
            # Determine which is original (lower filename = original, typical for photo sessions)
            if get_sort_key(img1) <= get_sort_key(img2):
                original, duplicate = img1, img2
            else:
                original, duplicate = img2, img1
            
            # Skip if this image is already marked as a duplicate
            if duplicate.filename in assigned_duplicates:
                continue
            
            # Skip if the "original" is itself already a duplicate of something else
            if original.filename in assigned_duplicates:
                continue
            
            # Mark as duplicate
            duplicate.is_duplicate = True
            duplicate.duplicate_of = original.filename
            duplicate.similarity_score = similarity
            duplicate.match_reason = reason
            assigned_duplicates.add(duplicate.filename)
            
            if original.filename not in self.duplicate_groups:
                self.duplicate_groups[original.filename] = []
            self.duplicate_groups[original.filename].append(duplicate)
        
        duplicate_count = len(assigned_duplicates)
        print(f"   Total duplicates: {duplicate_count}")
        print(f"   Duplicate groups: {len(self.duplicate_groups)}")
        
        return self.duplicate_groups
    
    def segregate_images(self, output_dir: Path) -> Tuple[int, int]:
        """Segregate images into originals and duplicates folders."""
        originals_dir = output_dir / "originals"
        duplicates_dir = output_dir / "duplicates"
        
        originals_dir.mkdir(parents=True, exist_ok=True)
        duplicates_dir.mkdir(parents=True, exist_ok=True)
        
        original_count = 0
        duplicate_count = 0
        
        print(f"📁 Segregating images...")
        
        iterator = tqdm(self.images, desc="Copying") if TQDM_AVAILABLE else self.images
        
        for img in iterator:
            try:
                if img.is_duplicate:
                    # All duplicates go directly into duplicates folder
                    shutil.copy2(img.path, duplicates_dir / img.filename)
                    duplicate_count += 1
                else:
                    shutil.copy2(img.path, originals_dir / img.filename)
                    original_count += 1
            except Exception as e:
                print(f"⚠ Error copying {img.filename}: {e}")
        
        return original_count, duplicate_count
    
    def generate_report(self, output_dir: Path) -> Path:
        """Generate Excel report."""
        report_path = output_dir / "scene_duplicates_report.xlsx"
        
        if not PANDAS_AVAILABLE:
            report_path = output_dir / "scene_duplicates_report.csv"
            with open(report_path, 'w') as f:
                f.write("Image,Status,Duplicate Of,Similarity,Match Reason,Has Human,File Size\n")
                for img in self.images:
                    status = "DUPLICATE" if img.is_duplicate else "ORIGINAL"
                    f.write(f"{img.filename},{status},{img.duplicate_of},{img.similarity_score:.2f},{img.match_reason},{img.has_human},{img.file_size}\n")
            return report_path
        
        # All images sheet
        rows = []
        for img in self.images:
            rows.append({
                'Image': img.filename,
                'Status': 'DUPLICATE' if img.is_duplicate else 'ORIGINAL',
                'Duplicate Of': img.duplicate_of if img.is_duplicate else '',
                'Similarity Score': f"{img.similarity_score:.2%}" if img.is_duplicate else '',
                'Match Reason': img.match_reason if img.is_duplicate else '',
                'Has Human': '✓' if img.has_human else '',
                'File Size (KB)': img.file_size // 1024,
                'Dimensions': f"{img.dimensions[0]}x{img.dimensions[1]}"
            })
        
        df = pd.DataFrame(rows)
        df = df.sort_values(['Status', 'Duplicate Of', 'Image'], ascending=[False, True, True])
        
        # Summary sheet
        summary_data = {
            'Metric': [
                'Total Images',
                'Original Images',
                'Duplicate Images',
                'Images with Humans',
                'Duplicate Groups (Sessions)'
            ],
            'Count': [
                len(self.images),
                len([i for i in self.images if not i.is_duplicate]),
                len([i for i in self.images if i.is_duplicate]),
                len([i for i in self.images if i.has_human]),
                len(self.duplicate_groups)
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        
        # Groups sheet
        group_rows = []
        for original, duplicates in self.duplicate_groups.items():
            for dup in duplicates:
                group_rows.append({
                    'Original Image': original,
                    'Duplicate Image': dup.filename,
                    'Similarity': f"{dup.similarity_score:.2%}",
                    'Match Reason': dup.match_reason,
                    'Original Has Human': '✓' if any(i.has_human for i in self.images if i.filename == original) else '',
                    'Duplicate Has Human': '✓' if dup.has_human else ''
                })
        
        groups_df = pd.DataFrame(group_rows) if group_rows else pd.DataFrame()
        
        # Write Excel
        with pd.ExcelWriter(report_path, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            df.to_excel(writer, sheet_name='All Images', index=False)
            if not groups_df.empty:
                groups_df.to_excel(writer, sheet_name='Duplicate Groups', index=False)
        
        return report_path


def process(input_dir: str, output_dir: str, threshold: float = 0.6):
    """Main processing function."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        print(f"❌ Input directory not found: {input_dir}")
        return
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("=" * 65)
    print("🔍 ADVANCED IMAGE DEDUPLICATOR - Scene/Session Detection")
    print("=" * 65)
    print()
    print("This tool detects images from the SAME SCENE even if:")
    print("  • Person has different poses")
    print("  • Person is looking in different directions")
    print("  • Person is visible in one but not another")
    print()
    print(f"📁 Input:  {input_path}")
    print(f"📁 Output: {output_path}")
    print(f"🎯 Similarity threshold: {threshold:.0%}")
    print()
    
    # Initialize
    deduplicator = AdvancedDeduplicator(similarity_threshold=threshold)
    
    # Scan and analyze
    deduplicator.scan_images(input_path)
    
    if not deduplicator.images:
        print("❌ No images found!")
        return
    
    print()
    
    # Find duplicates
    deduplicator.find_duplicates()
    print()
    
    # Segregate
    original_count, duplicate_count = deduplicator.segregate_images(output_path)
    print()
    
    # Report
    report_path = deduplicator.generate_report(output_path)
    print()
    
    # Summary
    print("=" * 65)
    print("✅ DEDUPLICATION COMPLETE")
    print("=" * 65)
    print()
    print(f"📊 Results:")
    print(f"   - Total images: {len(deduplicator.images)}")
    print(f"   - Originals: {original_count}")
    print(f"   - Duplicates: {duplicate_count}")
    print(f"   - Scene groups: {len(deduplicator.duplicate_groups)}")
    print()
    print(f"📁 Output:")
    print(f"   - originals/   : Unique images")
    print(f"   - duplicates/  : All duplicate images")
    print(f"   - {report_path.name}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Advanced Image Deduplicator - Detects same scene/session images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python image_deduplicator_advanced.py --input photos/ --output deduplicated/
  
  # Stricter matching
  python image_deduplicator_advanced.py --input photos/ --output deduplicated/ --threshold 0.7
  
  # More lenient (catch more variations)
  python image_deduplicator_advanced.py --input photos/ --output deduplicated/ --threshold 0.5

What this tool detects:
  ✓ Same background, different person poses
  ✓ Person looking straight vs sideways
  ✓ Person visible vs not visible
  ✓ Same photoshoot/session images
  ✓ Same location, different times
        """
    )
    
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", default="deduplicated_advanced/")
    parser.add_argument("--threshold", "-t", type=float, default=0.6,
                        help="Similarity threshold 0-1 (default: 0.6)")
    
    args = parser.parse_args()
    
    process(args.input, args.output, args.threshold)


if __name__ == "__main__":
    main()

