import csv
import matplotlib.pyplot as plt
import yaml
from random import randint

with open("../config/mcp.yaml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
    belt = cfg["belt"]
    rows=int(belt["rows"]) 
    cols=int(belt["cols"])
 
X1 = []
X2 = []
Y1 = []
Y2 = []
Z1 = []
Z2 = []

i = 0
with open('../config/test_map-dev.csv','r') as csvfile:
    plots = csv.reader(csvfile, delimiter=',')
    for row in plots:
        ore_id = row[0]
        x = i % cols
        y = i // cols

        if ore_id == "X":
            X1.append(x)
            Y1.append(y)
            Z1.append((int(row[1]) + 1)/300)
        else:
            X2.append(x)
            Y2.append(y)
            Z2.append((int(row[1]) + 1)/300)
        i += 1

# use the scatter function
plt.figure(figsize=(18,6))
plt.scatter(X1, Y1, Z1, alpha=0.2, color="blue")
plt.scatter(X2, Y2, Z2, alpha=0.2, color="red")
plt.show()
