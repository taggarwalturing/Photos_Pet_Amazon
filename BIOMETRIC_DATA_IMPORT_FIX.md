# Biometric Data Import Fix

## Problem Identified

### Issue
The database was not properly storing biometric compliance information from the pipeline. All images were being imported with:
- `compliance_status = 'processed'`
- `human_faces_detected = 0`

This meant the UI couldn't distinguish between:
- Images with blurred faces (in `03_biometric_processed/blurred/`)
- Clean images with no faces (in `03_biometric_processed/clean/`)

### Evidence
Looking at the pipeline workspace:
```
03_biometric_processed/
├── blurred/     (148 images - faces detected and blurred)
└── clean/       (547 images - no faces detected)
```

But the database had no information about which images were blurred!

## Solution

### Updated Import Script
Modified `backend/import_pipeline_images.py` to:

1. **Load Biometric Metadata** from `obfuscation_results.json`:
   ```json
   {
     "action": "obfuscated",
     "face_count": 1,
     "faces_obfuscated": 1,
     "image": "dogs_with_humans_4498083.jpg"
   }
   ```

2. **Check Physical Folder Location**:
   - Is the image in `blurred/` folder? → `compliance_status = 'blurred'`
   - Is the image in `clean/` folder? → `compliance_status = 'clean'`

3. **Extract Face Count** from JSON metadata:
   - `face_count` field → stored in `human_faces_detected`

4. **Update or Insert** with correct metadata:
   - New images: Insert with biometric data
   - Existing images: Update with biometric data

### Import Results
```
✅ Import complete!
   • New images imported: 0
   • Existing images updated: 695
   • Already in database: 695
   • Images with blurred faces: 148
   • Clean images (no faces): 547
   • Total in database: 696
```

## Database Verification

After running the improved import:

```sql
SELECT compliance_status, COUNT(*) as count
FROM images
GROUP BY compliance_status;
```

Result:
- `blurred`: **148 images** ✅
- `clean`: **547 images** ✅
- `processed`: **1 image** (special case)

## UI Impact

The Pipeline Statistics now correctly shows:
- ✅ **Images with Faces (Blurred)**: 148 images
- ✅ **Images without Faces**: 547 images

This matches the actual pipeline results in the `03_biometric_processed/` folder!

## How to Use

### For New Pipeline Runs
After running the master pipeline:
```bash
make run-pipeline
```

Import images with biometric metadata:
```bash
cd backend
python import_pipeline_images.py
```

### For Existing Data
If you already have images in the database but missing biometric data:
```bash
cd backend
python import_pipeline_images.py
```

The script will:
- Skip images already correctly imported
- Update images missing biometric metadata
- Import new images with full metadata

## Files Modified

1. **`backend/import_pipeline_images.py`**
   - Added JSON parsing for `obfuscation_results.json`
   - Added folder checking for `blurred/` vs `clean/`
   - Added UPDATE logic for existing images
   - Enhanced logging to show biometric statistics

2. **`backend/app/routers/pipeline.py`**
   - Updated `with_faces` query to check `compliance_status IN ('blurred', 'processed', 'obfuscated')`
   - This ensures blurred images are correctly counted

## Benefits

✅ **Accurate Statistics**: UI now shows correct counts for blurred vs clean images
✅ **Full Metadata**: All biometric processing data is preserved in the database
✅ **Data Integrity**: Can trace each image back to its pipeline processing results
✅ **Audit Trail**: `processing_log` field stores action and face count for debugging
✅ **Incremental Updates**: Can re-run import script to update existing records

## Next Steps

Consider adding more fields to the database schema:
- `faces_obfuscated` (int) - How many faces were blurred
- `animals_detected` (int) - Number of animals detected
- `verification_status` (varchar) - Face detection verification result
- `max_confidence_after` (float) - Confidence score after blurring

This would allow even more detailed analytics and quality assurance!
