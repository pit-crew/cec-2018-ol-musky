import matplotlib.pyplot as plt
from math import sin, cos, ceil
import yaml
 
with open("../config/mcp.yaml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
    consts = cfg["constants"]
    lifetime = int(consts["lifetime"]) 

def get_market_report(week):
    X = ceil(rpt_X(team.week) * 100) / 100
    Y = ceil(rpt_Y(team.week) * 100) / 100
    # X = 4.5
    # Y = 4.5
    return {"week": team.week, "prices": {"X": X, "Y": Y}, "status": 0}

# helper stuff for market report
rad = 3.14 / 180


def rpt_X(week):
    return 6 + (sin(5 * week * rad) + cos(2 * week * rad) + sin(week / 10 * rad) - 1.55) * (5 / 3.989)


def rpt_Y(week):
    return 8 + (cos(3 * week * rad) + cos(7 * week * rad) + sin(week / 10 * rad) - 1.60) * (5 / 4.278)


X = [ceil(rpt_X(i)*100)/100 for i in range(lifetime)]
Y = [ceil(rpt_Y(i)*100)/100 for i in range(lifetime)]

x = list(range(len(X)))
plt.plot(x, X)
plt.plot(x, Y)
plt.show()
