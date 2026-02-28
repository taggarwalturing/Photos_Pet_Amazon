# Biometric Compliance Pipeline V2.1

**Production-ready pipeline for automated face detection, obfuscation, and biometric compliance.**

---

## 🎯 Overview

This pipeline automatically processes images to ensure biometric privacy compliance by:
- Detecting human faces with high accuracy
- Obfuscating faces using context-preserving blur
- Filtering out animal faces (cats/dogs)
- Separating clean (face-free) images
- Providing QA workflow for manual review

---

## ✨ Key Features

### 1. **OpenCV DNN Face Detection**
- Pre-trained Caffe model optimized for human faces
- 69% reduction in false positives vs InsightFace
- ~30 images/second processing speed

### 2. **YOLO Animal Filtering**
- Automatic cat/dog detection
- Prevents animal face obfuscation
- IoU-based overlap detection

### 3. **Smart Output Routing**
- `data/clean/` - Images with no faces (ready to use)
- `data/obfuscated/` - Images with blurred human faces
- `data/qa_review/` - Images requiring manual review

### 4. **EgoBlur Anonymization**
- Context-preserving blur (maintains image usability)
- Multiple methods: EgoBlur, Gaussian, Pixelate, Solid
- Configurable intensity and padding

### 5. **Excel-based QA Workflow**
- Export QA checklist to Excel
- Offline review and decision-making
- Batch import of QA decisions

---

## 🚀 Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Run the pipeline
python run_pipeline_enhanced.py --input YOUR_FOLDER
```

### With Custom Paths

```bash
python run_pipeline_enhanced.py \
  --input /path/to/images \
  --output /path/to/obfuscated \
  --qa-dir /path/to/qa_review
```

---

## 📁 Directory Structure

```
biometric_compliance_pipeline/
├── run_pipeline_enhanced.py      # Main pipeline script
├── config/
│   └── settings.env              # Configuration settings
├── scripts/
│   ├── stage2_detect_faces_enhanced.py    # OpenCV DNN detection
│   ├── stage3_obfuscate_faces_enhanced.py # EgoBlur obfuscation + YOLO
│   └── stage4_qa_review.py                # Excel QA workflow
├── models/
│   ├── deploy.prototxt                    # OpenCV DNN config
│   └── res10_300x300_ssd_iter_140000.caffemodel  # Face detector
├── yolov8n.pt                    # YOLO animal detector
├── data/
│   ├── input/        # Place your images here
│   ├── clean/        # Output: Images with no faces
│   ├── obfuscated/   # Output: Images with blurred faces
│   └── qa_review/    # Output: Images needing review
└── results/
    ├── logs/         # Execution logs
    └── *.json        # Detection/obfuscation results
```

---

## ⚙️ Configuration

Edit `config/settings.env`:

```ini
# Input/Output Directories
INPUT_DIR=data/input
OUTPUT_DIR=data/obfuscated
QA_DIR=data/qa_review
CLEAN_DIR=data/clean

# Animal Face Filtering
FILTER_ANIMAL_FACES=True
ANIMAL_IOU_THRESHOLD=0.3

# Anonymization Method
ANONYMIZATION_METHOD=egoblur  # Options: egoblur, gaussian, pixelate, solid
EGOBLUR_INTENSITY=1.0

# Quality Filtering
MIN_FACE_BRIGHTNESS=40
MIN_FACE_CONTRAST=30
```

---

## 📊 Pipeline Stages

### Stage 1: Contributor Controls
Documentation and guidelines for image submission.

### Stage 2: Face Detection
- Uses OpenCV DNN (Caffe pre-trained model)
- Detects human faces with high accuracy
- Filters out silhouettes and low-quality detections

### Stage 3: Face Obfuscation
- YOLO detects cats/dogs to skip animal faces
- Applies EgoBlur or other anonymization methods
- Re-verifies obfuscation effectiveness
- Routes images to clean/obfuscated/qa_review folders

### Stage 4: QA Review
- Exports flagged images to Excel checklist
- Human reviewer fills in APPROVE/REJECT decisions
- Import decisions to move images to final folders

---

## 📈 Performance Metrics

| Metric | Value |
|--------|-------|
| Speed | ~30 images/second |
| False Positives | 12.1% (vs 39.3% baseline) |
| Animal Protection | 100% of detected animals |
| Clean Image Detection | Automatic separation |

---

## 🔧 Advanced Usage

### Running Individual Stages

```bash
# Stage 2: Detection only
python scripts/stage2_detect_faces_enhanced.py --input data/input

# Stage 3: Obfuscation only
python scripts/stage3_obfuscate_faces_enhanced.py \
  --input data/input \
  --output data/obfuscated \
  --qa-dir data/qa_review

# Stage 4: QA Export
python scripts/stage4_qa_review.py --qa-dir data/qa_review

# Stage 4: QA Import (after reviewing Excel)
python scripts/stage4_qa_review.py --import results/qa_review_checklist.xlsx
```

### Customizing Anonymization

In `settings.env`:

```ini
# Use Gaussian blur (stronger obfuscation)
ANONYMIZATION_METHOD=gaussian
BLUR_KERNEL_SIZE=99
BLUR_SIGMA=30

# Or use pixelation
ANONYMIZATION_METHOD=pixelate
PIXELATE_SIZE=12
```

---

## 📝 Requirements

- Python 3.8+
- OpenCV
- InsightFace (for verification)
- Ultralytics YOLO
- openpyxl (for Excel QA)
- tqdm (progress bars)

See `requirements.txt` for full list.

---

## 🛡️ Privacy & Compliance

This pipeline is designed for:
- GDPR compliance (EU)
- BIPA compliance (Illinois)
- CCPA compliance (California)
- Enhanced privacy jurisdictions

**Important**: This tool assists with compliance but does not guarantee it. Always consult with legal counsel for your specific use case.

---

## 📚 Documentation

- **[USAGE_GUIDE.md](USAGE_GUIDE.md)** - Detailed usage instructions
- **[CONTRIBUTOR_GUIDELINES.md](CONTRIBUTOR_GUIDELINES.md)** - Guidelines for image contributors
- **[CLEAN_FOLDER_SUMMARY.md](CLEAN_FOLDER_SUMMARY.md)** - Clean folder feature details

---

## 🤝 Support

For issues or questions:
1. Check the documentation in the `docs/` folder
2. Review the configuration in `config/settings.env`
3. Examine the logs in `results/logs/`

---

## 📄 License

This project is provided as-is for biometric compliance purposes.

---

**Version**: 2.1  
**Last Updated**: 2026-02-25
