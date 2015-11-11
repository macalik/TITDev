import json
import time
from itertools import chain
import re
import math

from flask import Blueprint, render_template, g, request, session, redirect, url_for, abort

from bson.objectid import ObjectId
import bson.errors

from views.auth import requires_sso
from helpers import conversions, eve_central, caches

buyback = Blueprint("buyback", __name__, template_folder="templates")


def price_calc(names, character_id, jf_rate=0):
    item_list = g.mongo.db.items.find({"name": {"$in": names}})
    id_list = g.mongo.db.items.find({"name": {"$in": names}}).distinct("_id")

    mineral_list = {}
    item_materials = conversions.refine_calc(id_list, character_id)
    material_id_list = set()
    non_refine_list = []
    for item in item_list:
        if item["materials"] and (not item["meta"] or item["meta"] < 4):
            for material_id, material_amount in item_materials[item["_id"]].items():
                material_id_list.add(material_id)
                mineral_list.setdefault(material_id, 0)
                mineral_list[material_id] += material_amount
        else:
            item_materials[item["_id"]] = {}
            non_refine_list.append(item["_id"])
    market_prices, prices_usable = eve_central.market_hub_prices(list(mineral_list.keys()) +
                                                                 list(item_materials.keys()) +
                                                                 non_refine_list)

    # Material info for volume
    material_info_db = g.mongo.db.items.find({"_id": {"$in": list(material_id_list)}})
    material_volumes = {}
    for material_info in material_info_db:
        material_volumes[material_info["_id"]] = material_info.get("volume", 0)

    # Tax Checks
    taxes_list = g.mongo.db.taxes.find({"_id": {"$in": list(item_materials.keys()) + non_refine_list}})
    tax_definition = {}
    for tax_item in taxes_list:
        tax_definition[tax_item["_id"]] = tax_item["tax"]
    refine_preferences = g.mongo.db.preferences.find_one({"_id": "buyback_yield"})
    if refine_preferences:
        default_tax = refine_preferences.get("tax", 0)
        default_refine_tax = refine_preferences.get("tax_refine", 0)
    else:
        default_tax = 0
        default_refine_tax = 0

    # Refined Calculations
    calculations = {}
    for key, value in item_materials.items():
        item_cost = 0
        volume = 0
        for material_id, material_amount in value.items():
            item_cost += material_amount * market_prices[material_id]["buy"]
            volume += material_amount * material_volumes[material_id]
        jf_price = jf_rate * volume
        calculations[key] = {"total": item_cost * (1 - tax_definition.get(key, default_refine_tax) / 100),
                             "no_tax": item_cost,
                             "sell": market_prices[key]["sell"],
                             "buy": market_prices[key]["buy"],
                             "volume": volume,
                             "jf_price": jf_price,
                             "delta_sell": item_cost - (market_prices[key]["sell"] - jf_price),
                             "delta_buy": item_cost - (market_prices[key]["buy"] - jf_price),
                             "tax": tax_definition.get(key, default_refine_tax)}

    # Info for non-refined
    non_refine_info_db = g.mongo.db.items.find({"_id": {"$in": non_refine_list}})

    # Non-refined modules
    for non_refine_item in non_refine_info_db:
        calculations[non_refine_item["_id"]] = {
            "total": market_prices[non_refine_item["_id"]]["buy"] * (
                1 - tax_definition.get(non_refine_item["_id"], default_tax) / 100),
            "no_tax": market_prices[non_refine_item["_id"]]["buy"],
            "sell": market_prices[non_refine_item["_id"]]["sell"],
            "buy": market_prices[non_refine_item["_id"]]["buy"],
            "volume": non_refine_item["volume"],
            "jf_price": non_refine_item["volume"] * jf_rate,
            "delta_sell": item_cost - (market_prices[non_refine_item["_id"]]["sell"] - jf_price),
            "delta_buy": item_cost - (market_prices[non_refine_item["_id"]]["buy"] - jf_price),
            "tax": tax_definition.get(non_refine_item["_id"], default_tax)
        }

    mineral_prices = {}
    for mineral in mineral_list.keys():
        mineral_prices[mineral] = market_prices[mineral]

    return calculations, mineral_prices, item_materials, prices_usable


