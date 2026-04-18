import requests

# If your Docker is mapped to 8000, use this. 
# If it's a different port, change it here.
URL = "http://localhost:8000/chat"

payload = {
    "message": "Hello, hot picks under $50 in California CA?",
    "session_id": "",
    "user_type": "portal_customer",
}

try:
    response = requests.post(URL, json=payload)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(response.json())
except Exception as e:
    print(f"Failed to connect to the server: {e}")