import yaml

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
except Exception as e:
	print("Exception", e)

