import json
from datetime import datetime

import django
import pytz
from django.db import models


# Parameter set for entire game 
#
class Parameter(models.Model):
    scenario_id = models.CharField(max_length=32, primary_key=True)
    lifetime = models.IntegerField()
    rows = models.IntegerField()
    cols = models.IntegerField()
    hub_capacity = models.IntegerField()
    mining_rate = models.IntegerField()
    starting_capital = models.IntegerField()
    ms_per_week = models.IntegerField()
    prospecting_offset = models.IntegerField(default=7)

    def as_dict(self):
        costs = {cost.item: cost.as_dict() for cost in self.cost_set.all()}
        d = {"lifetime": self.lifetime, "rows": self.rows, "cols": self.cols,
             "hub_capacity": self.hub_capacity, "mining_rate": self.mining_rate, "ms_per_week": self.ms_per_week,
             "costs": costs}
        return d


# Operational costs
#
class Cost(models.Model):
    parameter = models.ForeignKey(Parameter, default=None, on_delete=models.CASCADE)
    id = models.AutoField(primary_key=True)
    item = models.CharField(max_length=16)
    weeks = models.IntegerField()
    rate = models.FloatField()

    def as_dict(self):
        return {"item": self.item, "weeks": self.weeks, "rate": self.rate}


# The team's registration
#
class Team(models.Model):
    token = models.CharField(max_length=40, primary_key=True)
    name = models.CharField(max_length=64)
    week = models.IntegerField()
    start_time = models.DateTimeField()
    balance = models.IntegerField()

    def as_dict(self):
        d = {"token": self.token, "name": self.name, "week": self.week, "start_time": str(self.start_time),
             "balance": self.balance}
        return d


# Team financial Ledger
#
class Ledger(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    week = models.IntegerField()
    item = models.CharField(max_length=32)
    credit = models.FloatField()
    debit = models.FloatField()

    def as_dict(self):
        d = {"week": self.week, "item": self.item, "credit": self.credit, "debit": self.debit}
        return d


# Mining hub
#
class Hub(models.Model):
    class Meta:
        unique_together = (('team', 'hub_id'),)

    team = models.ForeignKey(Team, default=None, on_delete=models.CASCADE)
    hub_id = models.CharField(max_length=8)
    start_time = models.DateTimeField(default=django.utils.timezone.now)
    sector_id = models.IntegerField()
    amt = models.CharField(max_length=32, default="{}")
    active = models.BooleanField()
    space_remaining = models.IntegerField()

    def activate(self, sector_id):
        self.sector_id = sector_id
        self.active = True
        self.start_time = pytz.utc.localize(datetime.now())
        self.save()
        return 0

    def deactivate(self):
        self.sector_id = -1
        self.active = False
        self.save()
        return 0

    def pause(self):
        self.active = False

    # load ore from multiple sites possibly with different ore_ids
    def load_ore(self, mined_ore, hub_capacity):
        excess = 0
        amts = json.loads(self.amt)
        for ore_id, ore in mined_ore.items():
            amt = amts.setdefault(ore_id, 0)
            excess += max(amt + ore - hub_capacity, 0)
            amt = min(amt + ore, hub_capacity)
            amts[ore_id] = amt

        self.amt = json.dumps(amts)
        self.space_remaining = 100 - int(100 * sum(amts.values()) / hub_capacity)
        return excess

    def unload_and_reset(self):
        amt_to_unload = self.amt
        self.amt = "{}"
        self.space_remaining = 100
        self.start_time = pytz.utc.localize(datetime.now())
        self.activate(self.sector_id)
        return amt_to_unload

    def as_dict(self):
        d = {"hub_id": self.hub_id, "start_time": str(self.start_time), "sector_id": self.sector_id,
             "amt": self.amt, "space_remaining": self.space_remaining, "active": self.active}

        return d


# Store for Current Market value of ore
#
class Market(models.Model):
    class Meta:
        unique_together = (("week", "ore_id"))

    week = models.IntegerField()
    ore_id = models.CharField(max_length=8)
    price = models.FloatField()


# Asteroid Belt
#
class Belt(models.Model):
    sector_id = models.IntegerField(primary_key=True)
    ore_id = models.CharField(max_length=8)
    deposit_amt = models.IntegerField()


# Site - to keep track of where a team is mining
#
class Site(models.Model):
    class Meta:
        unique_together = (("team", "sector_id"))

    team = models.ForeignKey(Team, default=None, on_delete=models.CASCADE)
    sector_id = models.IntegerField()
    ore_id = models.CharField(max_length=8, default="X")
    deposit_amt = models.IntegerField()

    def as_dict(self):
        d = {"sector_id": self.sector_id, "ore_id": self.ore_id, "deposit_amt": self.deposit_amt}
        return d


class Order(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    week = models.IntegerField()
    action = models.CharField(max_length=32)
    hub_list = models.TextField()
    sector_id_list = models.TextField()
    ore_load = models.CharField(max_length=32, default="{}")
    complete = models.BooleanField(default=False)
    insured = models.BooleanField(default=False)
    pirated = models.BooleanField(default=False)

    def as_dict(self):
        d = {"week": self.week, "action": self.action, "hub_list": self.hub_list,
             "sector_id_list": self.sector_id_list, "ore_load": self.ore_load, "complete": self.complete}
        return d


# Convenience class
#
class TeamSession:
    def __init__(self, team):
        self.team = team.as_dict()
        self.hubs = {hub.hub_id: hub.as_dict() for hub in team.hub_set.all()}
        self.orders = [order.as_dict() for order in team.order_set.filter(complete=0)]

    def as_dict(self):
        d = {"team": self.team, "hubs": self.hubs, "pending_orders": self.orders}
        return d
