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
connection.text_factory = lambda x: str(x, 'iso-8859-1')
cursor = connection.cursor()

stations = {}
marketable_items = {}

for row in cursor.execute("SELECT stationID, stationName FROM staStations"):
    stations[int(row[0])] = row[1]

for row in cursor.execute("select typeID, typeName, volume from invTypes where marketGroupID not null"):
    marketable_items[int(row[0])] = {"name": row[1], "volume": row[2]}

with open("staStations.json", "w") as stations_file:
    json.dump(stations, stations_file, sort_keys=True, indent=4, separators=(',', ': '))
with open("../static/staStations.json", "w") as static_file:
    json.dump(stations, static_file, sort_keys=True, indent=4, separators=(',', ': '))
with open("invTypes.json", "w") as types_file:
    json.dump(marketable_items, types_file, sort_keys=True, indent=4, separators=(',', ': '))
