import json
import random
import sys
from time import sleep
from time import strftime

import requests

token = sys.argv[1]
week = 0


def wprint(msg):
    print(f"[{week}] {msg}")


wprint(f"bootstrapping team {token}")

# local
uri = "http://localhost:8000/mcp"

# remote
uri = "https://7066414.pythonanywhere.com/mcp"

session = requests.Session()
session.auth = ('ryehigh', '99PercentReady')

fmt = "%Y-%m-%d %H:%M:%S    "
logfile = open(token + ".log", "w")

build_hubs = True
hubs_deployed = []

upload = 0
download = 0
def send_request(action, parameters=""):
    global upload, download
    url = f"{uri}/{action}?token={token}&{parameters}"
    upload += len(url)
    logfile.write(strftime(fmt) + " " + url)
    logfile.write("\n")

    response = session.get(url)
    download += len(response.content)
    if response.status_code != 200:
        wprint(f"BUMMER: code={response.status_code}")
        return {}

    try:
        resp = response.json()
        status = int(resp["status"])
        if status != 0:
            desc = resp["description"]
            wprint(f"code: {status}, description: {desc}")

        return resp
    except Exception as e:
        wprint(f"Exception: {e}")
    return resp


def get_status():
    report = send_request("status_report")
    try:
        team = report["status_report"]["team"]
        week = int(team["week"])
    except Exception as e:
        wprint(f"Exception: {str(e)}")
    return report

def get_final():
    report = send_request("final_report")
    ledger = report["final_report"]

    try:
        wprint("------------------------------------------------------")
        print(fmt_ledger(ledger))
    except Exception as e:
        wprint(f"Exception: {e}")
    return report

from collections import Counter

hub_stats = Counter()

def mine_ore(threshold=5):
    # check if any hubs are full, then ship them
    global last_built_hubs

    # print number of hubs only when new ones are added
    if last_built_hubs < built_hubs:
        last_built_hubs = built_hubs
        wprint(f"total hubs: {built_hubs}")

    team_status = get_status()
    status = int(team_status["status"])
    if status == -1:
        return 0

    try:
        report = team_status["status_report"]
    except:
        return 0

    hubs = report["hubs"]
    hubs_to_ship = []

    total_mined = 0
    total_to_ship = 0
    for id, hub in hubs.items():
        if hub["active"]:
            ore_amts = json.loads(hub["amt"])
            mined = sum(ore_amts.values())
            total_mined += mined
            # hubs with < 5% space remaining get shipped
            if int(hub["active"]) == True and int(hub["space_remaining"]) < threshold:
                hubs_to_ship.append(id)
                total_to_ship += hub_stats.setdefault(id, mined)

    wprint(f"mined {total_mined}")

    insured = ""  # "&insured=true" if total_to_ship * 5 / 1000 > 1000 else ""
    if total_to_ship > 0:
        wprint(f"shipping from {len(hubs_to_ship)} hubs, {hubs_to_ship}: {total_to_ship} tonnes")
        result = send_request("ship_ore", "hubs=" + ",".join(hubs_to_ship) + insured)

        #        wprint(result)
        status = int(result["status"])
        if status != 0:
            wprint(f"code: {status}")
        if status == -1:
            return 0

    return len(hubs_to_ship)

#    return 0

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


# MAIN -----------------------------------------------------------------------------------------------------------------

wprint("---------")
wprint("startup")
resp = send_request("startup")
team = resp["startup"]
avail_balance = int(resp["startup"]["team"]["balance"])

#get_status(True)

params = send_request("parameters", "scenario_id=debug")["parameters"]

ROWS = int(params["rows"])
COLS = int(params["cols"])
MS_PER_WEEK = int(params["ms_per_week"])
LIFETIME = int(params["lifetime"])
HUB_CAPACITY = int(params["hub_capacity"])
PROSPECT_LAG = 7

# pause between polls - don't want to DDOS the mcp!
PAUSE = .9 * MS_PER_WEEK / 1000

COSTS = params["costs"]

send_request("prospect_report")

send_request("market_report")

built_hubs = 0
last_built_hubs = 0

# total cost build, deploy hub, ship hub
total_cost = params["costs"]["hub"]["rate"] + params["costs"]["deploy"]["rate"] + (
        HUB_CAPACITY * params["costs"]["ship"]["rate"]) / 1000

# cash to hold back per hub to ship the ore
reserve = 0

