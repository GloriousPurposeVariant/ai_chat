# -*- coding: utf-8 -*-
import time
import json

from app.tools import (
    hot_picks, compliance_filter,
    stock_by_warehouse, vendor_validate, kb_search
)
from app.llm import format_response
from app.observability import make_tool_record
from app.permissions import check_permission, redact_list


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN A — Sales: Hot picks under budget
# Intent: SALES_RECO
# Flow: hot_picks → compliance_filter → LLM format
# ─────────────────────────────────────────────────────────────────────────────
def chain_sales(
    message: str,
    state: str,
    budget: float,
    session: dict,
    user_type: str,
) -> dict:
    tool_details = []
    total_start = time.time()

    # ── hot_picks ──
    t0 = time.time()
    picks = hot_picks(state=state, budget=budget, limit=5)
    tool_details.append(make_tool_record(
        tool_name="hot_picks",
        args={"state": state, "budget": budget, "limit": 5},
        latency_ms=int((time.time() - t0) * 1000),
        result_size=len(picks),
    ))

    pick_ids = [p["product_id"] for p in picks]

    # Compliance gating is MANDATORY — blocked items must never be recommended.
    t0 = time.time()
    compliance_results = compliance_filter(state=state, product_ids=pick_ids)
    tool_details.append(make_tool_record(
        tool_name="compliance_filter",
        args={"state": state, "product_ids": pick_ids},
        latency_ms=int((time.time() - t0) * 1000),
        result_size=len(compliance_results),
    ))

    # Separate allowed vs blocked for the LLM
    allowed = [r for r in compliance_results if r["status"] == "ALLOWED"]
    review  = [r for r in compliance_results if r["status"] == "REVIEW"]
    blocked = [r for r in compliance_results if r["status"] == "BLOCKED"]

    tool_results = {
        "state": state,
        "budget": budget,
        "allowed_products": allowed,
        "review_products": review,   # Lab report needed
        "blocked_products": blocked, # Do NOT recommend these
    }

    response_text, prompt_tokens = format_response(
        intent="SALES_RECO",
        tool_results=tool_results,
        original_message=message,
        user_type=user_type,
    )

    # ── Update session memory ──
    session.update({
        "last_intent": "SALES_RECO",
        "last_state": state,
        "last_budget": budget,
        "last_product_ids": pick_ids,
    })

    return {
        "response": response_text,
        "tools_called": ["hot_picks", "compliance_filter"],
        "tool_details": tool_details,
        "latency_ms": int((time.time() - total_start) * 1000),
        "prompt_tokens_est": prompt_tokens,
        "debug": {
            "picks_found": len(picks),
            "allowed": len(allowed),
            "blocked": len(blocked),
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN B — Compliance: Is it legal? Why blocked? Show alternatives.
# Intent: COMPLIANCE_CHECK
# Flow: compliance_filter → (if blocked) hot_picks for alternatives → LLM
# ─────────────────────────────────────────────────────────────────────────────
def chain_compliance(
    message: str,
    state: str,
    product_ids: list,
    session: dict,
    user_type: str,
) -> dict:
    tool_details = []
    total_start = time.time()

    t0 = time.time()
    results = compliance_filter(state=state, product_ids=product_ids)
    tool_details.append(make_tool_record(
        tool_name="compliance_filter",
        args={"state": state, "product_ids": product_ids},
        latency_ms=int((time.time() - t0) * 1000),
        result_size=len(results),
    ))

    blocked = [r for r in results if r["status"] == "BLOCKED"]
    allowed = [r for r in results if r["status"] == "ALLOWED"]

    # ── Find alternatives if products are blocked ──
    # WHY: "Why is SKU-1002 blocked?" deserves a follow-up:
    # "Here are products you CAN sell in MA instead."
    alternatives = []
    if blocked:
        t0 = time.time()
        alternatives = hot_picks(state=state, budget=9999, limit=3)
        # Filter to only ALLOWED alternatives
        alt_ids = [a["product_id"] for a in alternatives]
        alt_compliance = compliance_filter(state=state, product_ids=alt_ids)
        alternatives = [
            a for a, c in zip(alternatives, alt_compliance)
            if c["status"] == "ALLOWED"
        ]
        tool_details.append(make_tool_record(
            tool_name="hot_picks",
            args={"state": state, "budget": 9999, "limit": 3, "purpose": "alternatives"},
            latency_ms=int((time.time() - t0) * 1000),
            result_size=len(alternatives),
        ))

    tool_results = {
        "state": state,
        "compliance_check": results,
        "alternatives": alternatives,
    }

    response_text, prompt_tokens = format_response(
        intent="COMPLIANCE_CHECK",
        tool_results=tool_results,
        original_message=message,
        user_type=user_type,
    )

    session.update({
        "last_intent": "COMPLIANCE_CHECK",
        "last_state": state,
        "last_product_ids": product_ids,
    })

    return {
        "response": response_text,
        "tools_called": ["compliance_filter", "hot_picks"] if blocked else ["compliance_filter"],
        "tool_details": tool_details,
        "latency_ms": int((time.time() - total_start) * 1000),
        "prompt_tokens_est": prompt_tokens,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN C — Vendor Onboarding Validation
# Intent: VENDOR_ONBOARDING
# Flow: vendor_validate → LLM explains what to fix
# ─────────────────────────────────────────────────────────────────────────────
def chain_vendor(
    message: str,
    attributes: dict,
    session: dict,
    user_type: str,
) -> dict:
    tool_details = []
    total_start = time.time()

    # ── vendor_validate ──
    t0 = time.time()
    result = vendor_validate(attributes)
    tool_details.append(make_tool_record(
        tool_name="vendor_validate",
        args={"attributes": attributes},
        latency_ms=int((time.time() - t0) * 1000),
        result_size=len(result.get("missing_fields", [])),
    ))

    # ── Step 2: LLM explains in plain English ──
    tool_results = {"validation_result": result, "submitted": attributes}

    response_text, prompt_tokens = format_response(
        intent="VENDOR_ONBOARDING",
        tool_results=tool_results,
        original_message=message,
        user_type=user_type,
    )

    session.update({"last_intent": "VENDOR_ONBOARDING"})

    return {
        "response": response_text,
        "tools_called": ["vendor_validate"],
        "tool_details": tool_details,
        "latency_ms": int((time.time() - total_start) * 1000),
        "prompt_tokens_est": prompt_tokens,
        "validation": result,  # Return raw result too — useful for the demo
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN D — Ops Stock Check
# Intent: OPS_STOCK
# Flow: stock_by_warehouse → LLM formats
# ─────────────────────────────────────────────────────────────────────────────
def chain_ops(
    message: str,
    product_id: int,
    session: dict,
    user_type: str,
) -> dict:
    tool_details = []
    total_start = time.time()

    t0 = time.time()
    result = stock_by_warehouse(product_id)
    tool_details.append(make_tool_record(
        tool_name="stock_by_warehouse",
        args={"product_id": product_id},
        latency_ms=int((time.time() - t0) * 1000),
        result_size=len(result.get("warehouses", [])),
    ))

    response_text, prompt_tokens = format_response(
        intent="OPS_STOCK",
        tool_results={"stock": result},
        original_message=message,
        user_type=user_type,
    )

    session.update({
        "last_intent": "OPS_STOCK",
        "last_product_ids": [product_id],
    })

    return {
        "response":  response_text,
        "tools_called": ["stock_by_warehouse"],
        "tool_details": tool_details,
        "latency_ms": int((time.time() - total_start) * 1000),
        "prompt_tokens_est": prompt_tokens,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN E — General KB / Policy Questions
# Intent: GENERAL_KB
# Flow: kb_search → LLM explains
# ─────────────────────────────────────────────────────────────────────────────
def chain_kb(
    message: str,
    session: dict,
    user_type: str,
) -> dict:
    tool_details = []
    total_start = time.time()

    t0 = time.time()
    docs = kb_search(message, top_k=3)
    tool_details.append(make_tool_record(
        tool_name="kb_search",
        args={"query": message, "top_k": 3},
        latency_ms=int((time.time() - t0) * 1000),
        result_size=len(docs),
    ))

    response_text, prompt_tokens = format_response(
        intent="GENERAL_KB",
        tool_results={"documents": docs},
        original_message=message,
        user_type=user_type,
    )

    session.update({"last_intent": "GENERAL_KB"})

    return {
        "response": response_text,
        "tools_called": ["kb_search"],
        "tool_details": tool_details,
        "latency_ms": int((time.time() - total_start) * 1000),
        "prompt_tokens_est": prompt_tokens,
    }
