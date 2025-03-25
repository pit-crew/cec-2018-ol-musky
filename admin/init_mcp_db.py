import yaml

from mcp.models import Parameter
from mcp.models import Cost
from mcp.models import Belt

#from sidmeier.settings import DATA_FOLDER
DATA_FOLDER = "../config/"
try:
	print("initializing database")
	with open(DATA_FOLDER + "mcp.yaml", 'r') as ymlfile:
		cfg = yaml.load(ymlfile)

		Belt.objects.all().delete()
		belt = cfg["belt"]
		with open(DATA_FOLDER + belt["file"]) as f:
			sector_id = 0
			rows = f.read().splitlines()
			for row in rows:
				cols = row.split(',')
				Belt(sector_id=sector_id, ore_id=cols[0], deposit_amt=int(cols[1])).save()
				sector_id += 1

		Parameter.objects.all().delete()
		Cost.objects.all().delete()

		const = cfg["constants"]
		scenario_id = cfg["scenario_id"]
		param = Parameter(scenario_id=cfg["scenario_id"], 
			lifetime = int(const["lifetime"]), 
			rows = int(belt["rows"]), 
			cols = int(belt["cols"]), 
			hub_capacity = int(const["hub_capacity"]), 
			mining_rate = int(const["mining_rate"]), 
			starting_capital = int(const["starting_capital"]), 
			ms_per_week = int(const["ms_per_week"]),
			prospecting_offset = int(belt["prospecting_offset"]))
		param.save()

		c = cfg["costs"]
		Cost(parameter=param, item="hub",    rate=int(c["hub"]["rate"]),    weeks=int(c["hub"]["weeks"])).save()
		Cost(parameter=param, item="deploy", rate=int(c["deploy"]["rate"]), weeks=int(c["deploy"]["weeks"])).save()
		Cost(parameter=param, item="ship",   rate=int(c["ship"]["rate"]),   weeks=int(c["ship"]["weeks"])).save()
		Cost(parameter=param, item="move",   rate=int(c["move"]["rate"]),   weeks=int(c["move"]["weeks"])).save()
except Exception as e:
	print("Exception", e)

