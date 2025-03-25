import hmac
import json
import logging
import sys
import traceback

import pytz

logger = logging.getLogger(__name__)
logging.disable(logging.CRITICAL)

from datetime import datetime

from mcp.constants import _SECTOR_IDS
from mcp.constants import _HUB
from mcp.constants import _HUBS
from mcp.constants import _DEPLOY
from mcp.constants import _MOVE
from mcp.constants import _SHIP

from mcp.constants import PARAM
from mcp.constants import COST
from mcp.constants import SECTOR_ADJACENCY

from django.http import HttpResponse
from django.template.loader import get_template
from django.db.models import Max
from django.db.models import Sum


from hashlib import sha1

from mcp.models import Team
from mcp.models import Parameter
from mcp.models import Ledger
from mcp.models import Hub
from mcp.models import TeamSession
from mcp.models import Belt
from mcp.models import Order

from functools import wraps
from bulk_update.helper import bulk_update
from random import randint, getrandbits
from collections import Counter
from math import sin, cos, ceil

_RELOCATE_HUBS = "relocate_hubs"
_DELIVER_HUBS = "deliver_hubs"
_SHIP_AND_SELL_ORE = "ship and sell ore"

# filter for crap characters in request data
#
disallowed = lambda char: char.isalnum() or char == '-' or char == '_'

# used by above filter
#
def not_alnum(s): return not "".join(filter(disallowed, s)) == s

# THE target asteroid belt segment data
#
belt = Belt.objects.all()


# Endpoint /mcp/ - the progress tracker
#
def index(request):
    template = get_template('index.html')
    name = ""
    try:
        token = request.GET.get("token")
        team = Team.objects.get(pk=token)
        name = team.name
    except:
        pass

    # creating the values to pass
    context = {
        'name': name,
    }
    return HttpResponse(template.render(context, request))


