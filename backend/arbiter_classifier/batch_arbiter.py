"""
Arbiter Classifier - Batch Processing
Strategy:
1. Gemini + OpenAI classify WITH reasoning (in parallel)
2. On disagreement → Arbiter model decides based on reasoning
3. Agreement → Use agreed prediction (no arbiter needed)
"""

import os
import json
import base64
import requests
import time
import pandas as pd
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from PIL import Image
import io

# ============================================================================
# LOAD CONFIGURATION
# ============================================================================
# Priority: Environment variables (from backend/.env) > settings.env file
# ============================================================================
def _read_env_file(filepath):
    """Parse a .env file directly from disk (no caching via os.environ)."""
    result = {}
    if Path(filepath).exists():
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
    return result


def load_config():
    """Load config fresh from .env files on disk (never stale os.environ).
    Priority: backend/.env (fresh read) > settings.env fallback > os.environ (last resort)
    """
    # 1. Fresh-read backend/.env from disk
    backend_env = Path(__file__).parent.parent / ".env"
    fresh_env = _read_env_file(backend_env)

    # 2. Fallback: local settings.env
    file_config = _read_env_file(Path(__file__).parent / "config" / "settings.env")

    # 3. Merge: fresh .env > settings.env > os.environ (last resort)
    all_keys = set(file_config.keys()) | set(fresh_env.keys()) | {
        "TURING_API_URL", "TURING_API_KEY", "TURING_GW_KEY", "TURING_AUTH",
        "GEMINI_MODEL", "GEMINI_PROVIDER", "GEMINI_PROMPT_VERSION",
        "OPENAI_MODEL", "OPENAI_PROVIDER", "OPENAI_PROMPT_VERSION",
        "ARBITER_MODEL", "ARBITER_PROVIDER", "ARBITER_PROMPT_VERSION",
        "ARBITER_BATCH_SIZE", "ARBITER_TIMEOUT_SECONDS",
        "ARBITER_PARALLEL_WORKERS", "ARBITER_PIPELINE_VERSION",
        "BATCH_SIZE", "TIMEOUT_SECONDS", "PARALLEL_WORKERS",
        "PIPELINE_VERSION", "TEMPERATURE", "RESULTS_DIR",
    }
    config = {}
    for key in all_keys:
        if key in fresh_env:
            config[key] = fresh_env[key]
        elif key in file_config:
            config[key] = file_config[key]
        elif os.environ.get(key):
            config[key] = os.environ[key]

    # Map ARBITER_ prefixed keys to legacy keys
    if "ARBITER_BATCH_SIZE" in config and "BATCH_SIZE" not in config:
        config["BATCH_SIZE"] = config["ARBITER_BATCH_SIZE"]
    if "ARBITER_TIMEOUT_SECONDS" in config and "TIMEOUT_SECONDS" not in config:
        config["TIMEOUT_SECONDS"] = config["ARBITER_TIMEOUT_SECONDS"]
    if "ARBITER_PARALLEL_WORKERS" in config and "PARALLEL_WORKERS" not in config:
        config["PARALLEL_WORKERS"] = config["ARBITER_PARALLEL_WORKERS"]
    if "ARBITER_PIPELINE_VERSION" in config and "PIPELINE_VERSION" not in config:
        config["PIPELINE_VERSION"] = config["ARBITER_PIPELINE_VERSION"]

    return config

CONFIG = load_config()

# ============================================================================
# CONFIGURATION
# ============================================================================
TURING_API_URL = CONFIG.get("TURING_API_URL", "https://kong.turing.com/api/v2/chat")
TURING_API_KEY = CONFIG.get("TURING_API_KEY", "YOUR_API_KEY")
TURING_GW_KEY = CONFIG.get("TURING_GW_KEY")
TURING_AUTH = CONFIG.get("TURING_AUTH")

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": TURING_API_KEY,
    "x-api-gw-key": TURING_GW_KEY,
    "Authorization": TURING_AUTH
}

