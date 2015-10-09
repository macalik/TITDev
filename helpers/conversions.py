"""
Check caches before converting
"""
import calendar
import time

from flask import g


def character(character_id):
    db_character = g.mongo.db.characters.find_one({"_id": character_id})
    db_character = db_character["name"] if db_character else ""

    # Fix "N/A" characters
    if db_character == "Unknown Item":
        db_character = "None"

    return db_character


def valid_value(history_array, init_time):
    if isinstance(init_time, str):
        xml_time_pattern = "%Y-%m-%d %H:%M:%S"
        current_time = int(calendar.timegm(time.strptime(init_time, xml_time_pattern)))
    else:
        current_time = int(init_time)
    return min(history_array,
               key=lambda x: current_time - x["valid_after"]
               if x["valid_after"] <= current_time else current_time + x["valid_after"])
