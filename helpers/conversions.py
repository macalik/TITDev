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


def refine_calc(type_ids, character_id):
    """

    :param type_ids: [id, ...]
    :param character_id: character_id
    :return: calculation[id] = {material_id: amount, ...}
    """
    refine_preferences = g.mongo.db.preferences.find_one({"_id": "buyback_yield"})
    if refine_preferences:
        base = refine_preferences.get("base", 0)  # 0.54
        implant = refine_preferences.get("implant", 0)  # 1.04
    else:
        base = 0
        implant = 0

    refine_query = g.mongo.db.items.find({"_id": {"$in": type_ids},
                                          "materials": {"$exists": True, "$not": {"$size": 0}}})
    refine_character = g.mongo.db.character_sheet.find_one({"_id": character_id})
    if refine_character:
        scrapmetal_processing = refine_character["skills"].get("12196", {}).get("level", 0) * 0.02 + 1
        reprocessing = refine_character["skills"].get("3385", {}).get("level", 0) * 0.03 + 1
        reprocessing_efficiency = refine_character["skills"].get("3389", {}).get("level", 0) * 0.02 + 1
    else:
        refine_character = {}
        scrapmetal_processing = 1
        reprocessing = 1
        reprocessing_efficiency = 1

    tax_query = g.mongo.db.taxes.find({"_id": {"$in": type_ids}})
    base_definition = {}
    implant_definition = {}
    for tax_item in tax_query:
        base_definition[tax_item["_id"]] = tax_item["base"]
        implant_definition[tax_item["_id"]] = tax_item["implant"]

    calculation = {}
    for refine_item in refine_query:
        corrected_base = base_definition.get(refine_item["_id"], base) / 100
        corrected_implant = implant_definition.get(refine_item["_id"], implant) / 100
        calculation[refine_item["_id"]] = {}
        for refine_material in refine_item["materials"]:
            if refine_item["skill_id"]:  # Is an raw ore or ice item
                if not refine_item["name"].startswith("Compressed") and refine_item["market_group_id"] != 1855:
                    batch = 100
                else:
                    batch = 1
                specific_processing = refine_character.get("skills", {}).get(
                    str(refine_item["skill_id"]), {}).get("level", 0) * 0.02 + 1
                if corrected_base == 0:
                    calculation[refine_item["_id"]][refine_material["type_id"]] = refine_material["amount"]
                else:
                    calculation[refine_item["_id"]][refine_material["type_id"]] = refine_material["amount"] * (
                        corrected_base * reprocessing * reprocessing_efficiency * specific_processing
                    ) / batch * (1 + corrected_implant)
            else:
                if corrected_base == 0:
                    calculation[refine_item["_id"]][refine_material["type_id"]] = refine_material["amount"]
                else:
                    calculation[refine_item["_id"]][refine_material["type_id"]] = corrected_base * (
                        refine_material["amount"] * scrapmetal_processing
                    )

    return calculation
