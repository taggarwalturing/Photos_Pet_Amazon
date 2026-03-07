"""
Run Complete Arbiter Classification Pipeline
1. Gemini + OpenAI classify with reasoning
2. Arbiter resolves disagreements
3. Generate reports

Configuration: backend/.env (single source of truth)
"""

import os
import subprocess
import sys
from pathlib import Path

def load_config():
    """Load config from env vars (backend/.env) with fallback to local settings.env."""
    # Try loading backend/.env via dotenv
    backend_env = Path(__file__).parent.parent / ".env"
    if backend_env.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(backend_env, override=False)
        except ImportError:
            pass

    # Fallback: local settings.env
    file_config = {}
    config_file = Path(__file__).parent / "config" / "settings.env"
    if config_file.exists():
        with open(config_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    file_config[key.strip()] = value.strip()

    config = {}
    for key in file_config:
        config[key] = os.environ.get(key, file_config[key])
    # Also check env-only keys
    for key in ["GEMINI_MODEL", "OPENAI_MODEL", "ARBITER_MODEL",
                "GEMINI_PROMPT_VERSION", "OPENAI_PROMPT_VERSION", "ARBITER_PROMPT_VERSION",
                "ARBITER_PIPELINE_VERSION", "PIPELINE_VERSION", "RESULTS_DIR"]:
        env_val = os.environ.get(key)
        if env_val and key not in config:
            config[key] = env_val
    if "ARBITER_PIPELINE_VERSION" in config and "PIPELINE_VERSION" not in config:
        config["PIPELINE_VERSION"] = config["ARBITER_PIPELINE_VERSION"]
    return config

def main():
    CONFIG = load_config()
    
    GEMINI_MODEL = CONFIG.get("GEMINI_MODEL", "gemini-2.5-pro")
    GEMINI_PROMPT_VERSION = CONFIG.get("GEMINI_PROMPT_VERSION", "1")
    OPENAI_MODEL = CONFIG.get("OPENAI_MODEL", "gpt-4o")
    OPENAI_PROMPT_VERSION = CONFIG.get("OPENAI_PROMPT_VERSION", "1")
    ARBITER_MODEL = CONFIG.get("ARBITER_MODEL", "o3")
    ARBITER_PROMPT_VERSION = CONFIG.get("ARBITER_PROMPT_VERSION", "1")
    PIPELINE_VERSION = CONFIG.get("PIPELINE_VERSION", "1")
    RESULTS_DIR = CONFIG.get("RESULTS_DIR", "results")
    
    results_file = f"{RESULTS_DIR}/arbiter_v{PIPELINE_VERSION}_results.json"
    
    print("=" * 70)
    print("⚖️  RUNNING ARBITER CLASSIFICATION PIPELINE")
    print("=" * 70)
    print(f"  Model 1: {GEMINI_MODEL} (reasoning v{GEMINI_PROMPT_VERSION})")
    print(f"  Model 2: {OPENAI_MODEL} (reasoning v{OPENAI_PROMPT_VERSION})")
    print(f"  Arbiter: {ARBITER_MODEL} (v{ARBITER_PROMPT_VERSION})")
    print(f"  Pipeline Version: v{PIPELINE_VERSION}")
    print(f"  Output: {results_file}")
    print("=" * 70)
    print("\nStrategy:")
    print("  1. Gemini + OpenAI classify with reasoning (parallel)")
    print("  2. Agreement → Use shared prediction")
    print("  3. Disagreement → Arbiter decides based on reasoning")
    print("=" * 70)
    
    # Step 1: Batch Classification
    print("\n📌 STEP 1: Running classification with arbiter...")
    print("-" * 60)
    result = subprocess.run([sys.executable, "batch_arbiter.py"])
    
    if result.returncode != 0:
        print("❌ Classification failed!")
        return
    
    # Step 2: Generate Reports
    print("\n📌 STEP 2: Generating reports...")
    print("-" * 60)
    result = subprocess.run([sys.executable, "generate_report.py"])
    
    if result.returncode != 0:
        print("❌ Report generation failed!")
        return
    
    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETE!")
    print("=" * 70)
    print(f"\nConfiguration: backend/.env")
    print(f"\nPrompts:")
    print(f"  • prompts/gemini_reasoning_v{GEMINI_PROMPT_VERSION}.txt")
    print(f"  • prompts/openai_reasoning_v{OPENAI_PROMPT_VERSION}.txt")
    print(f"  • prompts/arbiter_v{ARBITER_PROMPT_VERSION}.txt")
    print(f"\nOutput files:")
    print(f"  • {results_file}")
    print(f"  • {RESULTS_DIR}/arbiter_v{PIPELINE_VERSION}_metrics.xlsx")

if __name__ == "__main__":
    main()
