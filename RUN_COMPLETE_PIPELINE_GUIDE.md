# 🚀 **Running the Complete Master Pipeline**

## **What This Pipeline Does:**

```
✅ Step 1: Download all images from Google Drive
✅ Step 2: Deduplicate images (perceptual hashing + feature matching)
✅ Step 3: Optional LLM validation for edge cases
✅ Step 4: Biometric compliance (face detection + blurring)
✅ Step 5: Screenshot detection & pet filtering
✅ Step 6: Organize into clusters
✅ Step 7: Final output ready for annotation
✅ Step 8: Optional S3 upload
```

---

## **📋 Prerequisites Checklist**

### **1. Google Drive Setup**
```bash
# You need:
✅ Google Drive folder ID
✅ Service account JSON credentials file
```

**Check if you have credentials:**
```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon/backend/master_pipeline
ls turing-genai-ws-*.json
# Result: turing-genai-ws-58339643dd3f.json ✅ (You have it!)
```

### **2. Environment Variables**
You need to configure these in `backend/.env`:

```env
# Required:
GOOGLE_DRIVE_FOLDER_ID=your_actual_folder_id_here
GOOGLE_SERVICE_ACCOUNT_FILE=master_pipeline/turing-genai-ws-58339643dd3f.json

# Optional (for LLM validation):
OPENAI_API_KEY=sk-...
USE_LLM_VALIDATION=false  # Set to true if you want LLM validation

# Optional (for S3 upload):
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=...
```

### **3. Dependencies**
```bash
# Check if pipeline dependencies are installed
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon
make install-pipeline
# Or manually:
# cd backend/master_pipeline
# pip install -r requirements.txt
```

---

## **🎯 Quick Start (3 Steps)**

### **Step 1: Configure Google Drive Folder ID**

```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon

# Edit backend/.env and set your Google Drive folder ID
# You can get it from the Google Drive URL:
# https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE
```

**Find your Google Drive folder ID:**
1. Open Google Drive in browser
2. Navigate to your images folder
3. Copy the ID from URL: `https://drive.google.com/drive/folders/1a2b3c4d5...`
4. The part after `/folders/` is your folder ID

### **Step 2: Run the Complete Pipeline**

```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon

# Option A: Using Makefile (Recommended)
make run-pipeline

# Option B: Using direct command
cd backend/master_pipeline
source ../.venv/bin/activate
python master_pipeline.py --all

# Option C: Step-by-step with monitoring
python master_pipeline.py --download --deduplicate --pipeline --consolidate
```

### **Step 3: Import to Database**

```bash
# After pipeline completes, import images to database
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon/backend
source .venv/bin/activate
python import_pipeline_images.py
```

---

## **🔧 Detailed Command Options**

### **Run All Steps (Recommended)**
```bash
cd backend/master_pipeline
python master_pipeline.py --all

# Or with custom settings:
python master_pipeline.py --all --workspace pipeline_workspace --threshold 0.85
```

### **Run Individual Steps**
```bash
# Step 1: Download only
python master_pipeline.py --download

# Step 2: Deduplicate only (after download)
python master_pipeline.py --deduplicate

# Step 3: Biometric processing (after deduplicate)
python master_pipeline.py --pipeline

# Step 4: Consolidate output
python master_pipeline.py --consolidate

# Step 5: Upload to S3 (optional)
python master_pipeline.py --s3
```

### **Advanced Options**
```bash
# Custom workspace directory
python master_pipeline.py --all --workspace /path/to/workspace

# Custom deduplication threshold (0.0-1.0, higher = stricter)
python master_pipeline.py --deduplicate --threshold 0.90

# Enable LLM validation for deduplication
python master_pipeline.py --deduplicate --use-llm --max-llm-validations 50

# Limit number of images (for testing)
python master_pipeline.py --all --limit 10

# Dry run (show what would happen without doing it)
python master_pipeline.py --all --dry-run

# Verbose logging
python master_pipeline.py --all --verbose
```

---

## **📂 What Gets Created**

The pipeline creates this folder structure:

```
backend/master_pipeline/
└── pipeline_workspace/
    ├── 01_downloaded_from_drive/     ← All images from Google Drive
    │   ├── image1.jpg
    │   ├── image2.heic
    │   └── ...
    │
    ├── 02_unique_images/              ← Unique images only
    │   ├── image1.jpg
    │   ├── image3.jpg
    │   └── ...
    │
    ├── 02_duplicate_clusters/         ← Organized duplicate groups
    │   ├── cluster_001/
    │   │   ├── original_image1.jpg    ← The "best" original
    │   │   ├── duplicate_1.jpg        ← Similar images
    │   │   └── duplicate_2.jpg
    │   ├── cluster_002/
    │   └── ...
    │
    ├── 03_biometric_processed/        ← After face detection/blurring
    │   ├── blurred/                   ← Images with faces (blurred)
    │   │   ├── image1_blurred.jpg
    │   │   └── ...
    │   └── clean/                     ← Images without faces
    │       ├── image3.jpg
    │       └── ...
    │
    └── 04_final_output/               ← Ready for annotation ✅
        ├── image1_blurred.jpg         ← These go to database
        ├── image3.jpg
        └── ...
```

