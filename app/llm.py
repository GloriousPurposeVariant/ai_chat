# -*- coding: utf-8 -*-
import os
import json
from dotenv import load_dotenv
from app.observability import estimate_tokens

load_dotenv()  # Load environment variables from .env file


def get_llm():
    """
    Returns the LLM instance.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=gemini_api_key,
            temperature=0.3,
            max_tokens=500,
        )
    except ImportError:
        pass

def format_response(
    intent: str,
    tool_results: dict,
    original_message: str,
    user_type: str = "portal_customer",
) -> tuple[str, int]:
    """
    Ask LLM to explain tool results in natural language.
    Returns (response_text, estimated_prompt_tokens)

    CRITICAL RULES ENFORCED IN THE PROMPT:
    1. Only use facts from tool_results
    2. Never recommend BLOCKED products
    3. Explain reason codes in plain English
    4. Keep response concise
    """
    llm = get_llm()

    system_prompt = """You are a helpful B2B wholesale assistant for GW Products (Reelo platform).

STRICT RULES:
1. Only state facts that appear in the tool_results provided. Never invent facts.
2. Never recommend products with status "BLOCKED" or "NOT_FOUND".
3. If a product is BLOCKED, explain the reason_code in plain English.
4. If a product needs REVIEW, mention the lab_report requirement clearly.
5. Be concise and professional. Max 150 words."""

    user_prompt = f"""User asked: {original_message}

Tool results (these are the ONLY facts you may use):
{json.dumps(tool_results, indent=2)}

Provide a clear, helpful response based strictly on these tool results."""

    full_prompt = system_prompt + user_prompt
    prompt_tokens_est = estimate_tokens(full_prompt)

    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ])

    return response.content, prompt_tokens_est
