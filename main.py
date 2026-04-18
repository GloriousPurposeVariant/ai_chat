# -*- coding: utf-8 -*-
import logging

import time
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.router import (
    classify_intent, extract_state, extract_budget,
    extract_product_ids, is_basket_followup, extract_basket_qty
)
from app.chains import chain_sales, chain_compliance, chain_vendor, chain_ops, chain_kb
from app.state import get_or_create_session, update_session, add_to_basket
from app.permissions import check_permission, validate_user_type
from app.observability import log_request
from app.tools import PRODUCTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


app = FastAPI(
    title="Reelo AI Chat Service",
    description="Odoo + AI orchestration layer for GW Products B2B marketplace",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str = Field(..., example="Hello, I want to onboard as a vendor")
    session_id: str | None = Field(None, example="test-123")
    user_type: str = Field(default="portal_customer", example="portal_vendor")
    # Options are "portal_customer", "portal_vendor", "internal_user"
    vendor_attributes: dict | None = Field(None, example={"company_name": "Acme Corp", "contact_email": "contact@acme.com"})
    
class ChatResponse(BaseModel):
    session_id: str
    intent: str
    response: str
    tools_called: list[str]
    latency_ms: int
    prompt_tokens_est: int


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "Reelo AI Chat",
        "status": "running",
    }

@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    request_id = str(uuid.uuid4())
    total_start = time.time()
    
    user_type = validate_user_type(payload.user_type)
    
    user_message = payload.message
    session_id = payload.session_id
    session_id, session_data = get_or_create_session(session_id)
    
    # ── Handle basket follow-up FIRST (before intent classification) ──
    # WHY: "add 2 of the first one to basket" has no clear intent keyword.
    # We detect it separately using prior session context.
    
    if is_basket_followup(payload.message):
        product_ids = session_data.get("last_product_ids", [])
        if not product_ids:
            return _build_response(
                session_id=session_id,
                intent="BASKET_FOLLOWUP",
                response="I don't have any products from our last conversation to add. Please search for products first.",
                tools_called=[],
                latency_ms=int((time.time() - total_start) * 1000),
                prompt_tokens_est=0,
            )

        qty = extract_basket_qty(payload.message)
        first_product_id = product_ids[0]
        basket_item = add_to_basket(session_data, first_product_id, qty)

        product = PRODUCTS.get(first_product_id, {})
        response_text = (
            f"Added {qty}x {product.get('name', f'Product {first_product_id}')} "
            f"(SKU: {product.get('sku', 'N/A')}) to your basket. "
            f"Your basket now has {len(session_data['basket'])} item(s)."
        )

        log_request(
            intent="BASKET_FOLLOWUP",
            user_type=user_type,
            tools_called=["session_state"],
            latency_ms=int((time.time() - total_start) * 1000),
            request_id=request_id,
            session_id=session_id,
        )

        return _build_response(
            session_id=session_id,
            intent="BASKET_FOLLOWUP",
            response=response_text,
            tools_called=["session_state"],
            latency_ms=int((time.time() - total_start) * 1000),
            prompt_tokens_est=0,
        )
    intent = classify_intent(user_message)  # Classify the intent of the user's message
    state  = extract_state(payload.message)  or session_data.get("last_state")  or "CA"
    budget = extract_budget(payload.message) or session_data.get("last_budget") or 9999.0
    product_ids = extract_product_ids(payload.message)
    
    chain_tools = {
        "SALES_RECO": ["hot_picks", "compliance_filter"],
        "COMPLIANCE_CHECK": ["compliance_filter"],
        "VENDOR_ONBOARDING": ["vendor_validate"],
        "OPS_STOCK": ["stock_by_warehouse"],
        "GENERAL_KB": ["kb_search"],
    }
    
    for tool_name in chain_tools.get(intent, []):
        allowed, reason = check_permission(user_type, tool_name)
        if not allowed:
            log_request(
                intent=intent,
                user_type=user_type,
                tools_called=[],
                latency_ms=int((time.time() - total_start) * 1000),
                request_id=request_id,
                session_id=session_id,
            )
            raise HTTPException(status_code=403, detail=f"Access denied: {reason}")
    
    # ── Execute the right chain ──
    result = {}

    if intent == "SALES_RECO":
        result = chain_sales(
            message=user_message,
            state=state,
            budget=budget,
            session=session_data,
            user_type=payload.user_type
        )
    elif intent == "COMPLIANCE_CHECK":
        # Need at least one product to check
        if not product_ids:
            # Try to use last known products from session
            product_ids = session_data.get("last_product_ids", [])

        if not product_ids:
            result = {
                "response": "Please specify a product SKU (e.g. SKU-1002) to check compliance.",
                "tools_called": [],
                "tool_details": [],
                "latency_ms": 0,
                "prompt_tokens_est": 0,
            }
        else:
            result = chain_compliance(
                message=payload.message,
                state=state,
                product_ids=product_ids,
                session=session_data,
                user_type=user_type,
            )
    elif intent == "VENDOR_ONBOARDING":
        # Use provided attributes or extract from message
        attributes = payload.vendor_attributes or _extract_vendor_attributes(payload.message)
        result = chain_vendor(
            message=payload.message,
            attributes=attributes,
            session=session_data,
            user_type=user_type,
        )
        
    elif intent == "OPS_STOCK":
        if not product_ids:
            product_ids = session_data.get("last_product_ids", [])

        if not product_ids:
            result = {
                "response": "Please specify a product SKU (e.g. SKU-1003) to check stock.",
                "tools_called": [],
                "tool_details": [],
                "latency_ms": 0,
                "prompt_tokens_est": 0,
            }
        else:
            result = chain_ops(
                message=payload.message,
                product_id=product_ids[0],
                session=session_data,
                user_type=user_type,
            )

    else:  # GENERAL_KB
        result = chain_kb(
            message=payload.message,
            session=session_data,
            user_type=user_type,
        )
    
    update_session(session_id, **session_data)
    
    total_latency = int((time.time() - total_start) * 1000)
    log_request(
        intent=intent,
        user_type=user_type,
        tools_called=result.get("tools_called", []),
        latency_ms=total_latency,
        tool_details=result.get("tool_details", []),
        prompt_tokens_est=result.get("prompt_tokens_est", 0),
        request_id=request_id,
        session_id=session_id,
    )

    # Simulate a response from the AI chat service
    return _build_response(
        session_id=session_id,
        intent=intent,
        response=result.get("response", "Sorry, I could not process that request."),
        tools_called=result.get("tools_called", []),
        latency_ms=total_latency,
        prompt_tokens_est=result.get("prompt_tokens_est", 0),
    )

