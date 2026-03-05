"""
Generate Arbiter Metrics Report
- Individual model accuracy
- Arbiter decisions analysis
- Agreement statistics
"""

import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

# ============================================================================
# LOAD CONFIGURATION
# ============================================================================
def load_config():
    config = {}
    config_file = Path(__file__).parent / "config" / "settings.env"
    if config_file.exists():
        with open(config_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
    return config

CONFIG = load_config()
PIPELINE_VERSION = CONFIG.get("PIPELINE_VERSION", "1")
RESULTS_DIR = Path(CONFIG.get("RESULTS_DIR", "results"))
RESULTS_FILE = RESULTS_DIR / f"arbiter_v{PIPELINE_VERSION}_results.json"
OUTPUT_FILE = RESULTS_DIR / f"arbiter_v{PIPELINE_VERSION}_metrics.xlsx"

CATEGORIES = ["lighting", "viewpoint", "environment", "occlusion", "activity", "multipet"]

def load_results():
    with open(RESULTS_FILE) as f:
        return json.load(f)

def generate_report(data: dict):
    results = data.get("results", [])
    total = len(results)
    
    print("=" * 70)
    print("Generating Arbiter Metrics Report")
    print("=" * 70)
    print(f"Loaded {total} image results")
    
    # Summary with all models
    summary_data = []
    
    for cat in CATEGORIES:
        # Gemini accuracy
        gem_correct = sum(1 for r in results 
                        if r.get("details", {}).get(cat, {}).get("gemini") == r.get("ground_truth", {}).get(cat))
        
        # OpenAI accuracy
        oai_correct = sum(1 for r in results 
                        if r.get("details", {}).get(cat, {}).get("openai") == r.get("ground_truth", {}).get(cat))
        
        # Final (Arbiter) accuracy
        final_correct = sum(1 for r in results if cat in r.get("correct_categories", []))
        
        # Agreement count
        agree = sum(1 for r in results if r.get("details", {}).get(cat, {}).get("status") == "agree")
        
        # Arbiter decisions
        arbiter_used = sum(1 for r in results if r.get("details", {}).get(cat, {}).get("status") == "arbiter")
        
        # Arbiter accuracy (when arbiter was called)
        arbiter_correct = sum(1 for r in results 
                             if r.get("details", {}).get(cat, {}).get("status") == "arbiter"
                             and cat in r.get("correct_categories", []))
        
        summary_data.append({
            "Category": cat,
            "Total": total,
            "Gemini Correct": gem_correct,
            "Gemini Acc": f"{gem_correct/total*100:.1f}%",
            "OpenAI Correct": oai_correct,
            "OpenAI Acc": f"{oai_correct/total*100:.1f}%",
            "Agreement": agree,
            "Agreement %": f"{agree/total*100:.1f}%",
            "Arbiter Used": arbiter_used,
            "Arbiter Correct": arbiter_correct,
            "Arbiter Acc": f"{arbiter_correct/arbiter_used*100:.1f}%" if arbiter_used > 0 else "-",
            "Final Correct": final_correct,
            "Final Acc": f"{final_correct/total*100:.1f}%"
        })
    
    # Overall
    total_gem = sum(d["Gemini Correct"] for d in summary_data)
    total_oai = sum(d["OpenAI Correct"] for d in summary_data)
    total_final = sum(d["Final Correct"] for d in summary_data)
    total_agree = sum(d["Agreement"] for d in summary_data)
    total_arbiter_used = sum(d["Arbiter Used"] for d in summary_data)
    total_arbiter_correct = sum(d["Arbiter Correct"] for d in summary_data)
    total_cats = total * 6
    
    summary_data.append({
        "Category": "OVERALL",
        "Total": total_cats,
        "Gemini Correct": total_gem,
        "Gemini Acc": f"{total_gem/total_cats*100:.1f}%",
        "OpenAI Correct": total_oai,
        "OpenAI Acc": f"{total_oai/total_cats*100:.1f}%",
        "Agreement": total_agree,
        "Agreement %": f"{total_agree/total_cats*100:.1f}%",
        "Arbiter Used": total_arbiter_used,
        "Arbiter Correct": total_arbiter_correct,
        "Arbiter Acc": f"{total_arbiter_correct/total_arbiter_used*100:.1f}%" if total_arbiter_used > 0 else "-",
        "Final Correct": total_final,
        "Final Acc": f"{total_final/total_cats*100:.1f}%"
    })
    
    summary_df = pd.DataFrame(summary_data)
    
    # Arbiter decisions detail
    arbiter_data = []
    for r in results:
        for cat in CATEGORIES:
            detail = r.get("details", {}).get(cat, {})
            if detail.get("status") == "arbiter":
                arbiter_data.append({
                    "Image": r["image"],
                    "Category": cat,
                    "Ground Truth": r.get("ground_truth", {}).get(cat, "None"),
                    "Gemini": detail.get("gemini", "None"),
                    "Gemini Reason": detail.get("gemini_reason", "")[:100],
                    "OpenAI": detail.get("openai", "None"),
                    "OpenAI Reason": detail.get("openai_reason", "")[:100],
                    "Arbiter Winner": detail.get("arbiter_winner", "?"),
                    "Final": detail.get("final", "None"),
                    "Correct": cat in r.get("correct_categories", []),
                    "Confidence": detail.get("arbiter_confidence", "unknown")
                })
    
    arbiter_df = pd.DataFrame(arbiter_data)
    
    # All results
    all_data = []
    for r in results:
        row = {"Image": r["image"]}
        for cat in CATEGORIES:
            detail = r.get("details", {}).get(cat, {})
            row[f"{cat}_GT"] = r.get("ground_truth", {}).get(cat, "None")
            row[f"{cat}_Gemini"] = detail.get("gemini", "None")
            row[f"{cat}_OpenAI"] = detail.get("openai", "None")
            row[f"{cat}_Final"] = detail.get("final", "None")
            row[f"{cat}_Status"] = detail.get("status", "unknown")
            row[f"{cat}_Correct"] = "✓" if cat in r.get("correct_categories", []) else "✗"
        row["Agreement"] = f"{r.get('agreement_count', 0)}/6"
        row["Arbiter Calls"] = r.get("arbiter_calls", 0)
        all_data.append(row)
    
    all_df = pd.DataFrame(all_data)
    
    # Save
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        if not arbiter_df.empty:
            arbiter_df.to_excel(writer, sheet_name='Arbiter Decisions', index=False)
        all_df.to_excel(writer, sheet_name='All Results', index=False)
    
    print(f"✓ Saved report: {OUTPUT_FILE}")
    
    # Print summary
    print("\n" + "=" * 90)
    print("SUMMARY - Individual Model vs Arbiter Final Accuracy")
    print("=" * 90)
    print(f"{'Category':<12} {'Gemini':<10} {'OpenAI':<10} {'Agree %':<10} {'Arbiter Acc':<12} {'Final':<10}")
    print("-" * 65)
    for row in summary_data:
        print(f"{row['Category']:<12} {row['Gemini Acc']:<10} {row['OpenAI Acc']:<10} {row['Agreement %']:<10} {row['Arbiter Acc']:<12} {row['Final Acc']:<10}")

def main():
    data = load_results()
    generate_report(data)

if __name__ == "__main__":
    main()
