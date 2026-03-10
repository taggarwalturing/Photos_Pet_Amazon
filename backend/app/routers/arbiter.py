"""
Arbiter Classifier API
=======================
Admin endpoints for running the 3-model arbiter classifier pipeline
on the final images from the master pipeline.

Strategy: Gemini + OpenAI classify in parallel → Arbiter resolves disagreements.
"""

import json
import os
import base64
import io
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests as http_requests
from PIL import Image as PILImage
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from sqlalchemy.orm import joinedload
from sqlalchemy import func as sa_func

from app.database import get_db, SessionLocal
from app.dependencies import require_admin
from app.models.user import User
from app.models.image import Image as ImageModel
from app.models.annotation import Annotation, AnnotationSelection
from app.models.category import Category
from app.models.option import Option

router = APIRouter(prefix="/admin/arbiter", tags=["Arbiter Classifier"])

# ─── Directories ──────────────────────────────────────────────
from app.utils import get_pipeline_workspace as _gp_ws
ARBITER_DIR = Path(__file__).parent.parent.parent / "arbiter_classifier"
PIPELINE_WORKSPACE = _gp_ws()
FINAL_OUTPUT_DIR = PIPELINE_WORKSPACE / "deliverable"  # legacy fallback
RESULTS_DIR = ARBITER_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = RESULTS_DIR / "final_images_results.json"
ERRORS_FILE = RESULTS_DIR / "failed_images.json"


def _get_all_final_images() -> list:
    """
    DB-driven: get unique (non-duplicate) images, download from GCS if needed.

    Returns a sorted list of Path objects (local paths to images).
    """
    from app.database import SessionLocal
    from app.utils.gcs import download_blob_to_file, gcs_path as _gcs_path

    db = SessionLocal()
    try:
        # Only fetch unique (non-duplicate) images from DB
        db_images = db.query(ImageModel).filter(
            ImageModel.is_duplicate == False,  # noqa: E712
        ).all()
    finally:
        db.close()

    if not db_images:
        return []

    gcs_cache_dir = PIPELINE_WORKSPACE / "_gcs_arbiter_cache"
    gcs_cache_dir.mkdir(parents=True, exist_ok=True)

    images = []
    for img in db_images:
        fname = img.filename
        if not fname:
            continue
        local_path = gcs_cache_dir / fname
        if local_path.exists() and local_path.stat().st_size > 0:
            images.append(local_path)
            continue
        # Download from GCS
        folder_id = img.source_drive_folder_id or ""
        gcs_folder = img.gcs_folder or "clean"
        # Try annotated sub-stage first, then input
        downloaded = False
        for stage in (gcs_folder, "input"):
            try:
                blob_path = _gcs_path(folder_id, fname, stage)
                download_blob_to_file(blob_path, str(local_path))
                if local_path.exists() and local_path.stat().st_size > 0:
                    downloaded = True
                    break
            except Exception:
                continue
        if downloaded:
            images.append(local_path)
        else:
            print(f"[Arbiter] Could not download {fname} for folder {folder_id}")

    return sorted(images, key=lambda x: x.name)


def _get_per_folder_image_counts() -> dict:
    """
    Returns per-folder image counts for the arbiter.
    { folder_id: { "folder_name": str, "total": int, "filenames": set } }
    """
    from app.database import SessionLocal
    from app.models.drive_folder import DriveFolder

    db = SessionLocal()
    try:
        db_images = db.query(
            ImageModel.source_drive_folder_id,
            ImageModel.filename,
        ).filter(
            ImageModel.is_duplicate == False,  # noqa: E712
        ).all()

        folders_db = {f.folder_id: f.folder_name or f.folder_id[:16] + "..."
                      for f in db.query(DriveFolder).all()}
    finally:
        db.close()

    result = {}
    for folder_id, fname in db_images:
        fid = folder_id or "__unassigned__"
        if fid not in result:
            result[fid] = {
                "folder_name": folders_db.get(fid, fid[:16] + "..."),
                "total": 0,
                "filenames": set(),
            }
        result[fid]["total"] += 1
        result[fid]["filenames"].add(fname)
    return result

CATEGORIES = ["lighting", "viewpoint", "environment", "occlusion", "activity", "multipet"]

# ─── In-memory pipeline status ────────────────────────────────
arbiter_status = {
    "is_running": False,
    "current_image": None,
    "processed": 0,
    "total": 0,
    "agreements": 0,
    "arbiter_calls": 0,
    "errors": [],
    "failed_count": 0,
    "started_at": None,
    "completed_at": None,
    "current_step": None,   # "idle" | "running" | "completed" | "failed"
}

_stop_event = threading.Event()


# ─── Config Loader ────────────────────────────────────────────
def _read_env_file(filepath: Path) -> dict:
    """Parse a .env file into a dict (ignoring comments and blank lines)."""
    result = {}
    if filepath.exists():
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
    return result


def load_arbiter_config():
    """
    Load arbiter config by re-reading backend/.env fresh every time.
    This ensures API key changes are picked up without a server restart.
    Priority: backend/.env (fresh read) > settings.env fallback > os.environ
    """
    # 1. Fresh-read backend/.env file (NOT from cached os.environ)
    backend_env = Path(__file__).parent.parent.parent / ".env"
    fresh_env = _read_env_file(backend_env)

    # 2. Fallback: arbiter settings.env (if it exists)
    file_config = _read_env_file(ARBITER_DIR / "config" / "settings.env")

    # 3. Merge: fresh .env > settings.env fallback > os.environ
    keys = [
        "TURING_API_URL", "TURING_API_KEY", "TURING_GW_KEY", "TURING_AUTH",
        "GEMINI_MODEL", "GEMINI_PROVIDER", "GEMINI_PROMPT_VERSION",
        "OPENAI_MODEL", "OPENAI_PROVIDER", "OPENAI_PROMPT_VERSION",
        "ARBITER_MODEL", "ARBITER_PROVIDER", "ARBITER_PROMPT_VERSION",
        "ARBITER_BATCH_SIZE", "ARBITER_MAX_RETRIES", "ARBITER_TIMEOUT_SECONDS",
        "ARBITER_PARALLEL_WORKERS", "ARBITER_PIPELINE_VERSION",
        "BATCH_SIZE", "MAX_RETRIES", "TIMEOUT_SECONDS",
        "PARALLEL_WORKERS", "PIPELINE_VERSION", "TEMPERATURE",
    ]
    config = {}
    for key in keys:
        if key in fresh_env:
            config[key] = fresh_env[key]
        elif key in file_config:
            config[key] = file_config[key]
        elif os.environ.get(key):
            config[key] = os.environ[key]

    # Normalize: ARBITER_ prefixed keys map to legacy keys for compatibility
    if "ARBITER_BATCH_SIZE" in config and "BATCH_SIZE" not in config:
        config["BATCH_SIZE"] = config["ARBITER_BATCH_SIZE"]
    if "ARBITER_TIMEOUT_SECONDS" in config and "TIMEOUT_SECONDS" not in config:
        config["TIMEOUT_SECONDS"] = config["ARBITER_TIMEOUT_SECONDS"]
    if "ARBITER_PARALLEL_WORKERS" in config and "PARALLEL_WORKERS" not in config:
        config["PARALLEL_WORKERS"] = config["ARBITER_PARALLEL_WORKERS"]
    if "ARBITER_PIPELINE_VERSION" in config and "PIPELINE_VERSION" not in config:
        config["PIPELINE_VERSION"] = config["ARBITER_PIPELINE_VERSION"]

    return config