# Endpoint /guide/
#
def guide(request):
    template = get_template('guide.html')

    # creating the values to pass
    context = {
        'ms_per_week': PARAM.ms_per_week,
        'starting_capital': PARAM.starting_capital,
        'lifetime': PARAM.lifetime,
        'rows': PARAM.rows,
        'cols': PARAM.cols,
        'hub_capacity': PARAM.hub_capacity,
        'mining_rate': PARAM.mining_rate,
        'build_weeks': COST[_HUB].weeks,
        'build_rate': COST[_HUB].rate,
        'deploy_weeks': COST[_DEPLOY].weeks,
        'deploy_rate': COST[_DEPLOY].rate,
        'move_weeks': COST[_MOVE].weeks,
        'move_rate': COST[_MOVE].rate,
        'ship_weeks': COST[_SHIP].weeks,
        'ship_rate': COST[_SHIP].rate,
        'total_years': int(PARAM.lifetime / 52),
        'total_minutes': int(PARAM.lifetime * PARAM.ms_per_week / 1000 / 60),
        'preport_freq': int(PARAM.lifetime // PARAM.prospecting_offset),
    }
    return HttpResponse(template.render(context, request))


# Decorators

# Catch Exceptions - for dev/debuggin
#
def catch_exceptions(fn):
    @wraps(fn)
    def decorator(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(
                "E=%s, F=%s, L=%s" % (str(e), traceback.extract_tb(exc_tb)[-1][0], traceback.extract_tb(exc_tb)[-1][1]))
            logger.error(
                "E=%s, F=%s, L=%s" % (str(e), traceback.extract_tb(exc_tb)[-1][0], traceback.extract_tb(exc_tb)[-1][1]))

    return decorator


# Require Token - ensure 'token' param is in the request
#
def require_token(fn):
    def wrapper(request):
        try:
            if PARAM is None:
                set_paremeters()

            token = request.GET.get("token")
            if len(token) > 32 or not_alnum(token):
                return mk_response("validation", {}, 1000, "token must be 32 or fewer alpha-numerics")
        except:
            return mk_response("validation", {}, 1001, "token required - see competition coordinator")
        return fn(request)

    return wrapper


def require_admin_token(fn):
    def wrapper(request):
        try:
            if PARAM is None:
                set_paremeters()

            token = request.GET.get("token")
            if len(token) > 32 or not_alnum(token):
                return mk_response("validation", {}, 1700, "token must be 32 or fewer alpha-numerics")
            if token != "backhaus":
                return mk_response("reset", {}, 1701, "admin token required")
        except:
            return mk_response("validation", {}, 1702, "token required - see competition coordinator")
        return fn(request)

    return wrapper

# Validate Life - reject request if life has expired
# if ok, update mining and order processing before executing request
#
def validate_life(fn):
    def wrapper(request):
        try:
            token = request.GET.get("token")
            team = Team.objects.get(token=token)
            team.week = get_week(team.start_time)
            if team.week > PARAM.lifetime:
                return mk_response("validation", {"week": team.week, "max": PARAM.lifetime}, -1, "times up")
            team.save()

            fulfillOrders(team)
            mine_asteroids(team)

            # inject the valid team into the function
            fn.__globals__['team'] = team

            return fn(request)
        except Team.DoesNotExist:
            return mk_response("validation", {}, 1100, "no team for token {0}")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(
                "E=%s, F=%s, L=%s" % (str(e), traceback.extract_tb(exc_tb)[-1][0], traceback.extract_tb(exc_tb)[-1][1]))
            logger.error(
                "E=%s, F=%s, L=%s" % (str(e), traceback.extract_tb(exc_tb)[-1][0], traceback.extract_tb(exc_tb)[-1][1]))
            return mk_response("validation", {}, 1101, str(e))

    return wrapper


#
# Admin-only API ------------------------------------------------------------------
# 

# Register a new team 
# /register_team?token=<admin_token>&name=<team name>&key=<any string will do>
# returns team model with new token
#
@require_admin_token
def register_team(request):
    try:
        key = request.GET.get("key")
        name = request.GET.get("name")

        if key is None or name is None or len(name) > 32 or not_alnum(name):
            return mk_response("validation", {}, 1201, "name must be 32 or fewer alpha-numerics")
    except:
        name = "developer"

    try:
        token = mk_token(name, key)
        team = reset_team(token, name)
    except Exception as e:
        return mk_response("register_team", {}, -1, str(e))

    return mk_response("register_team", team.as_dict(), 0, "")

# used by /register_team and /startup to erase team history, data and reset weeks clock to zero
#
def reset_team(token, name):
    try:
        Team.objects.get(token=token).delete()
    except:
        pass

    team = Team(token=token,
                name=name,
                week=0,
                start_time=pytz.utc.localize(datetime.now()),
                balance=PARAM.starting_capital)
    team.save()

    Ledger(team=team,
           week=0,
           item="startup",
           credit=PARAM.starting_capital,
           debit=0).save()

    return team


# Change the scenario
# /mcp/set_scenario?token=backhaus&scenario=<scenario name>
#
@require_admin_token
def set_scenario(request):
 
    scenario = request.GET.get("scenario")
    if scenario is None:
        return mk_response("set_scenario", {}, 1601, "scenario name required")

    try:
        PARAM = Parameter.objects.get(pk=scenario)
        COST = {cost.item: cost for cost in PARAM.cost_set.all()}
    except Parameter.DoesNotExist:
        return mk_response("set_scenario", {}, 1602, "scenario doesn't exist")

    return mk_response("set_scenario", PARAM, 0, "")


# Gets list of team summaries for tracking
# /mcp/teams_summary?token=backhaus
#
@require_admin_token
def teams_summary(request):
    teams = []
    try:
        teams = Team.objects.all()
        summary = [team.as_dict() for team in teams]

    except Exception as e:
        return mk_response("teams_summary", {}, 1301, str(e))

    return mk_response("teams_summary", summary, 0, "")


# Gets list of team details for tracking
# /mcp/teams_detail?token=backhaus
# 
@require_token
def teams_detail(request):
    teams = []
    try:
        token = request.GET.get("token")
        if token != "backhaus" and token != "s9SdrpqoTzNULfctqEJg":
            return mk_response("teams_detail", {}, 1400, "admin token required")
        teams = Team.objects.all().order_by('name')
        details = [mk_details(team) for team in teams]
        results = {"rows": PARAM.rows, "cols": PARAM.cols, "teams": details}

    except Exception as e:
        return mk_response("teams_detail", {}, 1401, str(e))

    return HttpResponse(json.dumps(results, default=dumper, indent=4), content_type="application/json")

# Gets list of team efficiency statistics
# /mcp/teams_stats?token=backhaus
#
@require_token
def teams_stats(request):
    teams = []
    try:
        token = request.GET.get("token")
        if token != "backhaus" and token != "s9SdrpqoTzNULfctqEJg":
            return mk_response("teams_detail", {}, 1400, "admin token required")
        teams = Team.objects.all().order_by('name')

        results = {}
        ore_prices = get_market_report(PARAM.lifetime)

        for team in teams:
            hub_count = team.hub_set.count()
            site_count = team.site_set.count()
            value = team.ledger_set.aggregate(Sum('debit'))['debit__sum']
            costs = (0 if value is None else int(value))
            value = team.ledger_set.aggregate(Sum('credit'))['credit__sum']
            revenue = (0 if value is None else int(value)) - PARAM.starting_capital

            gross_profit_margin = 0
            cost_per_hub = 0
            revenue_per_hub = 0
            gross_profit_margin = 0
            pending_order_count = 0
            pirated_revenue = 0
            pirated_order_count = 0
            total_loss_ratio = 0
            pending_revenue = 0
            
            gross_profit = revenue - costs
            if gross_profit > 0:
                gross_profit_margin = int(100 * revenue / gross_profit)

            if hub_count > 0:
                cost_per_hub = int(costs/hub_count)
                revenue_per_hub = int(revenue/hub_count)

            pending_orders = team.order_set.filter(complete = False)
            pending_order_count = len(pending_orders)

            X = 0
            Y = 0
            for order in pending_orders:
                ore = json.loads(order.ore_load)
                X += ore["X"] if "X" in ore else 0
                Y += ore["Y"] if "Y" in ore else 0

            pending_revenue += X * ore_prices["prices"]["X"] // 1000
            pending_revenue += Y * ore_prices["prices"]["Y"] // 1000

            pirated_orders = team.ledger_set.filter(item="ore was pirated")
            pirated_order_count = len(pirated_orders)
            for entry in pirated_orders:
                pirated_revenue += entry.credit // .20

            total_lost_revenue = pending_revenue + pirated_revenue
            if revenue + total_lost_revenue > 0:
                total_loss_ratio = 100 * total_lost_revenue//(revenue + total_lost_revenue)

            results[team.name] = {"hubs":hub_count,
                                  "sites":site_count,
                                  "costs":costs,
                                  "revenue":revenue,
                                  "gross_profit": gross_profit,
                                  "gross_profit_margin": gross_profit_margin,
                                  "cost_per_hub": cost_per_hub,
                                  "revenue_per_hub": revenue_per_hub,
                                  "pending_order_count": pending_order_count,
                                  "pending_revenue": pending_revenue,
                                  "pirated_order_count": pirated_order_count,
                                  "pirated_revenue": pirated_revenue,
                                  "total_lost_revenue": total_lost_revenue,
                                  "total_loss_ratio": total_loss_ratio,
                                  }

    except Exception as e:
        return mk_response("teams_detail", {}, 1401, str(e))

    return HttpResponse(json.dumps(results, default=dumper, indent=4), content_type="application/json")

# Convenience function to simply details for tracking
#
def mk_details(team):
    tsession = TeamSession(team)
    sector_ids = json.dumps([hub["sector_id"] for hub in tsession.hubs.values()])
    return {"name": team.name,
            "week": team.week,
            "balance": team.balance,
            "sector_ids": sector_ids}


# clear all teams from database
# /mcp/delete_all?token=backhaus
#
@require_admin_token
def delete_all(request):
    c = 0
    try:
        teams = Team.objects.all()
        c = teams.count()
        Team.objects.all().delete()

    except Exception as e:
        logger.error("Exception - reset_all", e)
        mk_response("reset_all", {}, 1501, f"failed: {e}")

    return mk_response("reset_all", {"deleted": c}, 0, "")


#
# Team API --------------------------------------------------------------------
#

# Team bootstrap
# resets team: cleans ledger, hubs and resets clock
# /mcp/startup?token=<token>
#
@require_token
@catch_exceptions
def startup(request):
    try:
        token = request.GET.get("token")
        team = Team.objects.get(token=token)
        team = reset_team(team.token, team.name)

    except Team.DoesNotExist:
        return mk_response("Exception - startup", {}, 2100, f"no team found for token {token}")
    except Exception as e:
        return mk_response("Exception - startup", {}, 2101, f"{e} (token {token})")

    session = TeamSession(team).as_dict()
    return mk_response("startup", session, 0, "")


# Get game-wide parameters
# /mcp/parameters?token=<token>
#
@require_token
def parameters(request):
    params = {}
    try:
        scenario_id = "debug"
        params = Parameter.objects.get(pk=scenario_id)
    except:
        return mk_response("parameters", {}, 2200, f"no such scenario_id ({scenario_id})")

    return mk_response("parameters", params.as_dict(), 0, "")


# Build hubs
# /mcp/build_hubs?token=<token>&hubs=h1,h2,...,hn
# Checks money then adds new hubs to team
#
@require_token
@validate_life
def build_hubs(request):
    hub_ids = request.GET.get(_HUBS)
    hubs_to_build = hub_ids.split(",")
    n = len(hubs_to_build)
    cost = n * int(COST[_HUB].rate)

    # check finances
    if cost > team.balance:
        return mk_response("build_hubs", {"hubs_to_build": n}, 2301, "not enough money")

    # update finances
    Ledger(week=team.week,
           team=team,
           item="build hubs",
           credit=0,
           debit=int(cost)).save()

    team.balance -= cost
    team.save()

    # Order the build
    Order(team=team,
          week=team.week + COST[_HUB].weeks,
          action=_DELIVER_HUBS,
          hub_list=hub_ids).save()

    return mk_response("build_hubs", {"hubs_built": n, "week": team.week}, 0)


@catch_exceptions
def fulfill_deliver_hubs(team, hub_ids):
    # build hubs
    new_hubs = []
    for hub in hub_ids:
        new_hubs.append(Hub(team=team,
                            hub_id=hub,
                            amt={},
                            start_time=pytz.utc.localize(datetime.now()),
                            sector_id=-1,
                            space_remaining=100,
                            active=False))
    Hub.objects.bulk_create(new_hubs)
    team.save()


# Deploy hubs to belt
# /mcp/deploy_hubs?token=<token>&hubs=h1,h2,...,hn&sector_ids=N1,N2,...,Nn
# Checks money then deploys hubs to belt
#
@require_token
@validate_life
def deploy_hubs(request):
    return locate_hubs(request, team, "deploy hubs", _DEPLOY)


# Move hub within belt
# /mcp/deploy_hubs?token=<token>&hubs=h1,h2,...,hn&sector_ids=N1,N2,...,Nn
# Checks money then moves hubs to new locations in belt
#
@require_token
@validate_life
def move_hubs(request):
    return locate_hubs(request, team, "move hubs", _MOVE)


def locate_hubs(request, team, endpoint, action):
    hub_ids = request.GET.get(_HUBS)
    sector_ids = request.GET.get(_SECTOR_IDS)

    if hub_ids is None or sector_ids is None:
        return mk_response(endpoint, {}, 2400, "hub list and sector_id list need to be the same length")

    hub_list = hub_ids.split(",")
    sector_id_list = list(map(int, sector_ids.split(",")))

    # Validate hub and sector_id lists:
    #
    diff = abs(len(hub_list) - len(sector_id_list))
    if diff != 0:
        return mk_response(endpoint, {}, 2401, f"hub list and sector_id list need to be the same length {diff}")

    max_sector_id = PARAM.rows * PARAM.cols
    sector_ids_to_locate = list(map(int, sector_id_list))
    invalid_sectors = [sid for sid in sector_id_list if not (0 <= sid < max_sector_id)]
    if len(invalid_sectors) > 0:
        return mk_response(endpoint, {}, 2404,
                           f"sector {invalid_sectors} - sector IDs must be within the range [0,{max_sector_id})")

    hubs_to_locate = team.hub_set.filter(hub_id__in=hub_list)
    if len(hubs_to_locate) == 0 or len(hubs_to_locate) != len(hub_list):
        return mk_response(endpoint, {}, 2402, "some hubs requested do not exist")

    if action == _MOVE:
        undeployed = team.hub_set.filter(hub_id__in=hub_list, sector_id=-1)
        if len(undeployed) != 0:
            return mk_response(endpoint, {}, 2408, f"hubs must be deployed before being moved: {undeployed}")

    n = len(hubs_to_locate)

    # check finances
    cost = n * int(COST[action].rate)
    if cost > team.balance:
        return mk_response(endpoint, {"hubs": n, "cost": cost}, 2409, "not enough money")

    # the data appear to be valid, check against the rules:
    #

    # are any hubs are already in deployment orders?
    orders = team.order_set.filter(action=_RELOCATE_HUBS, complete=0)
    in_deployment = []
    for order in orders:
        in_deployment += list(order.hub_list.split(","))

    collisions = list(set(hub_list).intersection(in_deployment))
    if len(collisions) > 0:
        return mk_response(endpoint, {}, 2403, f"hubs: {collisions} currently being deployed")

    # does request list have overlaps among themselves? including duplicates
    requested_sectors = sector_ids_to_locate[:]  # make copy
    if len(list(set(requested_sectors))) != len(requested_sectors):
        return mk_response(endpoint, {"hubs": n}, 2405, "hubs must be deployed to unique sectors")

    # are adjacent sectors overlap among the requested?
    for sid in sector_ids_to_locate:
        adj_sectors = get_adjacent_sectors(sid)
        collisions = list(set(requested_sectors).intersection(adj_sectors))
        if len(collisions) > 0:
            return mk_response(endpoint, {"hubs": n}, 2406, "mining bots must use separate sectors")
        requested_sectors += adj_sectors

    # whew, finally, place the hubs
    #

    # gather list of occupied sectors + adjacent sectors from existing deployed hubs
    deployed_hubs = team.hub_set.filter(sector_id__gte=0)
    if action == _MOVE:
        # Remove hubs from the deployed list so their sectors are freed up
        deployed_hubs = [hub for hub in deployed_hubs if hub.hub_id not in hub_list]

    occupied_sectors = []
    for hub in deployed_hubs:
        occupied_sectors.append(hub.sector_id)
        occupied_sectors += get_adjacent_sectors(hub.sector_id)

    # last check...are there any sector overalaps?
    collisions = list(set(requested_sectors).intersection(occupied_sectors))
    if len(collisions) > 0:
        return mk_response(endpoint, {"hubs": n}, 2407, f"unable to deploy to occupied sectors: {collisions}")

    # update finances
    team.balance -= cost
    Ledger(week=team.week,
           team=team,
           item=endpoint,
           credit=0,
           debit=cost).save()

    # deactivate for the big move
    [hub.deactivate() for hub in hubs_to_locate]

    team.save()

    # Now that everything has been validateed, rrder the re-location
    Order(team=team,
          week=team.week + COST[action].weeks,
          action=_RELOCATE_HUBS,
          hub_list=hub_ids,
          sector_id_list=sector_ids).save()

    return mk_response(endpoint, {"hubs relocated": n, "cost": cost}, 0)


def fulfill_relocate_hubs(team, hub_ids, sector_ids):
    hubs_to_locate = team.hub_set.filter(hub_id__in=hub_ids)
    sector_ids_to_locate = sector_ids

    i = 0
    ore_id = 'X'
    for hub in hubs_to_locate:
        sector_id = sector_ids_to_locate[i]
        for sid in get_adjacent_sectors(sector_id):
            sector = belt.get(sector_id=sid)
            team.site_set.get_or_create(sector_id=sid,
                                        defaults={"team": team,
                                                  "ore_id": sector.ore_id,
                                                  "deposit_amt": sector.deposit_amt})
        hub.activate(sector_id)
        i += 1
    team.save()
    return i


# Ship ore to Earth
# /mcp/ship_ore?token=<token>&hubs=h1,h2,...,hn
# Checks money then empties given hubs, ships ore to Earth and sells it
# 
@require_token
@validate_life
def ship_ore(request):
    hub_ids = request.GET.get(_HUBS)
    hub_list = hub_ids.split(",")
    hubs_to_ship = team.hub_set.filter(hub_id__in=hub_list)

    insured = False
    _insured = request.GET.get("insured")
    if _insured is not None and _insured.lower() == "true":
        insured = True

    n = len(hubs_to_ship)
    if n == 0:
        return mk_response("ship_ore", {"hubs_to_unload": n}, 2501, "no hubs requested")

    ore_load = Counter()
    for hub in hubs_to_ship:
        for ore_id, amt in json.loads(hub.amt).items():
            ore_load.setdefault(ore_id, 0)
            ore_load.update({ore_id: amt})
    ore_load = dict(ore_load)

    total_ore = sum(ore_load.values())
    if total_ore == 0:
        return mk_response("ship_ore", {"hubs_to_unload": n}, 2502, f"no ore to ship")

    # check finances
    cost = total_ore * int(COST[_SHIP].rate) / 1000
    premium = 0.20 * cost if insured else 0

    if (cost + premium) > team.balance:
        return mk_response("ship_ore", {"hubs_to_unload": n, "cost": cost}, 2503, "not enough money")

    # unload ore
    for hub in hubs_to_ship:
        hub.pause()  # prevent further mining until unloaded
        hub.unload_and_reset()  # this reactivates for more mining

    # update finances - take the money
    team.balance -= (cost + premium)
    Ledger(week=team.week,
           team=team,
           item="ship ore",
           debit=cost,
           credit=0).save()

    if insured:
        Ledger(week=team.week,
               team=team,
               item="insurance",
               debit=premium,
               credit=0).save()

    team.save()
    Order(team=team,
          week=team.week + COST[_SHIP].weeks,
          action=_SHIP_AND_SELL_ORE,
          insured=insured,
          ore_load=json.dumps(ore_load)).save()

    return mk_response("ship_ore", {"hubs_dumped": n, "ore": ore_load}, 0)

# execute ship-and-sell work order
#
def fulfill_ship_and_sell_ore(team, ore_load, pirated=False):
    # sell_ore
    ore_prices = get_market_report(team.week)

    revenue = 0
    for ore_id, amt in ore_load.items():
        price = ore_prices["prices"][ore_id]
        ktons = int(amt / 1000)
        revenue += int(ktons * price)

    # update finances
    team.balance += revenue
    Ledger(week=team.week,
           team=team,
           item="sell ore" if pirated == False else "ore was pirated",
           debit=0,
           credit=revenue).save()
    team.save()
    return 0


# Order fulfillment for build, move and ship/sell
#
@catch_exceptions
def fulfillOrders(team):
    status = 0
    orders = team.order_set.filter(week__lte=team.week, complete=False).order_by('week')
    for order in orders:
        hub_list = order.hub_list.split(",")
        n = len(hub_list)
        if order.action == _DELIVER_HUBS:
            fulfill_deliver_hubs(team, hub_list)
            order.complete = True

        elif order.action == _RELOCATE_HUBS:
            sector_id_list = list(map(int, order.sector_id_list.split(",")))
            n = fulfill_relocate_hubs(team, hub_list, sector_id_list)
            order.complete = True

        elif order.action == _SHIP_AND_SELL_ORE:
            ore_load = json.loads(order.ore_load)
            load_wt = sum([amt for amt in ore_load.values()])
            approx_value = int(load_wt * 6 / 1000)
            # if attractive shipment then flip a coin to attack for $1 billion
            if not order.insured and approx_value > 1000 and bool(getrandbits(1)):
                order.pirated = True
                # steal 80-90% of the ore
                for ore_id, wt in ore_load.items():
                    ore_load[ore_id] = int(randint(10, 20) * wt / 100)

            n = fulfill_ship_and_sell_ore(team, ore_load, order.pirated)
            order.complete = True

    bulk_update(orders, update_fields=["complete"])


#
# Reports --------------------------------------------------------------------
#

# Market Report
# List of current price of each ore type for the week
# TODO implement
@require_token
@validate_life
def market_report(request):
    report = get_market_report(team.week)
    return mk_response("market_report", report, 0)


def get_market_report(week):
    X = ceil(rpt_X(week) * 100) / 100
    Y = ceil(rpt_Y(week) * 100) / 100
    # X = 4.5
    # Y = 4.5
    return {"week": week, "prices": {"X": X, "Y": Y}, "status": 0}

# helper stuff for market report
rad = 3.14 / 180


def rpt_X(week):
    return 5 + (sin(5 * week * rad) + cos(2 * week * rad) + sin(week / 10 * rad) - 1.55) * (5 / 3.989)


def rpt_Y(week):
    return 9 + (cos(3 * week * rad) + cos(7 * week * rad) + sin(week / 10 * rad) - 1.60) * (5 / 4.278)


# Prospecting Report
# Simulate prospecting by retrieving % estimates from file for
# the current scenario, for the current week
#
@require_token
@validate_life
def prospect_report(request):
    bucket_size = PARAM.lifetime // PARAM.prospecting_offset
    offset = team.week // bucket_size

    max_deposit = belt.aggregate(Max('deposit_amt'))
    err = float(max_deposit["deposit_amt__max"]) // 6.5  # +/- 15% error

    p_report = []

    for i in range(offset, PARAM.cols * PARAM.rows, PARAM.prospecting_offset):
        est = max(0, randint(-err, err) + belt[i].deposit_amt)
        p_report.append((i, belt[i].ore_id, est))

    return mk_response("prospect_report", {"report": p_report}, 0)


# Status Report
# For every status report, all Active sites are
# updated by "extracting" ore using the rate of 
# extraction and the time spent at that site and the limit of ore present.
# The report returns the list of hubs and the % remaining space
#
@require_token
@validate_life
def status_report(request):
    session = TeamSession(team)
    return mk_response("status_report", session, 0)

@require_token
def get_ledger(request):
    token = request.GET.get("token")
    team = Team.objects.get(pk=token)
    ledger = [entry.as_dict() for entry in team.ledger_set.all()]
    status = 0
    if team.week > PARAM.lifetime:
        status = -1
    return mk_response("ledger", ledger, status)

# Final Report
# the difference here is that no mining or other activity
# will get triggered.
#
@require_token
def final_report(request):
    token = request.GET.get("token")
    try:
        team = Team.objects.get(pk=token)
        session = TeamSession(team)
    except:
        session = {}
    return mk_response("final_report", session, 0)

#
# Mining helper functions ------------------------------------------------
#

# Mine asteroids
# simulates bots' mining activiy, depleting sectors of ore while
# filling up hubs
#
@catch_exceptions
def mine_asteroids(team):
    active_hubs = team.hub_set.filter(active__exact=True, sector_id__gte=0)

    # for each hub compute mined ore from start_time of activation
    # (start_time is reset when hub is dumped)
    total_ore = Counter()
    for hub in active_hubs:
        # mine ore from the 8 sectors adjacent to the hub's sector
        weeks = get_week(hub.start_time)
        if weeks > 0:
            actual_mined = extract_ore(team, int(hub.sector_id), weeks)
            hub.load_ore(actual_mined, PARAM.hub_capacity)
            hub.start_time = pytz.utc.localize(datetime.now())
            hub.save()
            total_ore.update(actual_mined)
    return dict(total_ore)


# extract the ore from the sectors adjacent to the hub
#
def extract_ore(team, sector_id, weeks):
    max_ore = weeks * PARAM.mining_rate
    adj_sectors = team.site_set.filter(sector_id__in=get_adjacent_sectors(sector_id))

    total_ore = Counter()
    for sector in adj_sectors:
        ore_id = sector.ore_id
        # can't take more than is avialable in the deposit
        if sector.deposit_amt > 0:
            ore = min(sector.deposit_amt, max_ore)
            sector.deposit_amt -= ore
            total_ore.setdefault(ore_id, 0)
            total_ore.update({ore_id: ore})

    bulk_update(adj_sectors, update_fields=["deposit_amt"])  # updates only the remaining ore
    return dict(total_ore)


# get_adjacent_sectors
# returns list of up to 8 sectors adjacent to the given one
#
def get_adjacent_sectors(sid):
    adj_cells = []
    try:
        r = sid // PARAM.cols
        c = sid % PARAM.cols

        for dr, dc in SECTOR_ADJACENCY:
            if (0 <= (r + dr) < PARAM.rows) and (0 <= (c + dc) < PARAM.cols):  # boundaries check
                adj_cells.append((r + dr) * PARAM.cols + (c + dc))
    except Exception as e:
        logger.error("get_adjacent_sectors exception", e)
    return adj_cells


#
# Utility Functions ------------------------------------------------------------
#

# get_week - compute the current week
# e.g. 1 sim_week = 250 real ms
#
def get_week(start_time):
    delta = pytz.utc.localize(datetime.now()) - start_time
    elapsed_weeks = int(delta.total_seconds() * 1000) // PARAM.ms_per_week
    return elapsed_weeks


# mk_token
# wraps the python hashing algorithm with something better
#
def mk_token(data, secret_key, algo=sha1):
    try:
        dig = hmac.new(bytes(secret_key, 'ascii'),
                       msg=bytes(data, 'ascii'), digestmod=algo)
    except:
        raise
    return dig.hexdigest()[:32]


# dumper - helper for json serialization
#
def dumper(obj):
    try:
        return obj.toJSON()
    except:
        return obj.__dict__


# mk_response
# Create response package
#
@catch_exceptions
def mk_response(action, response, status, description=""):
    data = response
    if response != {}:
        try:
            data = json.dumps(response, default=dumper, indent=4)
        except Exception as e:
            logger.error("mk_response error parsing", data)
            data = {"exception": e}
    resp = f"{{\"{action}\":{data},\"status\":{status}, \"description\":\"{description}\"}}"
    return HttpResponse(resp.encode("utf-8"), content_type="application/json")

#	import pdb; pdb.set_trace()
