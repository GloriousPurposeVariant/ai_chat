import requests
import json
import time

BASE_URL = "http://localhost:8000"

def print_response(title, response):
    """Helper to format and print the API response data."""
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'-'*50}")
    
    if response.status_code != 200:
        print(f"ERROR: Received Status {response.status_code}")
        print(response.text)
        return None

    data = response.json()
    
    # Handling different structures for chat vs basket endpoints
    if "intent" in data:
        print(f"SESSION ID: {data.get('session_id', 'N/A')}")
        print(f"INTENT:     {data.get('intent')}")
        print(f"TOOLS:      {data.get('tools_called')}")
        print(f"LATENCY:    {data.get('latency_ms')} ms")
        print(f"\nRESPONSE:\n{data.get('response')}")
        return data.get('session_id')
    else:
        print("BASKET CONTENTS:")
        print(json.dumps(data, indent=2))
        return None

def main():
    session_id = None

    # --- Query 1: Sales — Hot picks ---
    payload1 = {
        "message": "Give me hot picks for CA under $5000",
        "user_type": "internal_sales"
    }
    resp1 = requests.post(f"{BASE_URL}/chat", json=payload1)
    session_id = print_response("QUERY 1: Sales — Hot picks for CA under $5000", resp1)

    # --- Query 2: Compliance — SKU-1002 ---
    payload2 = {
        "message": "Why is SKU-1002 not available in MA? Suggest alternatives.",
        "session_id": session_id,
        "user_type": "internal_sales"
    }
    resp2 = requests.post(f"{BASE_URL}/chat", json=payload2)
    print_response("QUERY 2: Compliance — Why is SKU-1002 blocked in MA?", resp2)

    # --- Query 3: Ops — Stock check ---
    payload3 = {
        "message": "How much stock does SKU-1003 have and where?",
        "session_id": session_id,
        "user_type": "internal_sales"
    }
    resp3 = requests.post(f"{BASE_URL}/chat", json=payload3)
    print_response("QUERY 3: Ops — How much stock does SKU-1003 have?", resp3)

    # --- Query 4: Vendor Onboarding ---
    payload4 = {
        "message": "I'm uploading a product missing Net Wt and no lab report — what do I fix?",
        "session_id": session_id,
        "user_type": "portal_vendor",
        "vendor_attributes": {
            "name": "Test THC Drink",
            "category": "THC Beverage",
            "net_wt_oz": None,
            "net_vol_ml": 30,
            "nicotine_mg": 0,
            "lab_report_attached": False
        }
    }
    resp4 = requests.post(f"{BASE_URL}/chat", json=payload4)
    print_response("QUERY 4: Vendor — Missing Net Wt and no lab report", resp4)

    # --- Query 5: Memory follow-up ---
    payload5 = {
        "message": "Ok add 2 of the first one to the basket",
        "session_id": session_id,
        "user_type": "internal_sales"
    }
    resp5 = requests.post(f"{BASE_URL}/chat", json=payload5)
    print_response("QUERY 5: Memory follow-up — Add 2 to basket", resp5)

    # --- View basket ---
    if session_id:
        resp6 = requests.get(f"{BASE_URL}/basket/{session_id}")
        print_response("FINAL BASKET STATE", resp6)

    print(f"\n{'='*50}")
    print(" ALL QUERIES COMPLETE")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()