@buyback.route("/", methods=["GET", "POST"])
def home():
    prices_usable = True
    quote_ran = False
    error_id = request.args.get("error_id")
    if not error_id:
        error_list = []
    else:
        error_list = ["Quote of id '{}' cannot be found. It's probably really old.".format(error_id)]

    if request.method == "POST":
        quote_ran = True
        with open("configs/base.json", "r") as base_config_file:
            base_config = json.load(base_config_file)

        # JF Calculations
        hub_to_home = base_config["market_hub_station"] * 100000000 + base_config["home_station"]
        selected_route_info = g.mongo.db.jf_routes.find_one({"_id": hub_to_home})
        if selected_route_info:
            rate_info = conversions.valid_value(selected_route_info["prices"], time.time())
            if session.get("UI_Corporation"):
                jf_rate = rate_info["corp"]
            else:
                jf_rate = rate_info["general"]
        else:
            jf_rate = 0

        # Parsing
        item_names = [x.split("\t")[0].strip() if x.find("\t") != -1
                      else (" ".join(x.split(" ")[:-1]).strip() if conversions.is_a_number(x.split(" ")[-1])
                            else x.strip())
                      for x in request.form.get("input").splitlines()]
        item_input = [re.compile("^" + x.split("\t")[0].strip() + "$", re.IGNORECASE) if x.find("\t") != -1
                      else re.compile("^" + " ".join(x.split(" ")[:-1]).strip() + "$"
                                      if conversions.is_a_number(x.split(" ")[-1]) else
                                      "^" + x.strip() + "$", re.IGNORECASE)
                      for x in request.form.get("input").splitlines()]
        item_qty = {}
        for input_line in request.form.get("input").splitlines():
            try:
                if input_line.find("\t") != -1:
                    input_split = [y.strip() for y in input_line.split("\t")]
                elif conversions.is_a_number(input_line.split(" ")[-1]):
                    input_split = [" ".join(input_line.split(" ")[:-1]).strip(), input_line.split(" ")[-1]]
                else:
                    input_split = [input_line.strip(), "1"]
                item_qty.setdefault(input_split[0].upper(), 0)
                try:
                    qty_clean = int(input_split[1].strip().replace(",", "")) if len(input_split) > 1 else 1
                except ValueError:
                    qty_clean = int(input_split[2].strip().replace(",", "")) if len(input_split) > 2 else 1
                item_qty[input_split[0].upper()] += qty_clean
            except (IndexError, ValueError):
                error_list.append("The line '{}' could not be processed.".format(input_line))

        refine_character = g.mongo.db.preferences.find_one({"_id": "refine_character"})
        if refine_character:
            refine_id = refine_character["character_id"]
        else:
            refine_id = 0
        item_prices, material_prices_list, item_materials, prices_usable = price_calc(item_input, refine_id, jf_rate)
        item_list = g.mongo.db.items.find({"name": {"$in": item_input}})

        # Headers
        material_id_list = list(set(chain(*[x.keys() for x in item_materials.values()])))
        material_name_db = g.mongo.db.items.find({"_id": {"$in": material_id_list}})
        material_header = []
        for material_name in material_name_db:
            material_header.append((material_name["_id"], material_name["name"]))
        material_header.sort(key=lambda x: x[0])
        item_table = [["Name", "Qty"] + [x[1] for x in material_header]]
        price_table = [[
            "Name",
            "Qty",
            "Our Price / Item",
            "Tax %",
            "No Tax",
            base_config["market_hub_name"] + " buy",
            base_config["market_hub_name"] + " sell",
            "Volume",
            "JF Price",
            "Sub Total"
        ]]

        # Items
        total_price = 0
        total_buy_delta = 0
        total_sell_delta = 0
        parsed_item_list = []
        for output_item in item_list:
            parsed_item_list.append(output_item["name"].upper())

            jf_price = output_item["volume"] * jf_rate

            # Deltas
            buy_delta = item_prices[output_item["_id"]]["total"] - (item_prices[output_item["_id"]]["buy"] - jf_price)
            sell_delta = item_prices[output_item["_id"]]["total"] - (item_prices[output_item["_id"]]["sell"] - jf_price)

            total_price += item_prices[output_item["_id"]]["total"] * item_qty[output_item["name"].upper()]
            total_buy_delta += buy_delta * item_qty[output_item["name"].upper()]
            total_sell_delta += sell_delta * item_qty[output_item["name"].upper()]

            materials_row = [math.floor(item_materials[output_item["_id"]].get(x[0], 0) *
                                        item_qty[output_item["name"].upper()])
                             for x in material_header]
            # noinspection PyTypeChecker
            item_table.append([output_item["name"], item_qty[output_item["name"].upper()]] + materials_row)
            price_table.append([
                output_item["name"],
                item_qty[output_item["name"].upper()],
                item_prices[output_item["_id"]]["total"],
                item_prices[output_item["_id"]]["tax"],
                item_prices[output_item["_id"]]["no_tax"],
                item_prices[output_item["_id"]]["buy"],
                item_prices[output_item["_id"]]["sell"],
                output_item["volume"],
                jf_price,
                item_prices[output_item["_id"]]["total"] * item_qty[output_item["name"].upper()]
            ])

        # Check if all items parsed
        for item in item_names:
            if item.upper() not in parsed_item_list:
                error_list.append("The item '{}' could not be found.".format(item))

        # Materials
        material_table = [["Name", base_config["market_hub_name"] + " buy", base_config["market_hub_name"] + " sell"]]
        for material_id, material_name in material_header:
            material_table.append([material_name, material_prices_list[material_id]["buy"],
                                   material_prices_list[material_id]["sell"]])

        # Formatting
        item_table = [item_table[0]] + [row[:1] + ["{:,.02f}".format(value) for value in row[1:]]
                                        for row in item_table[1:]]
        price_table = [price_table[0]] + [row[:2] + ["{:,.02f}".format(value) for value in row[2:]]
                                          for row in price_table[1:]]
        material_table = [material_table[0]] + [row[:1] + ["{:,.02f}".format(value) for value in row[1:]]
                                                for row in material_table[1:]]
        total_buy_delta = "{:,.02f}".format(total_buy_delta)
        total_sell_delta = "{:,.02f}".format(total_sell_delta)
        if total_price < 100000:
            total_price = "{:,.02f}".format(total_price)
        else:
            total_price = "{:,.02f}".format(round(total_price + 50000, -5))

        # GUI Tables
        quick_table = [x[:3] + [x[-1]] for x in price_table]

        # Quote Saving
        quote_id = g.mongo.db.buyback_quotes.insert({
            "item_table": item_table,
            "price_table": price_table,
            "material_table": material_table,
            "total_buy_delta": total_buy_delta,
            "total_sell_delta": total_sell_delta,
            "total_price": total_price,
            "quick_table": quick_table,
            "date_added": time.time()
        })
    else:
        item_table = []
        price_table = []
        material_table = []
        total_buy_delta = 0
        total_sell_delta = 0
        total_price = 0
        quick_table = []
        quote_id = 0

    # Quote Saving
    if request.method == "GET" and request.args.get("action") == "quote":
        return redirect(url_for("buyback.quote", quote_id=request.args.get("quote_id", "0")))

    return render_template("buyback.html", item_table=item_table, price_table=price_table,
                           material_table=material_table, total_buy_delta=total_buy_delta,
                           total_sell_delta=total_sell_delta, total_price=total_price,
                           quick_table=quick_table, error_list=error_list, quote=quote_ran, quote_id=quote_id,
                           prices_usable=prices_usable)


