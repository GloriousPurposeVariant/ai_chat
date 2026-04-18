# -*- coding: utf-8 -*-
import logging
import re

from app.llm import get_llm
from app.tools import PRODUCTS

INTENT_KEYWORDS = {
    "VENDOR_ONBOARDING": [
        "uploading", "vendor", "onboard", "lab report",
        "net wt", "missing field", "what do i fix", "upload",
        "catalog", "product submission"
    ],
    "COMPLIANCE_CHECK": [
        "legal", "blocked", "why not available", "not available",
        "restricted", "compliance", "why is sku", "allowed in",
        "can i sell", "is it legal", "why blocked"
    ],
    "OPS_STOCK": [
        "stock", "inventory", "how much", "warehouse",
        "qty", "quantity", "where is", "how many units",
        "available stock"
    ],
    "SALES_RECO": [
        "hot picks", "recommend", "best sellers",
        "under $", "budget", "suggest", "top products",
        "what should i sell", "popular"
    ],
    "GENERAL_KB": [
        "policy", "returns", "shipping", "how do i",
        "what is", "explain", "sop", "guide", "procedure"
    ],
}

def classify_intent(message: str) -> str:
    """
    Classify the intent of the user's message.
    This is a placeholder function. In a real implementation, this would use an NLP model.
    """
    message = message.lower()
    
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in message for kw in keywords):
            return intent

    return _llm_classify_intent(message)
    logging.info(f"LLM intent classification result: {result}")

def _llm_classify_intent(message: str) -> str:
    llm = get_llm()
    prompt = f"""Classify the intent of the following message into one of these categories:
     {', '.join(INTENT_KEYWORDS.keys())}. Message: '{message}'
     Return only the intent category as a string, NOTHING ELSE. If it doesn't fit any category, return 'GENERAL_KB'."""
    result = llm.invoke(prompt)
    logging.info(f"LLM intent classification result: {result}")
    return result


US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
]

def extract_state(message: str) -> str | None:
    msg_upper = message.upper()
    for state in US_STATES:
        # Match state as a word boundary to avoid false matches
        if re.search(r'\b' + state + r'\b', msg_upper):
            return state
    return None


def extract_budget(message: str) -> float | None:
    # Match $5000, $5,000, 5000, "under 5000"
    match = re.search(r'\$\s?(\d[\d,]*(?:\.\d+)?)', message)
    if match:
        return float(match.group(1).replace(',', ''))

    match = re.search(r'under\s+(\d[\d,]*)', message.lower())
    if match:
        return float(match.group(1).replace(',', ''))

    return None

def extract_product_ids(message: str) -> list[int]:
    # Match SKU-1001, sku-1001, etc.
    skus = re.findall(r'SKU-(\d+)', message.upper())
    product_ids = [int(s) for s in skus]

    # Also try matching product names from the catalog
    if not product_ids:
        msg_lower = message.lower()
        for pid, product in PRODUCTS.items():
            if product["name"].lower() in msg_lower:
                product_ids.append(pid)

    return product_ids

def is_basket_followup(message: str) -> bool:
    msg = message.lower()
    return (
        "add" in msg and
        any(word in msg for word in ["first", "1st", "that one", "it", "one"])
    )


def extract_basket_qty(message: str) -> int:
    match = re.search(r'\b(\d+)\b', message)
    return int(match.group(1)) if match else 1