# Database Schema — Photo Pets Annotation Platform

**Database**: `photo_pets` (PostgreSQL) · **Tables**: 4

---

## `users`

| Column | Description |
|--------|-----------|
| `id` | Primary key |
| `username` | Login username (Turing email) |
| `password_hash` | Bcrypt-hashed password |
| `full_name` | Display name |
| `role` | `admin` or `annotator` |
| `is_active` | Whether account is active |
| `assigned_image_count` | Number of images assigned to this user |
| `created_at` | Account creation time |

---

## `images`

| Column | Description |
|--------|-----------|
| `id` | Primary key |
| `image_id` | Filename without extension |
| `filename` | Full filename (e.g. `abc123.jpeg`) |
| `url` | Image URL |
| `source_folder_id` | GCS folder this image came from |
| `original_filename` | Original filename before pipeline renaming |
| `image_drive_id` | Google Drive file ID (legacy) |
| `gcs_input_path` | GCS path to original image |
| `gcs_annotated_path` | GCS path to annotated/processed image |
| `gcs_folder` | GCS subfolder: `input` / `clean` / `blur` |
| `is_duplicate` | Whether marked as duplicate |
| `parent_image_id` | ID of parent image if duplicate (FK → images) |
| `pipeline_status` | Pipeline processing status |
| `compliance_status` | Compliance check result |
| `human_faces_detected` | Number of human faces detected |
| `is_ai_generated` | Whether flagged as AI-generated |
| `ai_detection_confidence` | AI detection confidence (0–100) |
| `marked_ai_by` | User who flagged as AI-generated (FK → users) |
| `marked_ai_at` | When flagged as AI-generated |
| `human_visible` | Whether a human is visible in the image |
| `human_visible_marked_by` | User who marked human visibility (FK → users) |
| `human_visible_marked_at` | When human visibility was marked |
| `is_programmatically_blurred` | Whether pipeline auto-blurred human faces |
| `is_manually_modified` | Whether image was manually modified |
| `is_using_processed` | Whether UI serves the processed version |
| `manually_blurred` | Whether manual blur is applied |
| `manually_blurred_by` | User who applied manual blur (FK → users) |
| `manually_blurred_at` | When manual blur was applied |
| `is_blurred_annotator` | Whether an annotator applied blur |
| `is_restore_annotator` | Whether an annotator removed blur |
| `blur_regions` | Blur bounding boxes JSON: `[{x, y, width, height}]` |
| `processed_url` | URL of processed/blurred version |
| `processing_method` | Processing method used |
| `annotation_status` | `pending` / `in_progress` / `completed` |
| `annotations` | Human selections JSON: `{"cat_key": {"selected_option_ids": [...], "selected_labels": [...]}}` |
| `annotated_by` | User who annotated (FK → users) |
| `annotated_at` | When annotation was saved |
| `annotation_history` | Append-only audit log of all annotation/review actions |
| `review_status` | `pending` / `approved` / `rework_requested` / `rework_completed` / `edit_requested` / `edit_approved` |
| `review_note` | Reviewer's note |
| `reviewed_by` | User who reviewed (FK → users) |
| `reviewed_at` | When review was done |
| `is_improper` | Whether marked as improper |
| `improper_reason` | Reason for marking improper |
| `marked_improper_by` | User who marked improper (FK → users) |
| `marked_improper_at` | When marked improper |
| `assigned_annotator` | Annotator this image is assigned to (FK → users) |
| `locked_by` | User currently editing this image (FK → users) |
| `locked_at` | When the lock was acquired |
| `deliverable_image_path` | GCS path to final deliverable after approval |
| `arbiter_labels` | AI classifier suggestions JSON: `{"lighting": {"key": "well_lit", "label": "Well-lit..."}}` |
| `batch_number` | Pipeline batch number — auto-increments per pipeline run, not overwritten on re-runs |
| `created_at` | When image record was created |
| `updated_at` | Last modification time |

---

## `drive_folders`

| Column | Description |
|--------|-----------|
| `id` | Primary key |
| `folder_id` | GCS/Drive folder ID (unique) |
| `folder_name` | Human-readable folder name |
| `added_at` | When folder was registered |
| `status` | `pending` / `downloading` / `processing` / `completed` / `failed` |
| `last_run_at` | When pipeline last ran on this folder |
| `total_in_drive` | Total images found in folder |
| `downloaded_count` | Images successfully downloaded |
| `unique_count` | Unique images after deduplication |
| `duplicate_count` | Duplicates found |
| `blurred_count` | Images with human faces blurred |
| `clean_count` | Clean images (no blur needed) |
| `failed_count` | Images that failed processing |
| `batch_number` | Pipeline batch number — same as images.batch_number for the run that processed this folder |
| `notes` | General notes |
| `error_log` | Error messages from pipeline |

---

## `arbiter_predictions`

| Column | Description |
|--------|-----------|
| `id` | Primary key |
| `image_id` | Filename without extension (unique, used for cross-environment matching) |
| `predictions` | Raw AI predictions JSON: `{"lighting": "well_lit", "viewpoint": "front_eye_level"}` |
| `reasoning` | Per-category reasoning from each model |
| `model_used` | Models used (e.g. `gemini+openai+o3`) |
| `status` | `pending` / `completed` / `failed` |
| `error_message` | Error message if classification failed |
| `created_at` | When prediction was created |
| `updated_at` | Last update time |
