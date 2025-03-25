import requests
from time import strftime
from time import sleep

token = "9f35c9b734f9e17492c9e78f212e4641"
mysectors = "853"

week = 0
fmt = "%Y-%m-%d %H:%M:%S    "
logfile = open(token + ".log", "w")

uri="http://localhost:8000/mcp"
# remote host
#uri = "http://7066414.pythonanywhere.com/mcp"

session = requests.Session()
session.auth = ('ryehigh', '99PercentReady')

# API ========================================================================

def send_request(action, parameters=""):

    url = f"{uri}/{action}?token={token}&{parameters}"
    logfile.write(strftime(fmt) + " " + url)
    logfile.write("\n")

    response = session.get(url)
    if response.status_code != 200:
        print (f"BUMMER: code={response.status_code}")
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


def status_report(print_ledger=False):
    report = send_request("status_report")
    try:
        team = report["status_report"]["team"]
        week = int(team["week"])
        if print_ledger:
            ledger = report["status_report"]["ledger"]
            print("Ledger ---------------")
            print(fmt_ledger(ledger))
    except Exception as e:
        print(f"Exception: {e}")
    return report

def fmt_ledger(ledger):
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


def startup():
    result = send_request("startup")
    status = int(result["status"])
    return status, result

def parameters():
    result = send_request("parameters", "scenario_id=debug")
    status = int(result["status"])
    return status, result["parameters"]

def prospect_report():
    result = send_request("prospect_report")
    status = int(result["status"])
    return status, result

def market_report():
    result = send_request("market_report")
    status = int(result["status"])
    return status, result

def build_hubs(new_hub_ids):
    result = send_request("build_hubs", "hubs=" + new_hub_ids)
    status = int(result["status"])
    return status, result

def deploy_hubs(hub_ids, new_sector_ids):
    result = send_request("deploy_hubs", f"hubs={hub_ids}&sector_ids={new_sector_ids}")
    status = int(result["status"])
    return status, result

def move_hubs(hub_ids, new_sector_ids):
    result = send_request("move_hubs", f"hubs={hub_ids}&sector_ids={new_sector_ids}")
    status = int(result["status"])
    return status, result

def ship_ore(hub_ids,):
    result = send_request("ship_ore", f"hubs={hub_ids}")
    status = int(result["status"])
    return status, result

def wait_for_completion():
    while True:
        sleep(MS_PER_WEEK/1000)
        rpt = status_report()["status_report"]
        print("week", rpt["team"]["week"])
        pending = [int(order["complete"]) for order in rpt["orders"]]
        if len(pending) == 0:
            break;


def assertStatusEquals(test, expected, actual):
    if expected != actual:
        print(f"[FAILED] - test: expected {expected}, got {actual}")
        return False
    return True

#=============================================================================


# MAIN -----------------------------------------------------------------------------------------------------------------

print("--------------------------")

# sample code

# must startup for each run
status, resp = startup()
print("resp",resp)
print("status", status)

# get the system parameters
status, params = parameters()
print(params)
ROWS = int(params["rows"])
COLS = int(params["cols"])
MS_PER_WEEK = int(params["ms_per_week"])
LIFETIME = int(params["lifetime"])
HUB_CAPACITY = int(params["hub_capacity"])
COST = params["costs"]

myhubs = "hub-1"
print("build a hub -----------------------------")
status, resp = build_hubs(myhubs)
assertStatusEquals("build a hub", 0, status)

print("wait for delivery -----------------------")
wait_for_completion()

print("deploy the hub --------------------------")
status, resp = deploy_hubs(myhubs, mysectors)
assertStatusEquals("deploy a hub", 0, status)

print("wait for deployment ---------------------")
wait_for_completion()

status, rpt = prospect_report()
print(rpt)
sleep(70 * MS_PER_WEEK / 1000)
status, rpt = prospect_report()
print(rpt)

print("mine for 10 weeks -----------------------")
sleep(10 * MS_PER_WEEK / 1000)

print("ship_ore --------------------------------")
status, resp = ship_ore(myhubs)
print(resp)

print("move the hub ----------------------------")
new_sector = "863"
status, resp = move_hubs(myhubs, new_sector)
print("status", status)
print(status_report(True))

print("wait for re-location --------------------")
wait_for_completion()

print("mine for 10 weeks -----------------------")
sleep(10 * MS_PER_WEEK / 1000)

print("ship_ore --------------------------------")
status, resp = ship_ore(myhubs)

print("wait for revenue  -----------------------")
wait_for_completion()

print(status_report(True))