---

## **⏱️ Timeline Estimate**

Based on your 696 images:

```
Step 1: Download (696 images)
  Time: 15-30 minutes
  Speed: ~25-45 images/minute
  Depends on: Network speed, image sizes

Step 2: Deduplication
  Time: 10-20 minutes
  Process: Perceptual hashing + feature matching
  Result: ~500-600 unique images (estimate)

Step 3: Biometric Processing (unique images only)
  Time: 25-40 minutes
  Process: Face detection + blurring
  Speed: ~15-25 images/minute

Step 4: Consolidation
  Time: 2-5 minutes
  Process: Organize and copy to final output

Total: 50-95 minutes (1-1.5 hours)
```

**Factors affecting speed:**
- Image resolution (higher = slower)
- Number of faces per image
- CPU/GPU availability
- Network speed (for download)

---

## **📊 Monitoring Progress**

### **Console Output**
The pipeline prints detailed progress:

```
════════════════════════════════════════════════════════════════
📥 STEP 1: DOWNLOADING IMAGES FROM GOOGLE DRIVE
════════════════════════════════════════════════════════════════

🔍 Scanning Google Drive folder: 1a2b3c4d5...
Found 696 images in Google Drive

Downloading: [████████████████████] 100% | 696/696 | 00:15:32

✅ Downloaded 696 images
📊 Statistics:
   Total size: 2.3 GB
   Avg size: 3.4 MB
   Formats: jpg (450), heic (200), png (46)

════════════════════════════════════════════════════════════════
🔄 STEP 2: DEDUPLICATING IMAGES
════════════════════════════════════════════════════════════════

⚡ Using perceptual hashing + feature matching
Threshold: 0.85 (85% similarity required)

Analyzing images: [████████████████████] 100% | 696/696

Found duplicate groups:
  Cluster 1: 1 original + 5 duplicates
  Cluster 2: 1 original + 3 duplicates
  ...

✅ Deduplication complete
📊 Statistics:
   Original images: 696
   Unique images: 580
   Duplicates found: 116
   Clusters created: 28

════════════════════════════════════════════════════════════════
🔐 STEP 3: BIOMETRIC COMPLIANCE PROCESSING
════════════════════════════════════════════════════════════════

Processing unique images (580 total)

Processing: [████████████████████] 100% | 580/580 | 00:30:15

✅ Biometric processing complete
📊 Statistics:
   Total processed: 580
   🔐 Blurred (faces): 245 (42%)
   ✅ Clean (no faces): 320 (55%)
   ⏭️  Skipped (screenshots): 15 (3%)

════════════════════════════════════════════════════════════════
✅ PIPELINE COMPLETE!
════════════════════════════════════════════════════════════════

📁 Output: backend/master_pipeline/pipeline_workspace/04_final_output/
📊 Ready for annotation: 580 unique, processed images

Next step: Import to database
  cd backend
  python import_pipeline_images.py
```

### **Log Files**
Logs are saved to:
```
backend/master_pipeline/pipeline_workspace/logs/
  ├── pipeline_2026-03-02_18-45-30.log  ← Full pipeline log
  ├── download.log                       ← Download details
  ├── deduplication.log                  ← Dedup results
  └── biometric.log                      ← Face processing
```

---

## **🎯 Running It Now**

### **Complete Command (Copy-Paste This):**

```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon

# Step 1: Make sure you've configured Google Drive folder ID in backend/.env
# Open backend/.env and set GOOGLE_DRIVE_FOLDER_ID=your_folder_id

# Step 2: Run the complete pipeline
make run-pipeline

# This will:
# - Download all images from Google Drive
# - Deduplicate (find and organize duplicates)
# - Process (face detection + blurring)
# - Consolidate to final output
# 
# Time: 1-1.5 hours for 696 images
# Result: Unique, processed images in 04_final_output/

# Step 3: After completion, import to database
cd backend
source .venv/bin/activate
python import_pipeline_images.py

# Result: Database populated with unique, processed images ✅
```

---

## **🔍 Check Google Drive Configuration**

### **Option 1: Check if folder ID is set**
```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon

# This command will show your current config (if set)
grep -E "GOOGLE_DRIVE_FOLDER_ID" backend/.env
```

### **Option 2: Test Google Drive connection**
```bash
cd backend/master_pipeline
source ../.venv/bin/activate

# Test connection
python -c "
from pipeline_config import get_config
config = get_config()
print(f'Folder ID: {config.google_drive_folder_id}')
print(f'Credentials: {config.google_credentials_file}')
"
```

