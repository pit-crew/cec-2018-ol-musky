import json
import sys
import requests

from time import strftime

token = sys.argv[1]

# local
uri = "http://localhost:8000/mcp"

# remote
uri = "https://7066414.pythonanywhere.com/mcp"

session = requests.Session()
session.auth = ('ryehigh', '99PercentReady')

fmt = "%Y-%m-%d %H:%M:%S    "


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
        return

    try:
        status = int(resp["status"])
        if status != 0:
            desc = resp["description"]
            print(f"code: {status}, description: {desc}")
            print()
            return resp
    except Exception as e:
        print(f"Exception: {e}")
    return resp


def get_status(wprint_ledger=False):
    report = send_request("final_report")
    try:
        team = report["final_report"]["team"]
        week = int(team["week"])
        if wprint_ledger:
            ledger = report["final_report"]["ledger"]
            print("---------------------------------------------------")
            print(fmt_ledger(week, ledger))
    except Exception as e:
        print(f"Exception: {e}")
    return report


def fmt_ledger(wk, ledger):
    if ledger == "":
        return ""
    report = "\t{:<8} {:<18} {:>8} {:>8} {:>8}\n".format('week', 'item', 'debit', 'credit', 'balance')
    bal = 0

    for i in range(len(ledger)):
        entry = ledger[i]
        wk = entry["week"]
        item = entry["item"]
        debit = int(entry["debit"])
        credit = int(entry["credit"])
        bal = bal - debit + credit
        report += "\t{:<8} {:<18} {:>8} {:>8} {:>8}\n".format(wk, item, debit, credit, bal)
    return report


get_status(True)
