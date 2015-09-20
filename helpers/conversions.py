"""
Check caches before converting
"""

from flask import g


def character(character_id):
    db_character = g.mongo.db.characters.find_one({"_id": character_id})
    db_character = db_character["name"] if db_character else ""

    # Fix "N/A" characters
    if db_character == "Unknown Item":
        db_character = "None"

    return db_character