@app.get("/basket/{session_id}")
def view_basket(session_id: str):
    """View current basket contents for a session."""
    from app.state import SESSIONS
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    basket = session.get("basket", [])
    enriched = []
    for item in basket:
        product = PRODUCTS.get(item["product_id"], {})
        enriched.append({
            "product_id": item["product_id"],
            "sku": product.get("sku"),
            "name": product.get("name"),
            "qty": item["qty"],
            "unit_price": product.get("price"),
            "line_total": round(product.get("price", 0) * item["qty"], 2),
        })

    return {
        "session_id": session_id,
        "items": enriched,
        "total": round(sum(i["line_total"] for i in enriched), 2),
    }
    

def _build_response(
    session_id: str,
    intent: str,
    response: str,
    tools_called: list,
    latency_ms: int,
    prompt_tokens_est: int,
) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        intent=intent,
        response=response,
        tools_called=tools_called,
        latency_ms=latency_ms,
        prompt_tokens_est=prompt_tokens_est,
    )
    
# ── Helper: extract vendor attributes from natural language ──────────────────
def _extract_vendor_attributes(message: str) -> dict:
    """
    Basic extraction of vendor attributes from natural language.
    In production: structured form submission, not NLP parsing.
    """
    msg_lower = message.lower()
    return {
        "name": "Submitted Product",
        "category": _detect_category(msg_lower),
        "net_wt_oz": None if "missing net wt" in msg_lower or "no net wt" in msg_lower else 10.0,
        "net_vol_ml": None if "missing net vol" in msg_lower else 30.0,
        "nicotine_mg": 0,
        "lab_report_attached": not ("no lab report" in msg_lower or "missing lab" in msg_lower),
        "age_verification_attached": "age" in msg_lower,
    }

def _detect_category(msg: str) -> str:
    """Detect product category from message text."""
    if "thc" in msg or "beverage" in msg:
        return "THC Beverage"
    if "nicotine" in msg or "vape" in msg:
        return "Nicotine Vape"
    if "mushroom" in msg or "gummies" in msg:
        return "Mushroom Gummies"
    if "kratom" in msg:
        return "Kratom"
    if "cbd" in msg:
        return "CBD Tincture"
    return "Accessories"