### **Option 3: List images in Google Drive (test)**
```bash
cd backend/master_pipeline
source ../.venv/bin/activate

# Download just 5 images as a test
python master_pipeline.py --download --limit 5

# Check if they were downloaded
ls -lh pipeline_workspace/01_downloaded_from_drive/
```

---

## **⚙️ Configuration Options**

### **Required Configuration (`backend/.env`):**
```env
# 1. Google Drive folder ID (REQUIRED)
GOOGLE_DRIVE_FOLDER_ID=1a2b3c4d5e6f7g8h9i0j  # Get from Drive URL

# 2. Service account file path (REQUIRED)
GOOGLE_SERVICE_ACCOUNT_FILE=master_pipeline/turing-genai-ws-58339643dd3f.json

# 3. Workspace (optional, defaults to pipeline_workspace)
PIPELINE_WORKSPACE=pipeline_workspace
```

### **Optional Configuration:**
```env
# Deduplication settings
DEDUP_THRESHOLD=0.85  # 0.0-1.0, higher = stricter matching
USE_LLM_VALIDATION=false  # Enable for better duplicate detection
MAX_LLM_VALIDATIONS=100

# Face detection settings
FACE_DETECTION_CONFIDENCE=0.5
OBFUSCATION_METHOD=egoblur  # egoblur, gaussian, pixelate, solid
FILTER_ANIMAL_FACES=true  # Skip pet faces

# S3 upload (optional)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=my-bucket
```

---

## **🐛 Troubleshooting**

### **Error: "No Google Drive folder ID configured"**
```bash
# Edit backend/.env and add:
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here

# Get folder ID from Google Drive URL:
# https://drive.google.com/drive/folders/1a2b3c4d5...
#                                        ^^^^^^^^^^^
```

### **Error: "Credentials file not found"**
```bash
# Check if credentials file exists
ls -la backend/master_pipeline/turing-genai-ws-*.json

# If exists, make sure backend/.env points to it:
GOOGLE_SERVICE_ACCOUNT_FILE=master_pipeline/turing-genai-ws-58339643dd3f.json
```

### **Error: "Permission denied" or "Insufficient permissions"**
```bash
# The service account needs access to your Google Drive folder
# Share the folder with the service account email:
# turing-genai-ws@...iam.gserviceaccount.com
```

### **Error: "Module not found"**
```bash
# Install pipeline dependencies
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon
make install-pipeline
```

### **Pipeline hangs or is very slow**
```bash
# Check if images are very large (resize them first)
# Or reduce batch size in configuration
# Or run in smaller batches:
python master_pipeline.py --download --limit 100  # Process 100 at a time
```

---

## **📈 After Pipeline Completes**

### **Step 1: Verify Output**
```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon

# Check final output folder
ls -lh backend/master_pipeline/pipeline_workspace/04_final_output/ | wc -l
# Should show ~500-600 images (after deduplication)

# Check image types
cd backend/master_pipeline/pipeline_workspace/04_final_output/
ls *.jpg | wc -l  # Count JPG images
ls *.png | wc -l  # Count PNG images
```

### **Step 2: Import to Database**
```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon/backend

source .venv/bin/activate
python import_pipeline_images.py

# Output:
# ======================================================================
# 📥 IMPORTING PIPELINE IMAGES TO DATABASE
# ======================================================================
# 
# 📁 Found 580 images in final output
# 📊 Database has 696 existing images
# 
#    Imported 100 images...
#    Imported 200 images...
#    ...
# 
# ✅ Import complete!
#    • New images imported: 580
#    • Already in database: 116
#    • Total in database: 696
```

### **Step 3: Verify in UI**
```bash
# Start the application
make run-all

# Open in browser
open http://localhost:5173

# Images should now show in the annotation UI
# They'll load instantly from cache after first view
```

---

## **🎯 Summary - Run This Now**

```bash
cd /Users/tusharaggarwal/Desktop/Turing/photo_artifact/GIT_2/Photos_Pet_Amazon

# 1. Configure (one-time setup)
# Edit backend/.env:
#   GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here

# 2. Run complete pipeline (1-1.5 hours)
make run-pipeline

# 3. Import to database
cd backend
python import_pipeline_images.py

# 4. Start application
cd ..
make run-all

# 5. Open UI
open http://localhost:5173

# Done! ✅
```

---

## **📊 What You'll Get:**

- ✅ **Unique images only** (duplicates removed)
- ✅ **Face-blurred** (compliance-ready)
- ✅ **Organized** (clean folder structure)
- ✅ **Ready for annotation** (in database)
- ✅ **Cached** (fast UI loading)

**Time investment:** 1-1.5 hours  
**Result:** Production-ready annotation workflow 🚀
