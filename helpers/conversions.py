"""
Check caches before converting
"""

from flask import g


def station(station_id):
    db_station = g.mongo.db.stations.find_one({"_id": station_id})
    if not db_station:
        db_station = g.staStations[str(station_id)]
    else:
        db_station = db_station["name"]

    return db_station


def character(character_id):
    db_character = g.mongo.db.characters.find_one({"_id": character_id})
    db_character = db_character["name"] if db_character else ""

    # Fix "N/A" characters
    if db_character == "Unknown Item":
        db_character = "None"

    return db_character