# Models
GEMINI_MODEL = CONFIG.get("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_PROVIDER = CONFIG.get("GEMINI_PROVIDER", "google")
GEMINI_PROMPT_VERSION = CONFIG.get("GEMINI_PROMPT_VERSION", "1")

OPENAI_MODEL = CONFIG.get("OPENAI_MODEL", "gpt-4o")
OPENAI_PROVIDER = CONFIG.get("OPENAI_PROVIDER", "openai")
OPENAI_PROMPT_VERSION = CONFIG.get("OPENAI_PROMPT_VERSION", "1")

ARBITER_MODEL = CONFIG.get("ARBITER_MODEL", "o3")
ARBITER_PROVIDER = CONFIG.get("ARBITER_PROVIDER", "openai")
ARBITER_PROMPT_VERSION = CONFIG.get("ARBITER_PROMPT_VERSION", "1")

# Processing
PARALLEL_WORKERS = int(CONFIG.get("PARALLEL_WORKERS", "5"))
BATCH_SIZE = int(CONFIG.get("BATCH_SIZE", "50"))
TIMEOUT_SECONDS = int(CONFIG.get("TIMEOUT_SECONDS", "120"))
TEMPERATURE = float(CONFIG.get("TEMPERATURE", "0"))

# Output
PIPELINE_VERSION = CONFIG.get("PIPELINE_VERSION", "1")
RESULTS_DIR = Path(CONFIG.get("RESULTS_DIR", "results"))
RESULTS_DIR.mkdir(exist_ok=True)
RESULTS_FILE = RESULTS_DIR / f"arbiter_v{PIPELINE_VERSION}_results.json"

# Data
DATA_DIR = Path("../Model Eval Samples")
EXCEL_FILE = Path("../Model Eval Samples - All Categories_2.xlsx")

CATEGORIES = ["lighting", "viewpoint", "environment", "occlusion", "activity", "multipet"]

# ============================================================================
# LOAD PROMPTS
# ============================================================================
def load_prompt(name: str, version: str) -> str:
    prompt_file = Path(__file__).parent / "prompts" / f"{name}_v{version}.txt"
    if prompt_file.exists():
        content = prompt_file.read_text()
        lines = [l for l in content.split("\n") if not l.startswith("#")]
        return "\n".join(lines).strip()
    raise FileNotFoundError(f"Prompt not found: {prompt_file}")

GEMINI_PROMPT = load_prompt("gemini_reasoning", GEMINI_PROMPT_VERSION)
OPENAI_PROMPT = load_prompt("openai_reasoning", OPENAI_PROMPT_VERSION)
ARBITER_PROMPT = load_prompt("arbiter", ARBITER_PROMPT_VERSION)

# ============================================================================
# IMAGE ENCODING
# ============================================================================
def encode_image(image_path: str, max_size_mb: float = 4.0) -> tuple:
    with open(image_path, "rb") as f:
        data = f.read()
    
    size_mb = len(data) / (1024 * 1024)
    suffix = Path(image_path).suffix.lower()
    
    if size_mb > max_size_mb:
        img = Image.open(image_path)
        ratio = (max_size_mb / size_mb) ** 0.5
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG" if suffix == ".png" else "JPEG", quality=85)
        data = buffer.getvalue()
    
    media_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
    return base64.b64encode(data).decode("utf-8"), media_map.get(suffix, 'image/jpeg')

# ============================================================================
# API CALLS
# ============================================================================
def call_vision_api(model: str, provider: str, prompt: str, image_b64: str, mime: str) -> dict:
    """Call API with image"""
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
        "temperature": TEMPERATURE,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(TURING_API_URL, headers=HEADERS, json=payload, timeout=TIMEOUT_SECONDS)
        if response.status_code in [200, 201]:
            text = response.json()["choices"][0]["message"]["content"]
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        else:
            error_body = response.text[:300]
            return {"error": f"API returned {response.status_code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}


def call_text_api(model: str, provider: str, prompt: str) -> dict:
    """Call API without image (for arbiter)"""
    payload = {
        "model": model,
        "provider": provider,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(TURING_API_URL, headers=HEADERS, json=payload, timeout=TIMEOUT_SECONDS)
        if response.status_code in [200, 201]:
            text = response.json()["choices"][0]["message"]["content"]
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        else:
            error_body = response.text[:300]
            return {"error": f"API returned {response.status_code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}

# ============================================================================
# CLASSIFICATION WITH REASONING
# ============================================================================
def classify_with_reasoning(image_path: str) -> dict:
    """Run Gemini and OpenAI in parallel, get predictions with reasoning"""
    try:
        image_b64, mime = encode_image(image_path)
    except Exception as e:
        return {"error": str(e)}
    
    # Run both models in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        gemini_future = executor.submit(call_vision_api, GEMINI_MODEL, GEMINI_PROVIDER, GEMINI_PROMPT, image_b64, mime)
        openai_future = executor.submit(call_vision_api, OPENAI_MODEL, OPENAI_PROVIDER, OPENAI_PROMPT, image_b64, mime)
        
        gemini_result = gemini_future.result()
        openai_result = openai_future.result()
    
    # Propagate errors from either model
    if "error" in gemini_result and "error" in openai_result:
        return {"error": f"Both models failed — Gemini: {gemini_result['error'][:200]} | OpenAI: {openai_result['error'][:200]}"}
    if "error" in gemini_result:
        return {"error": f"Gemini failed: {gemini_result['error'][:300]}"}
    if "error" in openai_result:
        return {"error": f"OpenAI failed: {openai_result['error'][:300]}"}

    return {"gemini": gemini_result, "openai": openai_result}

def extract_prediction(result: dict, category: str) -> tuple:
    """Extract prediction and reasoning from model result"""
    cat_data = result.get(category, {})
    if isinstance(cat_data, dict):
        return cat_data.get("prediction", "None"), cat_data.get("reasoning", "")
    return str(cat_data) if cat_data else "None", ""

# ============================================================================
# ARBITER LOGIC
# ============================================================================
def call_arbiter(disagreements: dict) -> dict:
    """Call arbiter to resolve disagreements"""
    if not disagreements:
        return {}
    
    # Build arbiter prompt
    arbiter_input = ARBITER_PROMPT + "\n\n## Disagreements to Resolve:\n\n"
    
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
    
    result = call_text_api(ARBITER_MODEL, ARBITER_PROVIDER, arbiter_input)
    return result

# ============================================================================
# MAIN CLASSIFICATION PIPELINE
# ============================================================================
def classify_image_with_arbiter(image_path: str, ground_truth: dict) -> dict:
    """Full classification: Gemini + OpenAI → Arbiter (if needed)"""
    
    # Step 1: Get predictions with reasoning from both models
    results = classify_with_reasoning(image_path)
    gemini = results.get("gemini", {})
    openai = results.get("openai", {})
    
    # Step 2: Compare predictions, collect disagreements
    predictions = {}
    disagreements = {}
    agreements = 0
    arbiter_calls = 0
    
    for cat in CATEGORIES:
        g_pred, g_reason = extract_prediction(gemini, cat)
        o_pred, o_reason = extract_prediction(openai, cat)
        
        if g_pred == o_pred:
            # Agreement - use shared prediction
            predictions[cat] = {
                "final": g_pred,
                "status": "agree",
                "gemini": g_pred,
                "openai": o_pred,
                "gemini_reason": g_reason,
                "openai_reason": o_reason
            }
            agreements += 1
        else:
            # Disagreement - will need arbiter
            disagreements[cat] = {
                "gemini_pred": g_pred,
                "gemini_reason": g_reason,
                "openai_pred": o_pred,
                "openai_reason": o_reason
            }
    
    # Step 3: Call arbiter for disagreements
    if disagreements:
        arbiter_calls = 1
        arbiter_result = call_arbiter(disagreements)
        
        for cat, data in disagreements.items():
            arbiter_decision = arbiter_result.get(cat, {})
            winner = arbiter_decision.get("winner", "A")  # Default to Gemini
            
            if winner == "B":
                final_pred = data["openai_pred"]
            else:
                final_pred = data["gemini_pred"]
            
            # Override with arbiter's explicit prediction if provided
            if "final_prediction" in arbiter_decision:
                final_pred = arbiter_decision["final_prediction"]
            
            predictions[cat] = {
                "final": final_pred,
                "status": "arbiter",
                "gemini": data["gemini_pred"],
                "openai": data["openai_pred"],
                "gemini_reason": data["gemini_reason"],
                "openai_reason": data["openai_reason"],
                "arbiter_winner": winner,
                "arbiter_confidence": arbiter_decision.get("confidence", "unknown"),
                "arbiter_rationale": arbiter_decision.get("rationale", "")
            }
    
    # Step 4: Calculate accuracy
    correct_cats = []
    for cat in CATEGORIES:
        final_pred = predictions.get(cat, {}).get("final", "None")
        gt = ground_truth.get(cat, "None")
        if final_pred == gt:
            correct_cats.append(cat)
    
    return {
        "predictions": predictions,
        "agreement_count": agreements,
        "arbiter_calls": arbiter_calls,
        "correct_categories": correct_cats,
        "gemini_raw": gemini,
        "openai_raw": openai
    }

# ============================================================================
# GROUND TRUTH
# ============================================================================
def load_ground_truth():
    EXCEL_TO_CATEGORY = {
        "Dusk-dawn lighting": ("lighting", "dusk_dawn"),
        "Harsh outdoor sunlight with shadows": ("lighting", "harsh_sunlight"),
        "Low light conditions": ("lighting", "low_light"),
        "Well-lit conditions (typical)": ("lighting", "well_lit"),
        "Front-facing at eye level (typical)": ("viewpoint", "front_eye_level"),
        "Ground-level view": ("viewpoint", "ground_level"),
        "No head showing": ("viewpoint", "no_head"),
        "Partial view (head only)": ("viewpoint", "head_only"),
        "Top-down view": ("viewpoint", "top_down"),
        "In car-carrier": ("environment", "car_carrier"),
        "Indoor setting (typical)": ("environment", "indoor"),
        "Outdoor dirt road": ("environment", "outdoor_dirt"),
        "Snow environment": ("environment", "snow"),
        "Vet clinic": ("environment", "vet_clinic"),
        "Yard with a complex background": ("environment", "yard_complex"),
        "Behind furniture (face only)": ("occlusion", "behind_furniture"),
        "Full-body, unobstructed (typical)": ("occlusion", "full_body"),
        "Partially hidden under a blanket": ("occlusion", "under_blanket"),
        "Peeking out of box-carrier": ("occlusion", "peeking_box"),
        "Toy obscuring part of body": ("occlusion", "toy_obscuring"),
        "Eating-drinking": ("activity", "eating_drinking"),
        "Jumping to catch toy": ("activity", "jumping"),
        "Playing with another pet": ("activity", "playing"),
        "Running with motion blur": ("activity", "running"),
        "Sitting still-posed (typical)": ("activity", "sitting_posed"),
        "Sleeping-curled up": ("activity", "sleeping"),
        "Pet with breed lookalike": ("multipet", "pet_with_lookalike"),
        "Single pet (typical)": ("multipet", "single_pet"),
        "Three same-breed pets": ("multipet", "three_same"),
        "Two similar-looking pets together": ("multipet", "two_similar"),
    }
    
    df = pd.read_excel(EXCEL_FILE, header=None)
    headers = df.iloc[1, 1:31].tolist()
    
    ground_truth = {}
    for idx in range(2, len(df)):
        row = df.iloc[idx]
        image_name = str(row[0]).strip()
        if not image_name or image_name == 'nan':
            continue
        
        gt = {cat: "None" for cat in CATEGORIES}
        
        for col_idx, header in enumerate(headers):
            if pd.notna(header) and header in EXCEL_TO_CATEGORY:
                cell_value = row[col_idx + 1]
                if cell_value == True or cell_value == "True" or cell_value == 1:
                    category, label = EXCEL_TO_CATEGORY[header]
                    gt[category] = label
        
        ground_truth[image_name] = gt
    
    return ground_truth

def find_image_path(image_name: str) -> Path:
    for p in DATA_DIR.glob(f"**/{image_name}"):
        return p
    return None

def save_results(data: dict):
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 70)
    print("⚖️  ARBITER CLASSIFIER")
    print("=" * 70)
    print(f"  Gemini: {GEMINI_MODEL} (prompt v{GEMINI_PROMPT_VERSION})")
    print(f"  OpenAI: {OPENAI_MODEL} (prompt v{OPENAI_PROMPT_VERSION})")
    print(f"  Arbiter: {ARBITER_MODEL} (prompt v{ARBITER_PROMPT_VERSION})")
    print(f"  Pipeline Version: v{PIPELINE_VERSION}")
    print(f"  Parallel Workers: {PARALLEL_WORKERS}")
    print(f"  Output: {RESULTS_FILE}")
    print("=" * 70)
    
    if TURING_API_KEY == "YOUR_API_KEY":
        print("\n❌ Error: Set TURING_API_KEY")
        return
    
    print("\nLoading ground truth...")
    ground_truth = load_ground_truth()
    print(f"Loaded {len(ground_truth)} images")
    
    # Load existing
    existing = {"results": [], "metadata": {}}
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            existing = json.load(f)
    
    processed = {r["image"] for r in existing.get("results", [])}
    
    to_process = []
    for img_name, gt in ground_truth.items():
        if img_name not in processed:
            path = find_image_path(img_name)
            if path:
                to_process.append({"image": img_name, "path": str(path), "ground_truth": gt})
    
    print(f"Already processed: {len(processed)}")
    print(f"Remaining: {len(to_process)}")
    
    if not to_process:
        print("\n✓ All images processed!")
        return
    
    results = existing.get("results", [])
    results_lock = threading.Lock()
    total_arbiter_calls = 0
    
    def process_image(img):
        nonlocal total_arbiter_calls
        result = classify_image_with_arbiter(img["path"], img["ground_truth"])
        
        return {
            "image": img["image"],
            "ground_truth": img["ground_truth"],
            "predictions": {cat: result["predictions"][cat]["final"] for cat in CATEGORIES},
            "agreement_count": result["agreement_count"],
            "arbiter_calls": result["arbiter_calls"],
            "correct_categories": result["correct_categories"],
            "details": result["predictions"],
            "gemini_raw": result["gemini_raw"],
            "openai_raw": result["openai_raw"]
        }
    
    pbar = tqdm(total=len(to_process), desc="Processing", unit="img",
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]')
    
    processed_count = 0
    
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {executor.submit(process_image, img): img for img in to_process}
        
        for future in as_completed(futures):
            result = future.result()
            
            with results_lock:
                results.append(result)
                total_arbiter_calls += result.get("arbiter_calls", 0)
            
            processed_count += 1
            pbar.update(1)
            
            if processed_count % BATCH_SIZE == 0 or processed_count == len(to_process):
                with results_lock:
                    save_data = {
                        "results": results,
                        "metadata": {
                            "gemini_model": GEMINI_MODEL,
                            "openai_model": OPENAI_MODEL,
                            "arbiter_model": ARBITER_MODEL,
                            "pipeline_version": PIPELINE_VERSION,
                            "total_images": len(results),
                            "total_arbiter_calls": total_arbiter_calls,
                            "last_updated": datetime.now().isoformat()
                        }
                    }
                    save_results(save_data)
    
    pbar.close()
    
    # Summary
    print("\n" + "=" * 80)
    print("ARBITER CLASSIFIER RESULTS")
    print("=" * 80)
    
    total = len(results)
    total_agree = sum(r.get("agreement_count", 0) for r in results)
    total_arbiter = sum(r.get("arbiter_calls", 0) for r in results)
    
    print(f"\nAgreement: {total_agree}/{total*6} categories ({total_agree/(total*6)*100:.1f}%)")
    print(f"Arbiter calls: {total_arbiter} (for {total*6-total_agree} disagreements)")
    
    print(f"\n{'Category':<12} {'Gemini':<10} {'OpenAI':<10} {'Arbiter':<10} {'Accuracy':<10}")
    print("-" * 55)
    
    for cat in CATEGORIES:
        gem_correct = sum(1 for r in results 
                         if r.get("details", {}).get(cat, {}).get("gemini") == r.get("ground_truth", {}).get(cat))
        oai_correct = sum(1 for r in results 
                         if r.get("details", {}).get(cat, {}).get("openai") == r.get("ground_truth", {}).get(cat))
        final_correct = sum(1 for r in results if cat in r.get("correct_categories", []))
        
        print(f"{cat:<12} {gem_correct/total*100:>5.1f}%     {oai_correct/total*100:>5.1f}%     →        {final_correct/total*100:>5.1f}%")
    
    print(f"\nResults saved to: {RESULTS_FILE}")

if __name__ == "__main__":
    main()
