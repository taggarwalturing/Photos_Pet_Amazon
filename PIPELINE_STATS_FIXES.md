# Pipeline Statistics - Bug Fixes

## Issues Identified

### 1. ❌ Blurred Images Not Being Counted
**Problem:** The query was only counting images where `human_faces_detected > 0`, missing images that were processed with blurring status.

**Solution:** Updated the query to include:
- Images with `human_faces_detected > 0` (detected faces)
- Images with `compliance_status` in ('blurred', 'processed', 'obfuscated') - which indicates face processing occurred

### 2. ❌ Pipeline Statistics Appearing Twice
**Problem:** Pipeline Statistics component was being rendered twice on the Pipeline tab:
1. Once in `AdminDashboard.jsx` inside the pipeline tab
2. Once in `MasterPipelineTab.jsx` as a built-in summary section

**Solution:** 
- Removed the old basic statistics from `MasterPipelineTab.jsx`
- Integrated the new detailed `PipelineStatistics` component into `MasterPipelineTab.jsx`
- Removed the duplicate from `AdminDashboard.jsx`

## Files Modified

### Backend
- **`backend/app/routers/pipeline.py`**
  - Updated `with_faces` SQL query to correctly identify blurred images
  - Now checks both `human_faces_detected > 0` AND compliance status flags

### Frontend
- **`frontend/src/components/MasterPipelineTab.jsx`**
  - Added import for `PipelineStatistics` component
  - Replaced old basic statistics section with new detailed component
  
- **`frontend/src/pages/AdminDashboard.jsx`**
  - Removed duplicate `PipelineStatistics` import and usage
  - Simplified pipeline tab rendering to only use `MasterPipelineTab`

## Result

✅ Blurred images are now correctly counted in statistics
✅ Pipeline Statistics appears only once on the page
✅ All statistics now accurately reflect database state
✅ No duplicate sections on UI

## Testing

To verify the fixes:
1. Navigate to Admin Dashboard → Pipeline tab
2. Check that "Pipeline Statistics" header appears only once
3. Verify "Images with Faces (Blurred)" count reflects actual blurred images in database
4. Refresh the page to ensure stats update correctly
