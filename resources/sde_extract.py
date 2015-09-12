import tkinter
from tkinter.filedialog import askopenfilename
import sqlite3
import json

"""
Run this file separately. Extracts needed data from fuzzwork's sde sqlite conversion.
"""
tkinter.Tk().withdraw()
filename = askopenfilename()

connection = sqlite3.connect(filename)
cursor = connection.cursor()

stations = {}

for row in cursor.execute("SELECT stationID, stationName FROM staStations"):
    stations[int(row[0])] = row[1]

with open("staStations.json", "w") as stations_file:
    json.dump(stations, stations_file, sort_keys=True, indent=4, separators=(',', ': '))
with open("../static/staStations.json", "w") as static_file:
    json.dump(stations, static_file, sort_keys=True, indent=4, separators=(',', ': '))
