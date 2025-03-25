import json
import sys
import requests

# local
uri = "http://localhost:8000/mcp"

# remote
uri = "https://7066414.pythonanywhere.com/mcp"

session = requests.Session()
session.auth = ('ryehigh', '99PercentReady')

def send_request(action, parameters=""):
    url = f"{uri}/{action}?token={token}&{parameters}"
    response = session.get(url)
    if response.status_code != 200:
        print(f"BUMMER: code={response.status_code}")
        return {}
    try:
        resp = response.json()
    except Exception as e:
        print("Exception parsing response", response.content.decode("utf-8"))
        return {}
    return resp

token = "backhaus"
summaries = send_request("teams_summary")["teams_summary"]
action = "startup"
for summary in summaries:
    token = summary["token"]
    url = f"{uri}/{action}?token={token}"
    print(session.get(url))
