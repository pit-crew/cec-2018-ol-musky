import yaml
import csv
from numpy import correlate

with open("../config/mcp.yaml", 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
    belt = cfg["belt"]
    rows=int(belt["rows"]) 
    cols=int(belt["cols"])


def max_subarray(array, length):
    max_so_far = 0
    best_index = 0

    for i in range(0, len(array) - length):
    	a = array[i:i + length]
   
    	if max_so_far <= sum(a):
    		max_so_far = sum(a)
    		best_index = i
		
    return best_index, max_so_far


if __name__ == "__main__":
    with open('../config/belt_map-dev.csv', 'r') as csvfile:
        sites = csv.reader(csvfile, delimiter=',')
        belt = []
        for site in sites:
            belt.append(int(site[1]))
 
        index, amt = max_subarray(belt, 3*30)
        print(index, amt)
