import requests

def check_news():
    # Replace with Finlight or other provider
    response = requests.get("https://api.finlight.ai/calendar/today")
    events = response.json().get("events", [])
    impactful = [e for e in events if e["impact"] == "high"]
    return {"impactful_events": impactful}