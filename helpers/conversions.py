"""
Check caches before converting
"""
import calendar
import time
import itertools
import re
import collections

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
                    ) / refine_item["batch"]

    return calculation


def is_a_number(input_string):
    try:
        float(input_string)
    except ValueError:
        return False
    else:
        return True


def eft_parsing(input_string):
    subsystem = ["Legion", "Tengu", "Proteus", "Loki"]

    split_fit = [x.strip() for x in input_string.splitlines()]
    comma_split_fit = [x.split(",") for x in split_fit[1:] if not x.startswith("[")]
    comma_split_fit = list(itertools.chain(*comma_split_fit))

    multi = re.compile(r"(.*)x([0-9]+$)")
    try:
        ship, fit_name = [x.strip() for x in split_fit[0][1:-1].split(",")]

        # DNA Setup
        ship_fittings = [[], [], [], [], []]
        fit_counter = 0
        subsystem_list = []
        new_slot = False
        subsystem_flag = None
        for split_item in comma_split_fit:
            item_match = re.match(multi, split_item)
            subsystem_check = [split_item.startswith(x) for x in subsystem]
            if not split_item:
                if new_slot:
                    fit_counter += 1
                    fit_counter = min(fit_counter, 4)
                    new_slot = False
                if subsystem_flag:
                    subsystem_flag = False
            elif any(subsystem_check):
                if subsystem_flag is None or subsystem_flag:
                    subsystem_flag = True
                    subsystem_list.append(split_item.strip())
            elif item_match:
                new_slot = True
                item_match_name = item_match.group(1).strip()
                # noinspection PyTypeChecker
                ship_fittings[fit_counter].append(item_match_name)
            else:
                new_slot = True
                ship_fittings[fit_counter].append(split_item)
        ship_fittings[0], ship_fittings[2] = ship_fittings[2], ship_fittings[0]
        ship_fittings = subsystem_list + [x.strip() for x in list(itertools.chain(*ship_fittings))]
        dna_fittings = []
        for ship_fit in ship_fittings:
            if ship_fit not in dna_fittings:
                dna_fittings.append(ship_fit)

        clean_split_fit = [ship] + [x.split(",")[0].strip() for x in comma_split_fit
                                    if x and not re.match(multi, x)]
        item_counter = collections.Counter(clean_split_fit)
        for item in comma_split_fit:
            multiple_item = re.match(multi, item)
            if multiple_item:
                item_counter[multiple_item.group(1).strip()] += int(multiple_item.group(2))
    except (IndexError, ValueError):
        return None, None, None, None

    # DNA Parsing
    fit_db_ids = g.mongo.db.items.find({"name": {"$in": [ship] + subsystem_list + dna_fittings}})
    name_id_conversion = {}
    for db_item in fit_db_ids:
        name_id_conversion[db_item["name"]] = db_item["_id"]
    dna_string_list = [str(name_id_conversion[ship])]
    for item in dna_fittings:
        dna_string_list.append(str(name_id_conversion[item]) + ";" + str(item_counter[item]))
    dna_string = ":".join(dna_string_list) + "::"

    return fit_name, ship, item_counter, dna_string
