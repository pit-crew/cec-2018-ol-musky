import requests
import sys
from time import strftime
from time import sleep
import json

# local
uri = "http://localhost:8000/mcp"

# remote
uri = "http://7066414.pythonanywhere.com/mcp"

session = requests.Session()
session.auth = ('ryehigh', 'cec__2018')

n = 1
for i in range(20):
    url = f"{uri}/register_team?token=ronb&name=testteam{i}"

    response = session.get(url)
    if response.status_code != 200:
        print(f"BUMMER: code={response.status_code}")
        break;

    resp = response.json()
    team = resp["register_team"]
    token = team["token"]
    offset = i * 60 + 1
    print(f"python naive.py {token} {offset} &")
    if i % 3 == 0:
        print(f"sleep {n}")
        n += 1

