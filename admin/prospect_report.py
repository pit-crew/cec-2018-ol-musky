import csv
import matplotlib.pyplot as plt
import yaml
from random import randint

with open("../config/mcp.yaml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
    belt = cfg["belt"]
    rows=int(belt["rows"]) 
    cols=int(belt["cols"])
    consts = cfg["constants"]
    prospecting_offset = int(belt["prospecting_offset"])
    lifetime = int(consts["lifetime"])

colors = ["blue", "yellow", "magenta", "cyan", "black", "green", "white"]

i = 0
with open('../config/test_map-dev.csv','r') as csvfile:
    belt_data = csv.reader(csvfile, delimiter=',')

    belt = []
    for row in belt_data:
        belt.append((row[0], row[1]))

    for offset in range(0,1):
        X = []
        Y = []
        Z = []

        max_deposit = 97991
        err = float(max_deposit)//6.5  # +/- 15% error

        p_report = {}

        for i in range(offset, cols * rows, prospecting_offset):
            val = int(belt_data[i][1])
            est = val
            if(val > 0):
                est = max(0, randint(-err, err) + est)

            ore_id = belt_data[i][0]
            x = i % cols
            y = i // cols

            X.append(x)
            Y.append(y)
            Z.append(est/2000)

    #         if ore_id == "X":
    #             X1.append(x)
    #             Y1.append(y)
    #             Z1.append((int(row[1]) + 1)/300)
    #         else:
    #             X2.append(x)
    #             Y2.append(y)
    #             Z2.append((int(row[1]) + 1)/300)
    #         i += 1

        # use the scatter function
        plt.scatter(X, Y, Z, alpha=0.2, color=colors[offset])
        # plt.scatter(X1, Y1, Z1, alpha=0.5, color="blue")
        # plt.scatter(X2, Y2, Z2, alpha=0.5, color="red")
    plt.show()
