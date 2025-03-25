import random
import bz2
import yaml

from sklearn.datasets.samples_generator import make_blobs
 
with open("../config/mcp.yaml", 'r') as ymlfile:
	cfg = yaml.load(ymlfile)
	belt = cfg["belt"]
	rows=int(belt["rows"]) 
	cols=int(belt["cols"])

ores = ['X','Y','Z']

samples = cols * rows
raw = [None] * samples
indeces = [i for i in range(rows*cols)]
blobs = random.sample(indeces, 9)
centers = []
centers = [[i%cols, i//cols] for i in blobs]
#centers = [[5,25], [15,17], [39, 10], [55,18], [65,7], [75,27], [88,2]]
r, c = zip(*centers)
print(r)
print(c)

import numpy as np
import matplotlib.pyplot as plt
plt.scatter(r, c)
plt.show()

X,Y = make_blobs(n_samples=1800, centers=centers, cluster_std=5.0,random_state=0)

#X, Y = make_blobs(n_samples=samples, n_features=1, centers=centers, cluster_std=1700.0, center_box=(0, 0.0), shuffle=True, random_state=0)


raw = [0] * cols*rows
for coord in X:
    x = int(coord[0])
    y = int(coord[1])
    
    if 0 <= y < rows and 0 <= x < cols:
        sector = y * cols + x
        try:
            raw[sector] = int(random.gauss(0, 20000))
        except:
            print(x, y, "sector", sector)
            break
    
m = min(raw)
print ("min", m)

deposits = [0] * rows*cols
for i in range(len(raw)):
    if raw[i] != 0:
        deposits[i] = raw[i] - m
# m = min(raw)
# print(m, len(raw))
# deposits = [int(d - m) for d in raw]

print(min(deposits), max(deposits))

ore_Y = random.sample(indeces, len(indeces) //10) # 10% will by 'Y'
with open("../config/new_map-dev.csv", "w") as belt_file:
    for i in range(len(deposits)):
        ore_id = "X"
        if i in ore_Y: 
            ore_id = "Y"
        s = f"{ore_id},{deposits[i]}\n"
        belt_file.write (s)
