# Helper for determining sectors adjacent to a given sector
#
SECTOR_ADJACENCY = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1) if not (i == j == 0)]

# Field name constants
#
_BANK_BALANCE = "bank_balance"
_BELT_MAP = "belt_map"
_ID = "id"
_KEY = "key"
_START_TIME = "start_time"
_HUB = "hub"
_HUBS = "hubs"
_DEPLOY = "deploy"
_MOVE = "move"
_SHIP = "ship"
_SECTOR_IDS = "sector_ids"
_LEDGER = "ledger"
_CREDIT = "C"
_DEBIT = "D"
_WEEK = "week"


from mcp.models import Parameter
from mcp.models import Cost

PARAM = None
COST = None

try:
    PARAM = Parameter.objects.get(pk="debug")  # default scenario
    COST = {cost.item: cost for cost in PARAM.cost_set.all()}
except:
    raise ()