def load_prompt(name: str, version: str) -> str:
    prompt_file = ARBITER_DIR / "prompts" / f"{name}_v{version}.txt"
    if prompt_file.exists():
        content = prompt_file.read_text()
        lines = [l for l in content.split("\n") if not l.startswith("#")]
        return "\n".join(lines).strip()
    raise FileNotFoundError(f"Prompt not found: {prompt_file}")


# ─── Image Encoding ──────────────────────────────────────────
def encode_image(image_path: str, max_size_mb: float = 4.0) -> tuple:
    with open(image_path, "rb") as f:
        data = f.read()

    size_mb = len(data) / (1024 * 1024)
    suffix = Path(image_path).suffix.lower()

    if size_mb > max_size_mb:
        img = PILImage.open(image_path)
        ratio = (max_size_mb / size_mb) ** 0.5
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG" if suffix == ".png" else "JPEG", quality=85)
        data = buf.getvalue()

    media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    return base64.b64encode(data).decode("utf-8"), media_map.get(suffix, "image/jpeg")


# ─── API Calls ────────────────────────────────────────────────
def call_vision_api(api_url, headers, model, provider, prompt, image_b64, mime, timeout):
    payload = {
        "model": model,
        "provider": provider,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}}
            ]
        }],
        "temperature": 0,
        "max_tokens": 1000,
    }
    try:
        resp = http_requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code in [200, 201]:
            text = resp.json()["choices"][0]["message"]["content"]
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        else:
            # Surface non-200 errors (402 budget, 429 rate limit, etc.)
            error_body = resp.text[:300]
            return {"error": f"API returned {resp.status_code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}


def call_text_api(api_url, headers, model, provider, prompt, timeout):
    payload = {
        "model": model,
        "provider": provider,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 1000,
    }
    try:
        resp = http_requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code in [200, 201]:
            text = resp.json()["choices"][0]["message"]["content"]
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        else:
            error_body = resp.text[:300]
            return {"error": f"API returned {resp.status_code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}


# ─── Classification helpers ──────────────────────────────────
def extract_prediction(result: dict, category: str):
    cat_data = result.get(category, {})
    if isinstance(cat_data, dict):
        return cat_data.get("prediction", "None"), cat_data.get("reasoning", "")
    return str(cat_data) if cat_data else "None", ""


def classify_single_image(image_path, cfg):
    """Classify one image through both models, then arbiter on disagreements."""
    try:
        image_b64, mime = encode_image(image_path)
    except Exception as e:
        return {"error": str(e)}

    api_url = cfg["api_url"]
    headers = cfg["headers"]
    timeout = cfg["timeout"]

    # 1. Run Gemini + OpenAI in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        g_fut = ex.submit(call_vision_api, api_url, headers,
                          cfg["gemini_model"], cfg["gemini_provider"],
                          cfg["gemini_prompt"], image_b64, mime, timeout)
        o_fut = ex.submit(call_vision_api, api_url, headers,
                          cfg["openai_model"], cfg["openai_provider"],
                          cfg["openai_prompt"], image_b64, mime, timeout)
        gemini = g_fut.result()
        openai = o_fut.result()

    # If both models returned errors, propagate as a failure
    if "error" in gemini and "error" in openai:
        return {"error": f"Both models failed — Gemini: {gemini['error'][:200]} | OpenAI: {openai['error'][:200]}"}
    # If one model failed, propagate as a failure (partial results are unreliable)
    if "error" in gemini:
        return {"error": f"Gemini failed: {gemini['error'][:300]}"}
    if "error" in openai:
        return {"error": f"OpenAI failed: {openai['error'][:300]}"}

    # 2. Compare predictions
    predictions = {}
    disagreements = {}
    agreements = 0

    for cat in CATEGORIES:
        g_pred, g_reason = extract_prediction(gemini, cat)
        o_pred, o_reason = extract_prediction(openai, cat)
        if g_pred == o_pred:
            predictions[cat] = {
                "final": g_pred, "status": "agree",
                "gemini": g_pred, "openai": o_pred,
                "gemini_reason": g_reason, "openai_reason": o_reason,
            }
            agreements += 1
        else:
            disagreements[cat] = {
                "gemini_pred": g_pred, "gemini_reason": g_reason,
                "openai_pred": o_pred, "openai_reason": o_reason,
            }

    # 3. Call arbiter for disagreements
    arbiter_calls = 0
    if disagreements:
        arbiter_calls = 1
        arbiter_input = cfg["arbiter_prompt"] + "\n\n## Disagreements to Resolve:\n\n"
        for cat, data in disagreements.items():
            arbiter_input += f"""
### Category: {cat}

Model A (Gemini):
- Prediction: {data['gemini_pred']}
- Reasoning: {data['gemini_reason']}

Model B (OpenAI):
- Prediction: {data['openai_pred']}
- Reasoning: {data['openai_reason']}

---
"""
        arbiter_input += "\nReturn your decisions as JSON."
        arbiter_result = call_text_api(api_url, headers,
                                       cfg["arbiter_model"], cfg["arbiter_provider"],
                                       arbiter_input, timeout)

        for cat, data in disagreements.items():
            arbiter_decision = arbiter_result.get(cat, {})
            winner = arbiter_decision.get("winner", "A")
            final_pred = data["openai_pred"] if winner == "B" else data["gemini_pred"]
            if "final_prediction" in arbiter_decision:
                final_pred = arbiter_decision["final_prediction"]
            predictions[cat] = {
                "final": final_pred, "status": "arbiter",
                "gemini": data["gemini_pred"], "openai": data["openai_pred"],
                "gemini_reason": data["gemini_reason"], "openai_reason": data["openai_reason"],
                "arbiter_winner": winner,
                "arbiter_confidence": arbiter_decision.get("confidence", "unknown"),
                "arbiter_rationale": arbiter_decision.get("rationale", ""),
            }

    return {
        "predictions": predictions,
        "agreement_count": agreements,
        "arbiter_calls": arbiter_calls,
        "gemini_raw": gemini,
        "openai_raw": openai,
    }


# ─── Helpers for error tracking ───────────────────────────────

def _get_retry_count(failed_list, image_name):
    """Get the highest retry_count for a given image in the failed list."""
    for entry in reversed(failed_list):
        if entry.get("image") == image_name:
            return entry.get("retry_count", 0)
    return 0


def _save_results_and_errors(results, failed_images, cfg):
    """Save both results and errors files atomically."""
    save_data = {
        "results": results,
        "metadata": {
            "gemini_model": cfg["gemini_model"],
            "openai_model": cfg["openai_model"],
            "arbiter_model": cfg["arbiter_model"],
            "total_images": len(results),
            "failed_count": len(failed_images),
            "source": "deliverable",
            "last_updated": datetime.now().isoformat(),
        },
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(save_data, f, indent=2)

    # Save failed images
    errors_data = {
        "failed": failed_images,
        "last_updated": datetime.now().isoformat(),
    }
    with open(ERRORS_FILE, "w") as f:
        json.dump(errors_data, f, indent=2)


# ─── Background runner ───────────────────────────────────────
def run_arbiter_background():
    global arbiter_status
    _stop_event.clear()

    try:
        config = load_arbiter_config()

        # Build runtime config dict
        cfg = {
            "api_url": config.get("TURING_API_URL", "https://kong.turing.com/api/v2/chat"),
            "headers": {
                "Content-Type": "application/json",
                "x-api-key": config.get("TURING_API_KEY", ""),
                "x-api-gw-key": config.get("TURING_GW_KEY", ""),
                "Authorization": config.get("TURING_AUTH", ""),
            },
            "gemini_model": config.get("GEMINI_MODEL", "gemini-2.5-pro"),
            "gemini_provider": config.get("GEMINI_PROVIDER", "google"),
            "openai_model": config.get("OPENAI_MODEL", "gpt-4o"),
            "openai_provider": config.get("OPENAI_PROVIDER", "openai"),
            "arbiter_model": config.get("ARBITER_MODEL", "o3"),
            "arbiter_provider": config.get("ARBITER_PROVIDER", "openai"),
            "timeout": int(config.get("TIMEOUT_SECONDS", "120")),
            "gemini_prompt": load_prompt("gemini_reasoning", config.get("GEMINI_PROMPT_VERSION", "1")),
            "openai_prompt": load_prompt("openai_reasoning", config.get("OPENAI_PROMPT_VERSION", "1")),
            "arbiter_prompt": load_prompt("arbiter", config.get("ARBITER_PROMPT_VERSION", "1")),
        }
        workers = int(config.get("PARALLEL_WORKERS", "5"))
        batch_size = int(config.get("BATCH_SIZE", "50"))

        # Collect images from all per-folder workspaces + legacy
        image_files = _get_all_final_images()

        if not image_files:
            arbiter_status["is_running"] = False
            arbiter_status["current_step"] = "failed"
            arbiter_status["errors"].append("No images found in any final output folder")
            arbiter_status["completed_at"] = datetime.now().isoformat()
            return

        # Load existing results (resume support)
        existing = {"results": [], "metadata": {}}
        if RESULTS_FILE.exists():
            try:
                with open(RESULTS_FILE) as f:
                    existing = json.load(f)
            except json.JSONDecodeError:
                pass

        processed_names = {r["image"] for r in existing.get("results", [])}
        to_process = [p for p in image_files if p.name not in processed_names]

        arbiter_status["total"] = len(image_files)
        arbiter_status["processed"] = len(processed_names)
        arbiter_status["current_step"] = "running"
        arbiter_status["already_classified"] = len(processed_names)
        arbiter_status["pending_this_run"] = len(to_process)
        arbiter_status["processed_this_run"] = 0

        # Build per-folder tracking
        per_folder = _get_per_folder_image_counts()
        folder_progress = {}
        for fid, info in per_folder.items():
            classified_in_folder = len(info["filenames"] & processed_names)
            pending_in_folder = info["total"] - classified_in_folder
            folder_progress[fid] = {
                "folder_name": info["folder_name"],
                "total": info["total"],
                "classified": classified_in_folder,
                "pending": pending_in_folder,
                "status": "completed" if pending_in_folder == 0 else "running",
            }
        arbiter_status["folder_progress"] = folder_progress

        results = existing.get("results", [])
        results_lock = threading.Lock()

        # Load existing errors for resume
        failed_images = []
        if ERRORS_FILE.exists():
            try:
                with open(ERRORS_FILE) as f:
                    existing_errors = json.load(f)
                    failed_images = existing_errors.get("failed", [])
            except json.JSONDecodeError:
                pass

        # Remove previously-failed images from the skip list (so they get retried)
        previously_failed_names = {f["image"] for f in failed_images}

        if not to_process:
            # Check if there are failed images that need to be tracked
            arbiter_status["is_running"] = False
            arbiter_status["current_step"] = "completed"
            arbiter_status["completed_at"] = datetime.now().isoformat()
            arbiter_status["failed_count"] = len(failed_images)
            return

        # Clear previously-failed entries that are being retried
        failed_images = [f for f in failed_images if f["image"] not in {p.name for p in to_process}]

        def process_one(img_path):
            if _stop_event.is_set():
                return None
            result = classify_single_image(str(img_path), cfg)
            if "error" in result:
                return {"image": img_path.name, "error": result["error"]}
            return {
                "image": img_path.name,
                "predictions": {cat: result["predictions"][cat]["final"] for cat in CATEGORIES},
                "agreement_count": result["agreement_count"],
                "arbiter_calls": result["arbiter_calls"],
                "details": result["predictions"],
            }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_one, p): p for p in to_process}
            count = 0

            for future in as_completed(futures):
                if _stop_event.is_set():
                    break

                result = future.result()
                if result is None:
                    continue

                with results_lock:
                    if "error" in result:
                        arbiter_status["errors"].append(f"{result['image']}: {result['error']}")
                        # Persist to failed images list
                        failed_images.append({
                            "image": result["image"],
                            "error": result["error"],
                            "failed_at": datetime.now().isoformat(),
                            "retry_count": _get_retry_count(failed_images, result["image"]) + 1,
                        })
                    else:
                        results.append(result)
                        arbiter_status["agreements"] += result.get("agreement_count", 0)
                        arbiter_status["arbiter_calls"] += result.get("arbiter_calls", 0)

                    arbiter_status["processed"] = len(results)
                    arbiter_status["failed_count"] = len(failed_images)
                    arbiter_status["current_image"] = result.get("image", "")
                    count += 1
                    arbiter_status["processed_this_run"] = count

                    # Update per-folder progress
                    img_name = result.get("image", "")
                    fp = arbiter_status.get("folder_progress", {})
                    for fid, finfo in fp.items():
                        pf_counts = per_folder.get(fid, {})
                        if img_name in pf_counts.get("filenames", set()):
                            finfo["classified"] += 1
                            finfo["pending"] = max(0, finfo["pending"] - 1)
                            if finfo["pending"] == 0:
                                finfo["status"] = "completed"
                            break

                    # Save periodically
                    if count % batch_size == 0 or count == len(to_process):
                        _save_results_and_errors(results, failed_images, cfg)
                        # Also save to database
                        _save_predictions_to_db(results[-batch_size:])

        # Final save
        _save_results_and_errors(results, failed_images, cfg)

        # Save all results to database (final pass to catch any missed)
        _save_predictions_to_db(results)

        arbiter_status["is_running"] = False
        arbiter_status["failed_count"] = len(failed_images)
        if _stop_event.is_set():
            arbiter_status["current_step"] = "stopped"
        else:
            arbiter_status["current_step"] = "completed"
        arbiter_status["completed_at"] = datetime.now().isoformat()
        print(f"[ARBITER] Classification complete. {len(results)} succeeded, {len(failed_images)} failed.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        arbiter_status["is_running"] = False
        arbiter_status["current_step"] = "failed"
        arbiter_status["completed_at"] = datetime.now().isoformat()
        arbiter_status["errors"].append(f"Exception: {str(e)}")


# ─── Save predictions to database ─────────────────────────────

# Mapping: arbiter short labels → option labels in the database
ARBITER_TO_OPTION_LABEL = {
    # lighting
    "dusk_dawn": "Dusk-dawn lighting",
    "harsh_sunlight": "Harsh outdoor sunlight with shadows",
    "low_light": "Low light conditions",
    "well_lit": "Well-lit conditions (typical)",
    # viewpoint
    "front_eye_level": "Front-facing at eye level (typical)",
    "ground_level": "Ground-level view",
    "no_head": "No head showing",
    "head_only": "Partial view (head only)",
    "top_down": "Top-down view",
    # environment
    "car_carrier": "In car-carrier",
    "indoor": "Indoor setting (typical)",
    "outdoor_dirt": "Outdoor dirt road",
    "snow": "Snow environment",
    "vet_clinic": "Vet clinic",
    "yard_complex": "Yard with a complex background",
    # occlusion
    "behind_furniture": "Behind furniture (face only)",
    "full_body": "Full-body, unobstructed (typical)",
    "under_blanket": "Partially hidden under a blanket",
    "peeking_box": "Peeking out of box-carrier",
    "toy_obscuring": "Toy obscuring part of body",
    # activity
    "eating_drinking": "Eating-drinking",
    "jumping": "Jumping to catch toy",
    "playing": "Playing with another pet",
    "running": "Running with motion blur",
    "sitting_posed": "Sitting still-posed (typical)",
    "sleeping": "Sleeping-curled up",
    # multipet
    "pet_with_lookalike": "Pet with breed lookalike",
    "single_pet": "Single pet (typical)",
    "three_same": "Three pets of same breed",
    "two_similar": "Two similar-looking pets together",
    # fallback
    "None": "None of the Above",
}

# Mapping: arbiter category name → DB category name
ARBITER_CAT_TO_DB_CAT = {
    "lighting": "Lighting Variation",
    "viewpoint": "Angle & Perspective Variation",
    "environment": "Environmental Context Variation",
    "occlusion": "Occlusion & Partial Visibility",
    "activity": "Activity & Motion",
    "multipet": "Multi-Pet Disambiguation",
}


def _save_predictions_to_db(results_batch):
    """Save arbiter predictions to Image.arbiter_labels in the database."""
    try:
        db = SessionLocal()
        now = datetime.now()
        for result in results_batch:
            filename = result.get("image")
            predictions = result.get("predictions", {})
            if not filename or not predictions:
                continue
            image = db.query(ImageModel).filter(ImageModel.filename == filename).first()
            if image:
                image.arbiter_labels = predictions
                image.arbiter_classified_at = now
        db.commit()
        db.close()
    except Exception as e:
        print(f"[ARBITER] Error saving to DB: {e}")
        try:
            db.rollback()
            db.close()
        except Exception:
            pass


# ─── Error Categorization ─────────────────────────────────────

def _categorize_errors(errors: list) -> dict:
    """
    Parse error messages and categorize them so the UI can display
    clear, actionable banners instead of misleading 'None' predictions.
    """
    categories = {
        "budget_exceeded": 0,    # 402
        "forbidden": 0,          # 403
        "rate_limited": 0,       # 429
        "timeout": 0,            # timeout / connection errors
        "server_error": 0,       # 5xx
        "parse_error": 0,        # JSON parse failures
        "other": 0,
    }
    sample_errors = {}  # One sample per category for display

    for err in errors:
        err_lower = err.lower()
        if "402" in err or "budget" in err_lower:
            categories["budget_exceeded"] += 1
            sample_errors.setdefault("budget_exceeded", err)
        elif "403" in err or "forbidden" in err_lower:
            categories["forbidden"] += 1
            sample_errors.setdefault("forbidden", err)
        elif "429" in err or "rate limit" in err_lower or "too many" in err_lower:
            categories["rate_limited"] += 1
            sample_errors.setdefault("rate_limited", err)
        elif "timeout" in err_lower or "timed out" in err_lower or "connectionerror" in err_lower:
            categories["timeout"] += 1
            sample_errors.setdefault("timeout", err)
        elif any(code in err for code in ["500", "502", "503", "504"]):
            categories["server_error"] += 1
            sample_errors.setdefault("server_error", err)
        elif "json" in err_lower or "expecting value" in err_lower or "decode" in err_lower:
            categories["parse_error"] += 1
            sample_errors.setdefault("parse_error", err)
        else:
            categories["other"] += 1
            sample_errors.setdefault("other", err)

    # Determine the dominant error type
    total_errors = sum(categories.values())
    dominant_type = max(categories, key=categories.get) if total_errors > 0 else None
    is_api_issue = categories["budget_exceeded"] + categories["forbidden"] + categories["rate_limited"] > 0

    return {
        "total_errors": total_errors,
        "categories": {k: v for k, v in categories.items() if v > 0},
        "sample_errors": sample_errors,
        "dominant_type": dominant_type,
        "is_api_issue": is_api_issue,
        "actionable_message": _get_actionable_message(dominant_type, total_errors) if total_errors > 0 else None,
    }


def _get_actionable_message(dominant_type: str, total_errors: int) -> str:
    """Return a human-readable message for the dominant error type."""
    messages = {
        "budget_exceeded": f"🚫 API Budget Exceeded — The Turing API returned 402 errors for {total_errors} image(s). "
                          "Your API key has insufficient credits. Please top up the budget or contact your IT team.",
        "forbidden": f"🔒 API Access Forbidden — The Turing API returned 403 errors for {total_errors} image(s). "
                    "Check that your API key and authorization tokens are valid.",
        "rate_limited": f"⏱️ API Rate Limited — The Turing API returned 429 errors for {total_errors} image(s). "
                       "Too many requests were sent. Reduce parallel workers or wait before retrying.",
        "timeout": f"⏰ API Timeout — {total_errors} image(s) timed out during classification. "
                  "Try increasing the TIMEOUT_SECONDS in settings or reducing parallel workers.",
        "server_error": f"🔥 API Server Error — The Turing API returned server errors for {total_errors} image(s). "
                       "This is likely a temporary issue. Please retry later.",
        "parse_error": f"📄 Response Parse Error — {total_errors} image(s) returned unparseable responses. "
                      "The model output format may have changed.",
        "other": f"⚠️ {total_errors} image(s) failed with unexpected errors. Check the error details below.",
    }
    return messages.get(dominant_type, f"⚠️ {total_errors} classification errors occurred.")


# ─── Request / Response Models ────────────────────────────────
class ArbiterStartRequest(BaseModel):
    reprocess_folder_ids: Optional[List[str]] = None   # Re-classify all images in these folders
    reprocess_image_names: Optional[List[str]] = None  # Re-classify specific images by filename


# ─── API Endpoints ────────────────────────────────────────────

@router.get("/config")
def get_arbiter_config(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return current arbiter classifier configuration."""
    config = load_arbiter_config()

    # Fast image count from DB (avoid slow GCS listing on every page load)
    image_count = db.query(sa_func.count(ImageModel.id)).filter(
        ImageModel.is_duplicate == False,  # noqa: E712
    ).scalar() or 0

    # Per-folder breakdown and classification status
    per_folder = _get_per_folder_image_counts()

    # Check which images are already classified
    already_classified = set()
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE) as f:
                existing = json.load(f)
            already_classified = {r["image"] for r in existing.get("results", [])}
        except Exception:
            pass

    folder_stats = []
    for fid, info in per_folder.items():
        classified_in_folder = len(info["filenames"] & already_classified)
        folder_stats.append({
            "folder_id": fid,
            "folder_name": info["folder_name"],
            "total": info["total"],
            "classified": classified_in_folder,
            "pending": info["total"] - classified_in_folder,
            "status": "completed" if classified_in_folder == info["total"] else
                      "partial" if classified_in_folder > 0 else "pending",
        })

    return {
        "gemini_model": config.get("GEMINI_MODEL", "gemini-2.5-pro"),
        "gemini_provider": config.get("GEMINI_PROVIDER", "google"),
        "openai_model": config.get("OPENAI_MODEL", "gpt-4o"),
        "openai_provider": config.get("OPENAI_PROVIDER", "openai"),
        "arbiter_model": config.get("ARBITER_MODEL", "o3"),
        "arbiter_provider": config.get("ARBITER_PROVIDER", "openai"),
        "parallel_workers": int(config.get("PARALLEL_WORKERS", "5")),
        "batch_size": int(config.get("BATCH_SIZE", "50")),
        "timeout_seconds": int(config.get("TIMEOUT_SECONDS", "120")),
        "pipeline_version": config.get("PIPELINE_VERSION", "1"),
        "available_images": image_count,
        "already_classified": len(already_classified),
        "pending_images": image_count - len(already_classified),
        "categories": CATEGORIES,
        "folder_stats": folder_stats,
    }


@router.get("/status")
def get_arbiter_status(admin: User = Depends(require_admin)):
    """Get current arbiter pipeline execution status, including API error categorization."""
    enriched = dict(arbiter_status)
    enriched["api_error_summary"] = _categorize_errors(arbiter_status.get("errors", []))
    return enriched


@router.post("/start")
def start_arbiter(
    request: ArbiterStartRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
):
    """Start the arbiter classifier on final pipeline images."""
    global arbiter_status

    if arbiter_status["is_running"]:
        raise HTTPException(status_code=400, detail="Arbiter pipeline is already running")

    if not _get_all_final_images():
        raise HTTPException(status_code=400, detail="No final output images found. Run the master pipeline first.")

    # Collect images to reprocess — from folder IDs and/or individual image names
    reprocess_names = set(request.reprocess_image_names or [])

    # Resolve folder IDs → image filenames
    if request.reprocess_folder_ids:
        per_folder = _get_per_folder_image_counts()
        for fid in request.reprocess_folder_ids:
            if fid in per_folder:
                reprocess_names |= per_folder[fid]["filenames"]

    if reprocess_names:
        # Remove selected images from existing results so they get re-classified
        if RESULTS_FILE.exists():
            try:
                with open(RESULTS_FILE) as f:
                    existing = json.load(f)
                existing["results"] = [
                    r for r in existing.get("results", [])
                    if r.get("image") not in reprocess_names
                ]
                with open(RESULTS_FILE, "w") as f:
                    json.dump(existing, f, indent=2)
            except Exception:
                pass
        # Also remove from failed list
        if ERRORS_FILE.exists():
            try:
                with open(ERRORS_FILE) as f:
                    existing_errors = json.load(f)
                existing_errors["failed"] = [
                    e for e in existing_errors.get("failed", [])
                    if e.get("image") not in reprocess_names
                ]
                with open(ERRORS_FILE, "w") as f:
                    json.dump(existing_errors, f, indent=2)
            except Exception:
                pass

    # Reset status
    arbiter_status = {
        "is_running": True,
        "current_image": None,
        "processed": 0,
        "total": 0,
        "agreements": 0,
        "arbiter_calls": 0,
        "errors": [],
        "failed_count": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "current_step": "initializing",
    }

    background_tasks.add_task(run_arbiter_background)

    folder_ids = request.reprocess_folder_ids or []
    msg = (
        f"Arbiter started — re-classifying {len(reprocess_names)} image(s) from {len(folder_ids)} folder(s)"
        if reprocess_names else "Arbiter classifier started"
    )
    return {"message": msg, "status": arbiter_status}


@router.post("/stop")
def stop_arbiter(admin: User = Depends(require_admin)):
    """Stop the running arbiter pipeline gracefully."""
    if not arbiter_status["is_running"]:
        raise HTTPException(status_code=400, detail="Arbiter pipeline is not running")
    _stop_event.set()
    return {"message": "Stop signal sent. Pipeline will stop after current batch."}


@router.get("/results")
def get_arbiter_results(
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
    prediction: Optional[str] = None,
    status_filter: Optional[str] = None,  # "agree" | "arbiter"
    search: Optional[str] = None,
    admin: User = Depends(require_admin),
):
    """Get arbiter classification results with optional filters."""
    if not RESULTS_FILE.exists():
        return {"results": [], "metadata": {}, "total": 0, "page": page, "page_size": page_size, "summary": {}}

    with open(RESULTS_FILE) as f:
        data = json.load(f)

    results = data.get("results", [])
    metadata = data.get("metadata", {})

    # Filters
    if search:
        results = [r for r in results if search.lower() in r.get("image", "").lower()]

    if category and prediction:
        results = [r for r in results if r.get("predictions", {}).get(category) == prediction]

    if status_filter and category:
        results = [r for r in results
                   if r.get("details", {}).get(category, {}).get("status") == status_filter]

    # Compute summary before pagination
    all_results = data.get("results", [])
    total_images = len(all_results)
    total_agreements = sum(r.get("agreement_count", 0) for r in all_results)
    total_arbiter_calls = sum(r.get("arbiter_calls", 0) for r in all_results)
    total_categories = total_images * len(CATEGORIES)

    # Per-category stats
    cat_stats = {}
    for cat in CATEGORIES:
        labels = {}
        agree_count = 0
        arbiter_count = 0
        for r in all_results:
            detail = r.get("details", {}).get(cat, {})
            label = detail.get("final", "None")
            labels[label] = labels.get(label, 0) + 1
            if detail.get("status") == "agree":
                agree_count += 1
            elif detail.get("status") == "arbiter":
                arbiter_count += 1
        cat_stats[cat] = {
            "labels": labels,
            "agree_count": agree_count,
            "arbiter_count": arbiter_count,
        }

    # Load failed count and error categorization from errors file
    failed_count = 0
    api_error_summary = _categorize_errors([])
    if ERRORS_FILE.exists():
        try:
            with open(ERRORS_FILE) as ef:
                errors_data = json.load(ef)
                failed_list = errors_data.get("failed", [])
                failed_count = len(failed_list)
                error_strings = [f.get("error", "") for f in failed_list]
                api_error_summary = _categorize_errors(error_strings)
        except (json.JSONDecodeError, OSError):
            pass

    summary = {
        "total_images": total_images,
        "total_agreements": total_agreements,
        "total_arbiter_calls": total_arbiter_calls,
        "total_categories": total_categories,
        "agreement_rate": round(total_agreements / total_categories * 100, 1) if total_categories > 0 else 0,
        "failed_count": failed_count,
        "api_error_summary": api_error_summary,
        "category_stats": cat_stats,
    }

    # Pagination
    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    page_results = results[start:end]

    return {
        "results": page_results,
        "metadata": metadata,
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": summary,
    }


@router.post("/import-labels")
def import_labels_to_db(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Import arbiter predictions from results JSON into the Image table.
    Stores predictions as arbiter_labels so annotators see them as pre-filled suggestions.
    """
    if not RESULTS_FILE.exists():
        raise HTTPException(status_code=404, detail="No results file found. Run the classifier first.")

    with open(RESULTS_FILE) as f:
        data = json.load(f)

    results = data.get("results", [])
    if not results:
        raise HTTPException(status_code=400, detail="Results file is empty.")

    now = datetime.now()
    updated = 0
    not_found = []

    for result in results:
        filename = result.get("image")
        predictions = result.get("predictions", {})
        if not filename or not predictions:
            continue

        image = db.query(ImageModel).filter(ImageModel.filename == filename).first()
        if image:
            image.arbiter_labels = predictions
            image.arbiter_classified_at = now
            updated += 1
        else:
            not_found.append(filename)

    db.commit()

    return {
        "message": f"Imported labels for {updated} images",
        "updated": updated,
        "not_found_count": len(not_found),
        "not_found": not_found[:20],  # Show first 20
    }


@router.get("/failed")
def get_failed_images(admin: User = Depends(require_admin)):
    """Return the list of images that failed/errored during classification, with error categorization."""
    if not ERRORS_FILE.exists():
        return {"failed": [], "total": 0, "error_summary": _categorize_errors([])}

    try:
        with open(ERRORS_FILE) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"failed": [], "total": 0, "error_summary": _categorize_errors([])}

    failed = data.get("failed", [])

    # Categorize the error strings
    error_strings = [f.get("error", "") for f in failed]
    error_summary = _categorize_errors(error_strings)

    return {
        "failed": failed,
        "total": len(failed),
        "last_updated": data.get("last_updated"),
        "error_summary": error_summary,
    }


@router.post("/retry-failed")
def retry_failed_images(
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
):
    """
    Retry classification for images that previously failed/errored.
    Removes them from the failed list and re-runs classification only on those images.
    """
    global arbiter_status

    if arbiter_status["is_running"]:
        raise HTTPException(status_code=400, detail="Arbiter pipeline is already running")

    if not ERRORS_FILE.exists():
        raise HTTPException(status_code=400, detail="No failed images to retry")

    try:
        with open(ERRORS_FILE) as f:
            errors_data = json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Could not read errors file")

    failed = errors_data.get("failed", [])
    if not failed:
        raise HTTPException(status_code=400, detail="No failed images to retry")

    failed_names = [f["image"] for f in failed]

    # Reset status for retry run
    arbiter_status = {
        "is_running": True,
        "current_image": None,
        "processed": 0,
        "total": len(failed_names),
        "agreements": 0,
        "arbiter_calls": 0,
        "errors": [],
        "failed_count": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "current_step": "retrying_failed",
    }

    background_tasks.add_task(run_retry_failed_background, failed_names)

    return {
        "message": f"Retrying {len(failed_names)} failed images",
        "retrying": failed_names,
        "status": arbiter_status,
    }


def run_retry_failed_background(failed_names: list):
    """Background task: retry only the failed images."""
    global arbiter_status
    _stop_event.clear()

    try:
        config = load_arbiter_config()
        cfg = {
            "api_url": config.get("TURING_API_URL", "https://kong.turing.com/api/v2/chat"),
            "headers": {
                "Content-Type": "application/json",
                "x-api-key": config.get("TURING_API_KEY", ""),
                "x-api-gw-key": config.get("TURING_GW_KEY", ""),
                "Authorization": config.get("TURING_AUTH", ""),
            },
            "gemini_model": config.get("GEMINI_MODEL", "gemini-2.5-pro"),
            "gemini_provider": config.get("GEMINI_PROVIDER", "google"),
            "openai_model": config.get("OPENAI_MODEL", "gpt-4o"),
            "openai_provider": config.get("OPENAI_PROVIDER", "openai"),
            "arbiter_model": config.get("ARBITER_MODEL", "o3"),
            "arbiter_provider": config.get("ARBITER_PROVIDER", "openai"),
            "timeout": int(config.get("TIMEOUT_SECONDS", "120")),
            "gemini_prompt": load_prompt("gemini_reasoning", config.get("GEMINI_PROMPT_VERSION", "1")),
            "openai_prompt": load_prompt("openai_reasoning", config.get("OPENAI_PROMPT_VERSION", "1")),
            "arbiter_prompt": load_prompt("arbiter", config.get("ARBITER_PROMPT_VERSION", "1")),
        }
        workers = int(config.get("PARALLEL_WORKERS", "5"))

        # Resolve failed image names to actual file paths
        supported_exts = {".jpg", ".jpeg", ".png"}
        failed_set = set(failed_names)
        all_images = _get_all_final_images()
        to_retry = [p for p in all_images if p.name in failed_set]

        if not to_retry:
            arbiter_status["is_running"] = False
            arbiter_status["current_step"] = "completed"
            arbiter_status["completed_at"] = datetime.now().isoformat()
            arbiter_status["errors"].append("No matching image files found for retry")
            return

        # Load existing results to append successes
        existing = {"results": [], "metadata": {}}
        if RESULTS_FILE.exists():
            try:
                with open(RESULTS_FILE) as f:
                    existing = json.load(f)
            except json.JSONDecodeError:
                pass

        results = existing.get("results", [])
        new_failed = []
        results_lock = threading.Lock()

        arbiter_status["total"] = len(to_retry)
        arbiter_status["current_step"] = "retrying_failed"

        def process_one(img_path):
            if _stop_event.is_set():
                return None
            result = classify_single_image(str(img_path), cfg)
            if "error" in result:
                return {"image": img_path.name, "error": result["error"]}
            return {
                "image": img_path.name,
                "predictions": {cat: result["predictions"][cat]["final"] for cat in CATEGORIES},
                "agreement_count": result["agreement_count"],
                "arbiter_calls": result["arbiter_calls"],
                "details": result["predictions"],
            }

        succeeded_count = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_one, p): p for p in to_retry}

            for future in as_completed(futures):
                if _stop_event.is_set():
                    break

                result = future.result()
                if result is None:
                    continue

                with results_lock:
                    if "error" in result:
                        arbiter_status["errors"].append(f"{result['image']}: {result['error']}")
                        new_failed.append({
                            "image": result["image"],
                            "error": result["error"],
                            "failed_at": datetime.now().isoformat(),
                            "retry_count": _get_retry_count([], result["image"]) + 1,
                        })
                    else:
                        results.append(result)
                        succeeded_count += 1
                        arbiter_status["agreements"] += result.get("agreement_count", 0)
                        arbiter_status["arbiter_calls"] += result.get("arbiter_calls", 0)

                    arbiter_status["processed"] = succeeded_count + len(new_failed)
                    arbiter_status["failed_count"] = len(new_failed)
                    arbiter_status["current_image"] = result.get("image", "")

        # Save results and errors
        _save_results_and_errors(results, new_failed, cfg)

        # Save successful retries to database
        if succeeded_count > 0:
            _save_predictions_to_db(results[-succeeded_count:])

        arbiter_status["is_running"] = False
        arbiter_status["failed_count"] = len(new_failed)
        if _stop_event.is_set():
            arbiter_status["current_step"] = "stopped"
        else:
            arbiter_status["current_step"] = "completed"
        arbiter_status["completed_at"] = datetime.now().isoformat()
        print(f"[ARBITER RETRY] {succeeded_count} succeeded, {len(new_failed)} still failing.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        arbiter_status["is_running"] = False
        arbiter_status["current_step"] = "failed"
        arbiter_status["completed_at"] = datetime.now().isoformat()
        arbiter_status["errors"].append(f"Retry exception: {str(e)}")


# ─── Prediction Tracking ─────────────────────────────────────

@router.get("/prediction-tracking")
def get_prediction_tracking(
    page: int = 1,
    page_size: int = 20,
    filter_status: Optional[str] = None,  # "matched" | "mismatched" | "pending" | "corrected"
    category: Optional[str] = None,  # filter by arbiter category key
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Comparison table: AI predictions vs. annotator-approved labels.
    Each row = one image with per-category comparison.
    """
    # Get all images that have arbiter labels
    query = db.query(ImageModel).filter(ImageModel.arbiter_labels.isnot(None))

    if search:
        query = query.filter(ImageModel.filename.ilike(f"%{search}%"))

    images = query.order_by(ImageModel.id).all()

    if not images:
        return {
            "rows": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "summary": {
                "total_predicted": 0,
                "total_annotated": 0,
                "total_matched": 0,
                "total_mismatched": 0,
                "total_pending": 0,
                "match_rate": 0,
                "per_category": {},
            },
        }

    # Load categories with options
    categories = db.query(Category).options(joinedload(Category.options)).order_by(Category.display_order).all()
    cat_by_name = {c.name: c for c in categories}

    # Option ID → label lookup
    option_label_by_id = {}
    for c in categories:
        for o in c.options:
            option_label_by_id[o.id] = o.label

    # Get all completed human-validated annotations for these images
    image_ids = [img.id for img in images]
    annotations = (
        db.query(Annotation)
        .filter(
            Annotation.image_id.in_(image_ids),
            Annotation.status == "completed",
            Annotation.human_validated == True,
        )
        .options(joinedload(Annotation.selections), joinedload(Annotation.annotator))
        .all()
    )

    # Index: {image_id: {category_id: annotation}}
    ann_by_image_cat = {}
    for ann in annotations:
        ann_by_image_cat.setdefault(ann.image_id, {})[ann.category_id] = ann

    # Summary counters
    total_matched = 0
    total_mismatched = 0
    total_pending = 0
    per_category_stats = {cat: {"matched": 0, "mismatched": 0, "pending": 0} for cat in CATEGORIES}

    rows = []
    for img in images:
        arbiter_labels = img.arbiter_labels or {}
        img_annotations = ann_by_image_cat.get(img.id, {})

        category_comparisons = []
        img_matched = 0
        img_mismatched = 0
        img_pending = 0

        for arb_cat_key in CATEGORIES:
            db_cat_name = ARBITER_CAT_TO_DB_CAT.get(arb_cat_key)
            db_cat = cat_by_name.get(db_cat_name)
            if not db_cat:
                continue

            ai_pred_raw = arbiter_labels.get(arb_cat_key)
            # Predictions are stored as dicts: {"final": "well_lit", "status": "agree", ...}
            if isinstance(ai_pred_raw, dict):
                ai_pred_short = ai_pred_raw.get("final", "None")
            else:
                ai_pred_short = str(ai_pred_raw) if ai_pred_raw else None
            ai_pred_label = ARBITER_TO_OPTION_LABEL.get(ai_pred_short, ai_pred_short) if ai_pred_short else None

            # Get human annotation
            ann = img_annotations.get(db_cat.id)
            human_label = None
            annotator_name = None
            annotation_status = "pending"

            if ann:
                sel_ids = [s.option_id for s in ann.selections]
                if sel_ids:
                    human_label = option_label_by_id.get(sel_ids[0])
                annotator_name = ann.annotator.username if ann.annotator else None

                if human_label and ai_pred_label:
                    if human_label == ai_pred_label:
                        annotation_status = "matched"
                        img_matched += 1
                        total_matched += 1
                        per_category_stats[arb_cat_key]["matched"] += 1
                    else:
                        annotation_status = "mismatched"
                        img_mismatched += 1
                        total_mismatched += 1
                        per_category_stats[arb_cat_key]["mismatched"] += 1
                elif human_label:
                    annotation_status = "mismatched"
                    img_mismatched += 1
                    total_mismatched += 1
                    per_category_stats[arb_cat_key]["mismatched"] += 1
                else:
                    annotation_status = "pending"
                    img_pending += 1
                    total_pending += 1
                    per_category_stats[arb_cat_key]["pending"] += 1
            else:
                annotation_status = "pending"
                img_pending += 1
                total_pending += 1
                per_category_stats[arb_cat_key]["pending"] += 1

            category_comparisons.append({
                "category_key": arb_cat_key,
                "category_name": db_cat_name,
                "ai_prediction": ai_pred_label,
                "ai_prediction_short": ai_pred_short,
                "human_label": human_label,
                "annotator": annotator_name,
                "status": annotation_status,
            })

        # Overall image status
        if img_matched + img_mismatched == 0:
            overall = "pending"
        elif img_mismatched == 0:
            overall = "matched"
        else:
            overall = "corrected"

        row = {
            "image_id": img.id,
            "image_drive_id": img.image_drive_id,
            "filename": img.filename,
            "classified_at": img.arbiter_classified_at.isoformat() if img.arbiter_classified_at else None,
            "categories": category_comparisons,
            "matched_count": img_matched,
            "mismatched_count": img_mismatched,
            "pending_count": img_pending,
            "overall_status": overall,
        }

        # Apply filters
        if filter_status == "matched" and overall != "matched":
            continue
        if filter_status == "mismatched" and img_mismatched == 0:
            continue
        if filter_status == "corrected" and overall != "corrected":
            continue
        if filter_status == "pending" and overall != "pending":
            continue
        if category:
            cat_data = next((c for c in category_comparisons if c["category_key"] == category), None)
            if not cat_data:
                continue

        rows.append(row)

    # Paginate
    total = len(rows)
    start = (page - 1) * page_size
    paginated = rows[start:start + page_size]

    total_annotated = total_matched + total_mismatched

    return {
        "rows": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {
            "total_predicted": len(images),
            "total_annotated": total_annotated,
            "total_matched": total_matched,
            "total_mismatched": total_mismatched,
            "total_pending": total_pending,
            "match_rate": round(total_matched / total_annotated * 100, 1) if total_annotated > 0 else 0,
            "per_category": per_category_stats,
        },
    }
