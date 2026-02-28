"""
Update the pipeline status in the backend API to reflect the completed terminal pipeline run.
"""
import requests
import json
from pathlib import Path

# Read the actual pipeline results
results_file = Path(__file__).parent / "master_pipeline" / "biometric_compliance_pipeline" / "results" / "obfuscation_results.json"

if not results_file.exists():
    print(f"❌ Results file not found: {results_file}")
    exit(1)

with open(results_file, 'r') as f:
    results = json.load(f)

print("📊 Actual Pipeline Results:")
print(f"   Total images: {results['total_images']}")
print(f"   Obfuscated: {results['statistics']['obfuscated']}")
print(f"   Clean (no faces): {results['statistics']['clean']}")
print(f"   Verification failed (QA): {results['statistics']['verification_failed']}")
print(f"   Failed: {results['statistics']['failed']}")
print()

# Create a status update payload
status_update = {
    "is_running": False,
    "current_step": "completed",
    "progress": {
        "download": {
            "status": "completed",
            "current": 720,
            "total": 720,
            "message": "Downloaded 720 images from Google Drive"
        },
        "deduplicate": {
            "status": "completed",
            "current": 696,
            "total": 696,
            "message": f"Found 696 unique images (removed 24 duplicates)"
        },
        "biometric": {
            "status": "completed",
            "current": 696,
            "total": 696,
            "message": f"Processed {results['total_images']} images - {results['statistics']['clean']} clean, {results['statistics']['obfuscated']} obfuscated, {results['statistics']['verification_failed']} QA review"
        }
    },
    "completed_at": "2026-02-28T18:12:00",
    "errors": [],
    "summary": {
        "total_processed": results['total_images'],
        "clean": results['statistics']['clean'],
        "obfuscated": results['statistics']['obfuscated'],
        "qa_required": results['statistics']['verification_failed'],
        "failed": results['statistics']['failed']
    }
}

print("🔄 Updating pipeline status via API...")
print()

# Try to update via API (this won't work directly, but we can update the module)
# Instead, let's write a Python script that imports and updates the status directly

print("📝 To update the UI, the backend needs to be restarted or we need to")
print("   update the in-memory pipeline_status variable.")
print()
print("   The easiest way is to run the pipeline from the UI itself next time.")
print()
print("   For now, here's what the status should show:")
print(json.dumps(status_update, indent=2))
