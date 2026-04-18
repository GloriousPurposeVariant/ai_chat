# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "seed_data.json"
DATA = json.loads(DATA_PATH.read_text())
PRODUCTS = {p["product_id"]: p for p in DATA.get("products", [])}
INVENTORY = DATA.get("inventory", [])
VENDORS = DATA.get("vendors", [])
KB_DOCS = DATA.get("kb_docs", [])
CUSTOMERS = DATA.get("customers", [])

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1: hot_picks
# WHAT:  Returns products ranked by popularity that fit a budget and state.
# WHY:   Sales reps need quick recommendations. We filter BEFORE calling LLM
#        so we never dump the full product catalog into the prompt.
# WHEN:  Intent = SALES_RECO
# ─────────────────────────────────────────────────────────────────────────────

def hot_picks(state: str, budget: float, limit: int = 5) -> list[dict]:
    logger.info("hot_picks called state=%s budget=%s limit=%s", state, budget, limit)
    results = []
    missing_popularity = []

    for p in PRODUCTS.values():
        if len(results) >= limit:
            break
        if p["price"] <= budget and state not in p["blocked_states"]:
            if "popularity" not in p:
                missing_popularity.append(p.get("product_id", "unknown"))
            results.append(p)

    if missing_popularity:
        logger.warning(
            "hot_picks found products without popularity: %s",
            missing_popularity,
        )

    results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return [
        {
            "product_id": p["product_id"],
            "sku": p["sku"],
            "price": p["price"],
            "name": p["name"],
            "popularity_score": p["popularity_score"],
            "lab_report_required": p["lab_report_required"],
        }
        for p in results
    ]
    
def compliance_filter(state: str, product_ids: list) -> list:
    results = []
    for pid in product_ids:
        p = PRODUCTS.get(pid)
        if not p:
            results.append({
                "product_id": pid,
                "status": "NOT_FOUND",
                "reason_code": "PRODUCT_NOT_IN_CATALOG"
            })
            continue

        state_upper = state.upper()
        blocked_upper = [s.upper() for s in p["blocked_states"]]

        if state_upper in blocked_upper:
            status = "BLOCKED"
            reason_code = f"BLOCKED_IN_{state_upper}"
        elif p["lab_report_required"]:
            status = "REVIEW"
            reason_code = "LAB_REPORT_REQUIRED"
        else:
            status = "ALLOWED"
            reason_code = "CLEAR"

        results.append({
            "product_id": pid,
            "sku": p["sku"],
            "name": p["name"],
            "status": status,         # ALLOWED / BLOCKED / REVIEW
            "reason_code": reason_code,
            "price": p["price"],
        })
    return results

def stock_by_warehouse(product_id: int) -> dict:
    product = PRODUCTS.get(product_id)
    if not product:
        return {"error": f"Product {product_id} not found"}

    stock = [
        {"warehouse": item["warehouse"], "qty": item["qty"]}
        for item in INVENTORY
        if item["product_id"] == product_id
    ]

    total_qty = sum(s["qty"] for s in stock)

    return {
        "product_id": product_id,
        "sku": product["sku"],
        "name": product["name"],
        "warehouses": stock,
        "total_qty": total_qty,
    }
    
    REQUIRED_FIELDS = ["name", "category", "net_wt_oz", "net_vol_ml", "nicotine_mg"]

# Extra documents required per category
DOCS_BY_CATEGORY = {
    "THC Beverage": ["lab_report"],
    "Nicotine Vape": ["age_verification"],
    "Mushroom Gummies": ["lab_report"],
    "Kratom": ["lab_report"],
    "CBD Tincture": ["lab_report"],
}

def vendor_validate(attributes: dict) -> dict:
    # Check for missing required fields
    missing_fields = [
        f for f in REQUIRED_FIELDS
        if attributes.get(f) is None or attributes.get(f) == ""
    ]

    # Check for missing documents based on category
    category = attributes.get("category", "")
    required_docs = DOCS_BY_CATEGORY.get(category, [])
    missing_docs = [
        doc for doc in required_docs
        if not attributes.get(f"{doc}_attached", False)
    ]

    # Determine status
    if missing_fields:
        status = "FAIL"
    elif missing_docs:
        status = "REVIEW"
    else:
        status = "PASS"

    return {
        "status": status,           # PASS / REVIEW / FAIL
        "missing_fields": missing_fields,
        "required_documents": missing_docs,
        "checklist": {
            "fields_complete": len(missing_fields) == 0,
            "docs_complete": len(missing_docs) == 0,
        },
        "submitted_attributes": {
            k: v for k, v in attributes.items()
            if k not in ["email", "phone", "address"]  # PII redaction
        }
    }
    
def kb_search(query: str, top_k: int = 3) -> list:
    query_words = set(query.lower().split())
    scored = []

    for doc in KB_DOCS:
        doc_text = (doc["title"] + " " + doc["text"]).lower()
        doc_words = set(doc_text.split())
        # Score = number of overlapping words
        score = len(query_words & doc_words)
        if score > 0:
            scored.append((score, doc))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "snippet": doc["text"][:300],  # Never dump full text into LLM
        }
        for _, doc in scored[:top_k]
    ]





