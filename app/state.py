# -*- coding: utf-8 -*-
import uuid

SESSIONS: dict[str, dict] = {}  # session_id -> session_data

def get_or_create_session(session_id: str | None = None) -> tuple[str, dict]:
    if session_id and session_id in SESSIONS:
        return session_id, SESSIONS[session_id]

    new_id = str(uuid.uuid4())
    SESSIONS[new_id] = {
        "last_intent": None,
        "last_state": None,
        "last_budget": None,
        "last_product_ids": [],
        "basket": [],
        "turn_count": 0,
    }
    return new_id, SESSIONS[new_id]


def update_session(session_id: str, **kwargs) -> None:
    if session_id in SESSIONS:
        session = SESSIONS[session_id]
        session.update(kwargs)
        session["turn_count"] += 1
        
def add_to_basket(session: dict, product_id: int, qty: int) -> dict:
    # Check if product already in basket — update qty instead of duplicate
    for item in session["basket"]:
        if item["product_id"] == product_id:
            item["qty"] += qty
            return item

    # New item
    new_item = {"product_id": product_id, "qty": qty}
    session["basket"].append(new_item)
    return new_item


def get_basket_summary(session: dict) -> list:
    return session.get("basket", [])
        
    