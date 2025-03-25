import csv
import matplotlib.pyplot as plt
import yaml
from random import randint
import numpy as np
import matplotlib.pyplot as plt


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
size_factor = 4000
with open('../config/test_map-dev.csv','r') as csvfile:
    plots = csv.reader(csvfile, delimiter=',')
    for row in plots:

        ore_id = row[0]
        x = np.pi * (i % cols)/cols/4
        y = i // cols

        if ore_id == "X":
            X1.append(x)
            Y1.append(y)
            Z1.append((int(row[1]) + 1)/size_factor)
        else:
            X2.append(x)
            Y2.append(y)
            Z2.append((int(row[1]) + 1)/size_factor)
        i += 1

# use the scatter function
# plt.figure(figsize=(18,6))
# plt.scatter(X1, Y1, Z1, alpha=0.5, color="blue")
# plt.scatter(X2, Y2, Z2, alpha=0.5, color="red")
# plt.show()

"""
==========================
Scatter plot on polar axis
==========================

Size increases radially in this example and color increases with angle
(just to verify the symbols are being scattered correctly).
"""


# Fixing random state for reproducibility
# np.random.seed(19680801)

# # Compute areas and colors
# N = 150
# r = 2 * np.random.rand(N)
# theta = 2 * np.pi * np.random.rand(N)
# dia = 200 * r**2
# colors = theta


fig = plt.figure()
ax = fig.add_subplot(111, polar=True)
#c = ax.scatter(theta, r, s=dia, alpha=0.75)
c = ax.scatter(X1, Y1, s=Z1, alpha=0.5, color="blue")
c = ax.scatter(X2, Y2, s=Z2, alpha=0.5, color="red")

ax.set_rorigin(-100)
ax.set_thetamin(0)
ax.set_thetamax(45)

plt.show()
