# -*- coding: utf-8 -*-

# ── Tool Allowlists per user_type ────────────────────────────────────────────
#   Allowlist = "these tools are permitted" (safe by default)
#   Denylist  = "these tools are forbidden" (unsafe by default — easy to miss new tools)
#   Always use allowlists for security.

TOOL_ALLOWLIST: dict[str, list[str]] = {
    "internal_sales": [
        "hot_picks",
        "compliance_filter",
        "stock_by_warehouse",
        "kb_search",
        "vendor_validate",   # Internal team can see vendor validation too
    ],
    "portal_vendor": [
        "vendor_validate",
        "kb_search",         # Vendors can read policies
    ],
    "portal_customer": [
        "hot_picks",
        "compliance_filter",
        "kb_search",
        # Cannot call: stock_by_warehouse, vendor_validate
    ],
}

VALID_USER_TYPES = set(TOOL_ALLOWLIST.keys())


def check_permission(user_type: str, tool_name: str) -> tuple[bool, str]:
    if user_type not in VALID_USER_TYPES:
        return False, f"Unknown user_type: {user_type}"

    allowed_tools = TOOL_ALLOWLIST.get(user_type, [])
    if tool_name not in allowed_tools:
        return False, f"{user_type} is not permitted to call {tool_name}"

    return True, "OK"


def validate_user_type(user_type: str) -> str:
    """Return user_type if valid, else default to portal_customer (safest)."""
    if user_type in VALID_USER_TYPES:
        return user_type
    return "portal_customer"


# ── PII Redaction ─────────────────────────────────────────────────────────────
# Fields that must never go into an LLM prompt
PII_FIELDS = {
    "email", "phone", "address", "ssn",
    "credit_card", "customer_name", "contact"
}

def redact_pii(data: dict) -> dict:
    """
    Remove PII fields before sending data to LLM.

    WHY: LLM providers (OpenAI, Anthropic) process data on their servers.
    Customer PII should never leave our system boundary via LLM prompts.

    IN PRODUCTION: This would be more sophisticated — regex patterns for
    email addresses, phone numbers, credit card numbers embedded in text.
    """
    if not isinstance(data, dict):
        return data

    return {
        k: "***REDACTED***" if k.lower() in PII_FIELDS else v
        for k, v in data.items()
    }


def redact_list(data: list) -> list:
    """Apply PII redaction to a list of dicts."""
    return [redact_pii(item) if isinstance(item, dict) else item for item in data]
