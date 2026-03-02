# Manual Blur Tool Implementation

## Summary of Changes

### ✅ Completed Tasks

1. **Removed "Remaining" Stats from Annotator Dashboard**
   - Removed the "Remaining" stats card from `AnnotatorHome.jsx`
   - Simplified dashboard to show only "Total Images" and "Completed"

2. **Added Database Columns for Blur Tracking**
   - Added `manually_blurred` (Boolean) - Flag to track if image was manually blurred
   - Added `blur_regions` (JSON) - Stores array of blur region coordinates
   - Added `manually_blurred_by` (Integer) - Foreign key to user who applied blur
   - Added `manually_blurred_at` (DateTime) - Timestamp of blur application
   - Added `annotated_blur_url` (Text) - URL to the blurred image file

3. **Created Backend API Endpoints**
   - `POST /api/annotator/blur/apply` - Apply blur to image regions
   - `GET /api/annotator/blur/{image_id}/regions` - Get existing blur regions
   - `DELETE /api/annotator/blur/{image_id}/blur` - Remove manual blur

4. **Implemented Blur Processing Logic**
   - Uses existing `roi-blur` library for Gaussian blur
   - Downloads original image, applies blur to specified regions
   - Saves blurred image to `backend/master_pipeline/pipeline_workspace/annotated_blur/`
   - Updates database with coordinates and metadata

5. **Created Blur Tool UI Component**
   - Interactive canvas-based drawing tool
   - Annotators can draw rectangles over areas to blur
   - Real-time visual feedback during drawing
   - Undo/Clear functionality
   - Modal overlay for focused interaction

6. **Integrated Blur Tool into Annotation Page**
   - Added "Blur Tool" button in annotator's annotation interface
   - Available while annotating images
   - Non-intrusive, only activates when button is clicked

## File Changes

### Backend Files

#### Modified
- `backend/app/models/image.py` - Added blur tracking columns
- `backend/app/main.py` - Registered new annotator_blur router
- `backend/requirements.txt` - Confirmed roi-blur dependency

#### Created
- `backend/app/routers/annotator_blur.py` - Blur endpoints
- `backend/migrations/add_blur_tracking.py` - Database migration script

### Frontend Files

#### Modified
- `frontend/src/pages/AnnotatorHome.jsx` - Removed "Remaining" stats
- `frontend/src/pages/AnnotationPage.jsx` - Integrated BlurTool component

#### Created
- `frontend/src/components/BlurTool.jsx` - Interactive blur tool component

## How to Use

### 1. Run Database Migration

```bash
cd backend
source .venv/bin/activate
python migrations/add_blur_tracking.py
```

### 2. Restart the Application

```bash
make stop-all
make run-all
```

### 3. Use the Blur Tool

1. Log in as an annotator
2. Navigate to any category annotation page
3. Click the "🎨 Blur Tool" button
4. Draw rectangles over areas you want to blur
5. Click "✓ Apply Blur" to save

## Features

### Blur Tool Capabilities

- **Interactive Drawing**: Click and drag to draw blur regions
- **Multiple Regions**: Add as many blur regions as needed
- **Undo**: Remove the last drawn region
- **Clear All**: Remove all regions and start over
- **Visual Feedback**: See regions as red outlines with semi-transparent fill
- **Persistent Storage**: Blur coordinates and images saved permanently

### Database Schema

```sql
ALTER TABLE images ADD COLUMN manually_blurred BOOLEAN DEFAULT FALSE;
ALTER TABLE images ADD COLUMN blur_regions JSON;
ALTER TABLE images ADD COLUMN manually_blurred_by INTEGER;
ALTER TABLE images ADD COLUMN manually_blurred_at TIMESTAMP;
ALTER TABLE images ADD COLUMN annotated_blur_url TEXT;
```

### Storage Structure

Blurred images are saved to:
```
backend/master_pipeline/pipeline_workspace/annotated_blur/
└── blur_{image_id}_{filename}.jpg
```

### Blur Region Format

Coordinates are stored as normalized values (0.0 to 1.0):

```json
[
  {
    "x": 0.25,      // 25% from left
    "y": 0.30,      // 30% from top
    "width": 0.20,  // 20% of image width
    "height": 0.15  // 15% of image height
  }
]
```

## API Endpoints

### Apply Blur
```http
POST /api/annotator/blur/apply
Content-Type: application/json

{
  "image_id": 123,
  "regions": [
    {"x": 0.25, "y": 0.3, "width": 0.2, "height": 0.15}
  ]
}
```

### Get Blur Regions
```http
GET /api/annotator/blur/{image_id}/regions
```

Response:
```json
{
  "image_id": 123,
  "manually_blurred": true,
  "regions": [...],
  "blurred_by": 5,
  "blurred_at": "2026-03-02T20:30:00"
}
```

### Remove Blur
```http
DELETE /api/annotator/blur/{image_id}/blur
```

## Security

- Only annotators can use the blur tool (role check)
- Each blur operation is tracked with user ID and timestamp
- Original images are never modified
- Blurred versions are stored separately

## Performance

- Uses efficient Gaussian blur algorithm from `roi-blur`
- Canvas-based drawing for smooth interaction
- Blur processing happens on backend to ensure quality
- Images cached locally after processing

## Future Enhancements

Potential improvements:
- Preview blur before applying
- Adjustable blur intensity
- Circular/elliptical blur regions
- Batch blur multiple images
- Export blur regions for training data
- Admin review of manual blurs

## Troubleshooting

### Migration Issues
If migration fails:
```bash
cd backend
python migrations/add_blur_tracking.py
```

### Blur Not Applied
- Check browser console for errors
- Verify roi-blur is installed: `pip list | grep roi`
- Check backend logs for processing errors

### Canvas Not Drawing
- Ensure image loads completely
- Check browser compatibility (modern browsers required)
- Verify JavaScript console for errors

## Technical Details

### Dependencies
- **Backend**: roi-blur, opencv-python, numpy, pillow
- **Frontend**: React, axios

### Blur Algorithm
- Uses Gaussian blur with configurable kernel size and sigma
- Default: ksize=51, sigma=40.0
- Processes in RGB colorspace
- Output: JPEG at 90% quality

### Browser Compatibility
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Testing

To test the blur tool:
1. Create a test annotator account
2. Assign categories with images
3. Open annotation page
4. Click "Blur Tool" and draw regions
5. Verify blurred image in `annotated_blur/` folder
6. Check database for updated metadata

---

**Status**: ✅ Fully Implemented and Ready to Use

**Last Updated**: March 2, 2026