@buyback.route("/quote/<quote_id>")
def quote(quote_id):
    if not quote_id:
        abort(404)

    selected_quote = None
    try:
        selected_quote = g.mongo.db.buyback_quotes.find_one({"_id": ObjectId(quote_id)})
    except bson.errors.InvalidId:
        abort(404)

    if not selected_quote:
        return redirect(url_for("buyback.home", error_id=quote_id))

    item_table = selected_quote["item_table"]
    price_table = selected_quote["price_table"]
    material_table = selected_quote["material_table"]
    total_buy_delta = selected_quote["total_buy_delta"]
    total_sell_delta = selected_quote["total_sell_delta"]
    total_price = selected_quote["total_price"]
    quick_table = selected_quote["quick_table"]
    date_added = selected_quote["date_added"]

    # Formatting
    date_added_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(date_added)) + " UTC"

    return render_template("buyback_quote.html", item_table=item_table, price_table=price_table,
                           material_table=material_table, total_buy_delta=total_buy_delta,
                           total_sell_delta=total_sell_delta, total_price=total_price,
                           quick_table=quick_table, date_added_str=date_added_str, quote_id=quote_id)


@buyback.route("/admin", methods=["GET", "POST"])
@requires_sso("buyback_admin")
def admin():
    # # Settings
    refine_character = g.mongo.db.preferences.find_one({"_id": "refine_character"})

    if request.method == "POST":
        if request.form.get("action") == "refresh_character":
            caches.character_sheet([[refine_character["key_id"], refine_character["vcode"],
                                     refine_character["character_id"]]])
        elif request.form.get("action") == "general_settings":
            current_settings = g.mongo.db.preferences.find_one({"_id": "buyback_yield"})
            if not current_settings:
                current_settings = {}
            g.mongo.db.preferences.update({"_id": "buyback_yield"}, {
                "base": float(request.form.get("general_base")) if request.form.get("general_base")
                else current_settings.get("base", 0),
                "implant": float(request.form.get("general_implant")) if request.form.get("general_implant")
                else current_settings.get("implant", 0),
                "tax": float(request.form.get("general_tax")) if request.form.get("general_tax")
                else current_settings.get("tax", 0),
                "tax_refine": float(request.form.get("general_refine")) if request.form.get("general_refine")
                else current_settings.get("tax_refine", 0)
            }, upsert=True)
        elif request.form.get("action") == "specific_settings":
            db_item = g.mongo.db.items.find_one({"name": request.form.get("name").strip()})
            current_settings = g.mongo.db.taxes.find_one({"_id": db_item["_id"]})
            if not current_settings:
                current_settings = {}
            if db_item:
                g.mongo.db.taxes.update({"_id": db_item["_id"]}, {
                    "name": request.form.get("name").strip(),
                    "base": float(request.form.get("specific_base")) if request.form.get("specific_base")
                    else current_settings.get("base", 0),
                    "implant": float(request.form.get("specific_implant")) if request.form.get("specific_implant")
                    else current_settings.get("implant", 0),
                    "tax": float(request.form.get("specific_tax")) if request.form.get("specific_tax")
                    else current_settings.get("tax", 0),
                    "tax_refine": float(request.form.get("specific_refine")) if request.form.get("specific_refine")
                    else current_settings.get("tax_refine", 0)
                }, upsert=True)
        elif request.form.get("delete"):
            g.mongo.db.taxes.remove({"_id": int(request.form.get("delete"))})

    # Specific Rates Table
    specific_rates_table = [["Name", "Base", "Implant", "Tax", "Action"]]
    specific_rates_db = g.mongo.db.taxes.find()
    for rate in specific_rates_db:
        specific_rates_table.append([rate["name"], rate["base"], rate["implant"], rate["tax"], rate["_id"]])

    general_rates = g.mongo.db.preferences.find_one({"_id": "buyback_yield"})
    if general_rates:
        general_base = "{:,.02f}".format(general_rates["base"])
        general_implant = "{:,.02f}".format(general_rates["implant"])
        general_tax = "{:,.02f}".format(general_rates["tax"])
        general_refine = "{:,.02f}".format(general_rates["tax_refine"])
    else:
        general_base = 0
        general_implant = 0
        general_tax = 0
        general_refine = 0

    character_list = []
    current_user = g.mongo.db.api_keys.find_one({"_id": session["CharacterOwnerHash"]})
    # Set Refine Character
    current_refine_character = refine_character["character_name"] if refine_character else None
    if current_user:
        for key in current_user["keys"]:
            selected = False
            if request.method == "POST" and request.form.get("action") == "refine_character":
                if request.form.get("character") and key["character_id"] == int(request.form.get("character")):
                    selected = True
                    current_refine_character = key["character_name"]
                    g.mongo.db.preferences.update({"_id": "refine_character"}, {
                        "key_id": key["key_id"],
                        "vcode": key["vcode"],
                        "character_id": key["character_id"],
                        "character_name": key["character_name"]
                    }, upsert=True)
                    caches.character_sheet([[key["key_id"], key["vcode"], key["character_id"]]])
            elif refine_character and refine_character["character_id"] == key["character_id"]:
                # Fix front end view
                selected = True
            character_list.append([key["character_id"], key["character_name"], selected])

    # # Refine Quick-Look
    with open("configs/definitions.json") as groups_file:
        groups_definitions = json.load(groups_file)
    ore_market_group_ids = groups_definitions["ore_market_group_ids"]
    ice_market_group_ids = groups_definitions["ice_market_group_ids"]

    material_list = g.mongo.db.items.find({"market_group_id": {
        "$in": ore_market_group_ids + ice_market_group_ids
    }}).distinct("materials.type_id")
    material_db = g.mongo.db.items.find({"_id": {"$in": material_list}})
    ice_material_list = g.mongo.db.items.find({"market_group_id": {
        "$in": ice_market_group_ids
    }}).distinct("materials.type_id")
    ice_material_groups = g.mongo.db.items.find({"_id": {"$in": ice_material_list}}).distinct("market_group_id")
    refine_quick = g.mongo.db.items.find({"market_group_id": {"$in": ore_market_group_ids + ice_market_group_ids}})
    refine_quick_ids = g.mongo.db.items.find({"market_group_id": {
        "$in": ore_market_group_ids + ice_market_group_ids}}).distinct("_id")

    material_conversion = {}
    ore_headers = []
    ice_headers = []
    for material in material_db:
        material_conversion[material["_id"]] = material["name"]
        if material["market_group_id"] in ice_material_groups:
            ice_headers.append((material["_id"], material["name"]))
        else:
            ore_headers.append((material["_id"], material["name"]))
    ore_headers.sort(key=lambda x: x[0])
    ice_headers.sort(key=lambda x: x[0])

    refine_character = g.mongo.db.preferences.find_one({"_id": "refine_character"})
    if refine_character:
        refine_id = refine_character["character_id"]
    else:
        refine_id = 0
    character_refines = conversions.refine_calc(refine_quick_ids, refine_id)

    ore_table = []
    ice_table = []
    for item in refine_quick:
        qty = {}
        row = [item["name"]]
        for material in item["materials"]:
            qty[material["type_id"]] = material["amount"]
        if item["market_group_id"] == 1855:  # Ice
            for header in ice_headers:
                row.append(character_refines[item["_id"]].get(header[0], 0))
            ice_table.append(row)
        else:
            for header in ore_headers:
                row.append(character_refines[item["_id"]].get(header[0], 0))
            ore_table.append(row)

    # Formatting
    ore_table = [["Name"] + [x[1] for x in ore_headers]] + [
        ["{:,.02f}".format(value) if not isinstance(value, str) else value for value in row] for row in ore_table]
    ice_table = [["Name"] + [x[1] for x in ice_headers]] + [
        ["{:,.02f}".format(value) if not isinstance(value, str) else value for value in row] for row in ice_table]

    return render_template("buyback_admin.html", ore_table=ore_table, ice_table=ice_table,
                           character_list=character_list, refine_character=current_refine_character,
                           general_base=general_base, general_implant=general_implant,
                           general_tax=general_tax, specific_rates_table=specific_rates_table,
                           general_refine=general_refine)
