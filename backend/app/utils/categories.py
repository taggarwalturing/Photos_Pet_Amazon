"""
Static category configuration loader.
Categories and options are defined in categories.json (no DB tables).
"""
import json
import os
from functools import lru_cache
from typing import Dict, List, Optional

_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "categories.json")


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    with open(_JSON_PATH, "r") as f:
        return json.load(f)


def get_categories() -> List[dict]:
    """Return list of category dicts (each with 'id', 'name', 'key', 'display_order', 'options')."""
    return _load_raw()["categories"]


def get_category_by_id(cat_id: int) -> Optional[dict]:
    for c in get_categories():
        if c["id"] == cat_id:
            return c
    return None


def get_category_by_key(key: str) -> Optional[dict]:
    for c in get_categories():
        if c["key"] == key:
            return c
    return None


def get_option_by_id(option_id: int) -> Optional[dict]:
    """Find a single option by its global ID."""
    for c in get_categories():
        for o in c["options"]:
            if o["id"] == option_id:
                return {**o, "category_id": c["id"], "category_name": c["name"]}
    return None


def get_option_by_key(cat_key: str, opt_key: str) -> Optional[dict]:
    """Find a single option by category key and option key."""
    cat = get_category_by_key(cat_key)
    if not cat:
        return None
    for o in cat["options"]:
        if o.get("key") == opt_key:
            return {**o, "category_id": cat["id"], "category_name": cat["name"]}
    return None


def get_options_for_category(cat_id: int) -> List[dict]:
    cat = get_category_by_id(cat_id)
    return cat["options"] if cat else []


def resolve_option_ids(option_ids: List[int]) -> List[dict]:
    """Given a list of option IDs, return list of {id, label, category_id, category_name}."""
    result = []
    for oid in option_ids:
        opt = get_option_by_id(oid)
        if opt:
            result.append(opt)
    return result


def option_label_to_id(category_id: int, label: str) -> Optional[int]:
    """Find option ID by category and label text."""
    for o in get_options_for_category(category_id):
        if o["label"] == label:
            return o["id"]
    return None


# ── Arbiter key mappings ──────────────────────────────────────────

def category_name_to_arbiter_key() -> Dict[str, str]:
    """Map DB category names to arbiter keys (e.g. 'Lighting Variation' -> 'lighting')."""
    return {c["name"]: c["key"] for c in get_categories()}


def arbiter_key_to_category_id() -> Dict[str, int]:
    """Map arbiter keys to category IDs (e.g. 'lighting' -> 1)."""
    return {c["key"]: c["id"] for c in get_categories()}


# ── Arbiter label ↔ option label mapping ──────────────────────────

# Arbiter returns snake_case labels; map them to the human-readable option labels
_ARBITER_LABEL_TO_OPTION = {
    # Lighting
    "dusk_dawn": "Dusk-dawn lighting",
    "harsh_sunlight": "Harsh outdoor sunlight with shadows",
    "low_light": "Low light conditions",
    "well_lit": "Well-lit conditions (typical)",
    # Viewpoint
    "front_eye_level": "Front-facing at eye level (typical)",
    "ground_level": "Ground-level view",
    "no_head": "No head showing",
    "partial_head_only": "Partial view (head only)",
    "top_down": "Top-down view",
    # Environment
    "car_carrier": "In car-carrier",
    "indoor": "Indoor setting (typical)",
    "outdoor_dirt": "Outdoor dirt road",
    "snow": "Snow environment",
    "vet_clinic": "Vet clinic",
    "yard_complex_bg": "Yard with a complex background",
    # Occlusion
    "behind_furniture": "Behind furniture (face only)",
    "full_body": "Full-body, unobstructed (typical)",
    "under_blanket": "Partially hidden under a blanket",
    "peeking_box": "Peeking out of box-carrier",
    "toy_obscuring": "Toy obscuring part of body",
    "partial_visible_body": "Partial Visible Body",
    # Activity
    "eating_drinking": "Eating-drinking",
    "jumping": "Jumping to catch toy",
    "playing_other_pet": "Playing with another pet",
    "running_blur": "Running with motion blur",
    "sitting_posed": "Sitting still-posed (typical)",
    "sleeping": "Sleeping-curled up",
    "standing_posed": "Standing still-posed",
    # Multi-pet
    "breed_lookalike": "Pet with breed lookalike",
    "single_pet": "Single pet (typical)",
    "three_same_breed": "Three pets of same breed",
    "two_similar": "Two similar-looking pets together",
    # Catch-all
    "none": "None of the Above",
    "none_of_the_above": "None of the Above",
}


def arbiter_label_to_option_label(arbiter_label: str) -> Optional[str]:
    return _ARBITER_LABEL_TO_OPTION.get(arbiter_label)


def enrich_arbiter_labels(arbiter_labels: dict) -> dict:
    """
    Take arbiter_labels like:
      {"lighting": "well_lit", ...}
    or:
      {"lighting": {"final": "well_lit", "status": "agree", ...}, ...}
    and add human-readable labels:
      {"lighting": {"key": "well_lit", "label": "Well-lit conditions (typical)"}, ...}
    or:
      {"lighting": {"final": "well_lit", "label": "Well-lit conditions (typical)", "status": "agree", ...}, ...}
    """
    if not arbiter_labels:
        return arbiter_labels
    enriched = {}
    for cat_key, pred_data in arbiter_labels.items():
        if isinstance(pred_data, dict):
            # Detailed format — add label based on "final" key
            final_key = pred_data.get("final", "")
            label = arbiter_label_to_option_label(final_key) or final_key
            enriched[cat_key] = {**pred_data, "label": label}
        elif isinstance(pred_data, str):
            # Simple format — wrap with key + label
            label = arbiter_label_to_option_label(pred_data) or pred_data
            enriched[cat_key] = {"key": pred_data, "label": label}
        else:
            enriched[cat_key] = pred_data
    return enriched


def enrich_annotations_with_labels(annotations: dict) -> dict:
    """
    Take an annotations dict like:
      {"lighting": {"selected_option_ids": [1]}, ...}
    and return:
      {"lighting": {"selected_option_ids": [1], "selected_labels": ["Dusk-dawn lighting"]}, ...}
    """
    if not annotations:
        return annotations
    enriched = {}
    for cat_key, cat_data in annotations.items():
        ids = cat_data.get("selected_option_ids", [])
        labels = []
        for oid in ids:
            opt = get_option_by_id(oid)
            if opt:
                labels.append(opt["label"])
        enriched[cat_key] = {
            "selected_option_ids": ids,
            "selected_labels": labels,
        }
    return enriched
