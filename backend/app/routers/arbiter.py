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

from app.database import get_db, SessionLocal
from app.dependencies import require_admin
from app.models.user import User
from app.models.image import Image as ImageModel

router = APIRouter(prefix="/admin/arbiter", tags=["Arbiter Classifier"])

# ─── Directories ──────────────────────────────────────────────
ARBITER_DIR = Path(__file__).parent.parent.parent / "arbiter_classifier"
PIPELINE_WORKSPACE = Path(__file__).parent.parent.parent / "master_pipeline" / "pipeline_workspace"
FINAL_OUTPUT_DIR = PIPELINE_WORKSPACE / "04_final_output"
RESULTS_DIR = ARBITER_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = RESULTS_DIR / "final_images_results.json"
ERRORS_FILE = RESULTS_DIR / "failed_images.json"

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
def load_arbiter_config():
    config = {}
    config_file = ARBITER_DIR / "config" / "settings.env"
    if config_file.exists():
        with open(config_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
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
    except Exception as e:
        return {"error": str(e)}
    return {}


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
    except Exception as e:
        return {"error": str(e)}
    return {}


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
            "source": "04_final_output",
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
                "x-api-key": os.environ.get("TURING_API_KEY", config.get("TURING_API_KEY", "")),
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

        # Collect images
        supported_exts = {".jpg", ".jpeg", ".png"}
        image_files = sorted([
            p for p in FINAL_OUTPUT_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in supported_exts
        ])

        if not image_files:
            arbiter_status["is_running"] = False
            arbiter_status["current_step"] = "failed"
            arbiter_status["errors"].append("No images found in 04_final_output/")
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


# ─── Request / Response Models ────────────────────────────────
class ArbiterStartRequest(BaseModel):
    reset: bool = False   # If True, clear previous results and start fresh


# ─── API Endpoints ────────────────────────────────────────────

@router.get("/config")
def get_arbiter_config(admin: User = Depends(require_admin)):
    """Return current arbiter classifier configuration."""
    config = load_arbiter_config()
    # Count available images
    supported_exts = {".jpg", ".jpeg", ".png"}
    image_count = 0
    if FINAL_OUTPUT_DIR.exists():
        image_count = len([
            p for p in FINAL_OUTPUT_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in supported_exts
        ])

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
        "categories": CATEGORIES,
    }


@router.get("/status")
def get_arbiter_status(admin: User = Depends(require_admin)):
    """Get current arbiter pipeline execution status."""
    return arbiter_status


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

    if not FINAL_OUTPUT_DIR.exists():
        raise HTTPException(status_code=400, detail="No final output directory found. Run the master pipeline first.")

    if request.reset:
        if RESULTS_FILE.exists():
            RESULTS_FILE.unlink()
        if ERRORS_FILE.exists():
            ERRORS_FILE.unlink()

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

    return {"message": "Arbiter classifier started", "status": arbiter_status}


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

    # Load failed count from errors file
    failed_count = 0
    if ERRORS_FILE.exists():
        try:
            with open(ERRORS_FILE) as ef:
                failed_count = len(json.load(ef).get("failed", []))
        except (json.JSONDecodeError, OSError):
            pass

    summary = {
        "total_images": total_images,
        "total_agreements": total_agreements,
        "total_arbiter_calls": total_arbiter_calls,
        "total_categories": total_categories,
        "agreement_rate": round(total_agreements / total_categories * 100, 1) if total_categories > 0 else 0,
        "failed_count": failed_count,
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
    """Return the list of images that failed/errored during classification."""
    if not ERRORS_FILE.exists():
        return {"failed": [], "total": 0}

    try:
        with open(ERRORS_FILE) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"failed": [], "total": 0}

    failed = data.get("failed", [])
    return {
        "failed": failed,
        "total": len(failed),
        "last_updated": data.get("last_updated"),
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
                "x-api-key": os.environ.get("TURING_API_KEY", config.get("TURING_API_KEY", "")),
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
        to_retry = [
            p for p in FINAL_OUTPUT_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in supported_exts and p.name in failed_set
        ]

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
        arbiter_status["errors"].append(f"Exception: {str(e)}")