# naive distribution every 3rd row, every third column
# e.g. 10 cols, 5 rows
# oXXoXXoXXo   0,  3,  6,  9
# XXXXXXXXXX
# XXXXXXXXXX
# oXXoXXoXXo  30, 33, 36, 39
# XXXXXXXXXX

SECTOR_ADJACENCY = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1) if not (i == j == 0)]


def get_adjacent_sectors(sid):
    adj_cells = []
    r = sid // COLS
    c = sid % COLS

    for dr, dc in SECTOR_ADJACENCY:
        if (0 <= (r + dr) < ROWS) and (0 <= (c + dc) < COLS):  # boundaries check
            adj_cells.append((r + dr) * COLS + (c + dc))
    return adj_cells


occupied_sectors = []
potential_sectors = []


def get_sectors(start, count):
    # candidates = sectors_to_mine[start:start + count]
    global occupied_sectors
    candidates = []
    attempts = 0;
    while len(candidates) < count:
        sid = 1 + random.sample(potential_sectors, 1)[0]
        if sid not in occupied_sectors:
            adj_sids = get_adjacent_sectors(sid)
            if len(adj_sids) == 8:
                collisions = list(set(adj_sids).intersection(occupied_sectors))
                if len(collisions) == 0:
                    candidates.append(sid)
                    occupied_sectors.append(sid)
                    occupied_sectors += adj_sids
        attempts += 1
        if attempts > 100000:
            break

    #    print(f"attmepts {attempts}")
    [potential_sectors.remove(s-1) for s in candidates]
    return ",".join(str(x) for x in candidates)


build_hubs = True
deployed_hubs = 0
while True:

    # approx max number of hubs can build, deploy, ship with current balance
    hub_num = int((avail_balance) // total_cost)

    team_status = get_status()

    # build hubs
    if hub_num > 0 and build_hubs:
        wprint(f"building {hub_num} hubs...")
        new_hubs = ",".join([f"{hex(d).split('x')[1]}" for d in range(built_hubs, built_hubs + hub_num)])
        result = send_request("build_hubs", "hubs=" + new_hubs)
        status = int(result["status"])

        if status == 0:
            reserve += hub_num * params["costs"]["deploy"]["rate"]
            reserve += hub_num * (params["costs"]["ship"]["rate"] * HUB_CAPACITY) / 1000
            built_hubs += hub_num

    # deploy hubs
    try:
        status_report = team_status["status_report"]
        hubs = status_report["hubs"]
    except:
        hubs = {}

    if len(hubs) > 0:
        hubs_to_deploy = []
        for hub in hubs.values():
            if hub["sector_id"] == -1 and not hub["hub_id"] in hubs_deployed:
                hubs_to_deploy.append(hub["hub_id"])
        hub_num = len(hubs_to_deploy)
        if hub_num > 0:
            hubs_deployed += hubs_to_deploy
            hubs_to_deploy = ",".join(hubs_to_deploy)
            deployed_hubs += hub_num

            new_sectors = get_sectors(deployed_hubs, hub_num)
            # only deploy if hub and sector count match
            if len(new_sectors.split(",")) == len(hubs_to_deploy.split(",")):
                wprint(f"deploying hubs {hubs_to_deploy} -> {new_sectors}")

                result = send_request("deploy_hubs", f"hubs={hubs_to_deploy}&sector_ids={new_sectors}")
                try:
                    status = int(result["status"])
                except:
                    print("invalid result:", result)

    # stop building hubs at the 72% mark and just ship and earn
    if week > LIFETIME * 0.72:
        build_hubs = False

    team_status = get_status()
    try:
        status = team_status["status"]
    except:
        break

    if status < 0:
        break  # times up!

    # closing in on times up, so ship everything
    if LIFETIME - week < params["costs"]["ship"]["weeks"] + 3:
        # ship all hubs regardless of remaining space
        print("  upload", upload)
        print("download", download)
        mine_ore(100)
        break

    if week % PROSPECT_LAG == 0 or len(potential_sectors) == 0:
        rpt = send_request("prospect_report")
        p_report = rpt["prospect_report"]["report"]
        for sector in p_report:
            sector_id = int(sector[0])
            ore_id = sector[1]
            est = int(sector[2])
            if est > 35000 and sector_id:
                potential_sectors.append(sector_id)

    team = team_status["status_report"]["team"]
    avail_balance = int(team["balance"]) - reserve
    week = int(team["week"])

    mine_ore()
    sleep(PAUSE)

# wrapup
print("  upload", upload)
print("download", download)
get_final()
logfile.flush()
logfile.close()

