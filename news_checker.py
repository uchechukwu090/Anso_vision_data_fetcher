import os
import requests

API_KEY = os.getenv("FINLIGHT_API_KEY")

def check_news():
    if not API_KEY:
        return {"error": "Missing Finlight API key"}

    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get("https://api.finlight.ai/calendar/today", headers=headers)

    if response.status_code != 200:
        return {"error": "Failed to fetch news", "status": response.status_code}

    events = response.json().get("events", [])
    impactful = [e for e in events if e.get("impact") == "high"]
    return {"impactful_events": impactful}