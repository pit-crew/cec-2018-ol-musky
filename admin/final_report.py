import json
import sys
import requests

from time import strftime

token = sys.argv[1]

uri = "http://localhost:8000/mcp"

session = requests.Session()

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
    report = "\t{:<8} {:<18} {:>10} {:>10} {:>10}\n".format('week', 'item', 'debit', 'credit', 'balance')
    bal = 0

    for i in range(len(ledger)):
        entry = ledger[i]
        wk = entry["week"]
        item = entry["item"]
        debit = float(entry["debit"])
        credit = float(entry["credit"])
        bal = bal - debit + credit
        report += "\t{:<8} {:<18} {:>10.2f} {:>10.2f} {:>10.2f}\n".format(wk, item, debit, credit, bal)
    return report


get_status(True)
