import json
import time

from flask import Blueprint, render_template, request, g, redirect, url_for, session, abort

from bson.objectid import ObjectId
import bson.errors

from views.auth import requires_sso, auth_check
from helpers import eve_central, conversions

fittings = Blueprint("fittings", __name__, template_folder="templates")


@fittings.route("/", methods=["GET", "POST"])
@requires_sso("alliance")
def home():
    dna_string = None
    error_string = None

    # Check if fittings admin
    admin = auth_check("fittings_admin")

    if request.args.get("error"):
        if request.args.get("error") == "parsing":
            error_string = "Could not parse the EFT-Formatted fit. Please ensure it is correctly formatted."
        elif request.args.get("error") == "not_found":
            error_string = "Could not find the fit. It may have been deleted."

    if request.method == "POST" and request.form.get("action") == "fit_submit":
        if not request.form.get("fit_string"):
            return redirect(url_for("fittings.home"))

        fit_name, ship, item_counter, dna_string = conversions.eft_parsing(request.form.get("fit_string"))

        if not fit_name:  # Error in parsing
            return redirect(url_for("fittings.home", error="parsing"))

        fit_id = g.mongo.db.fittings.insert({
            "fit": request.form.get("fit_string"),
            "items": item_counter,
            "submitter": session["CharacterOwnerHash"],
            "price": 0,
            "volume": 0,
            "name": fit_name,
            "notes": request.form.get("notes"),
            "dna": dna_string,
            "ship": ship,
            "source": request.form.get("source"),
            "doctrine": True if request.form.get("doctrine") and admin else False
        })

        return redirect(url_for("fittings.fit", fit_id=fit_id))
    elif request.method == "POST" and request.form.get("action") == "direct_to_cart":
        session["fitting"] = request.form.get("fit_string")
        return redirect(url_for("ordering.home"))

    # Fit Listings

    all_fittings = g.mongo.db.fittings.find()
    user_corporation = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})["corporation_name"]

    header = ["Name", "Ship", "Submitter", "Price", "Volume", "Notes", "Action"]
    personal_fits = [header]
    doctrine_fits = [header]
    corporation_fits = [header]
    alliance_fits = [header]
    all_fits = [header]
    packs = [header]
    for db_fit in all_fittings:
        submitter = g.mongo.db.users.find_one({"_id": db_fit["submitter"]})
        # Delete Check
        can_delete = False
        if submitter["_id"] == session["CharacterOwnerHash"] or auth_check("fittings_admin"):
            can_delete = True

        fit_info = [db_fit["name"], db_fit["ship"], submitter["character_name"],
                    "{:,.02f}".format(db_fit["price"]), "{:,.02f}".format(db_fit["volume"]), db_fit["notes"],
                    can_delete, str(db_fit["_id"]), db_fit["dna"]]
        if db_fit.get("doctrine"):
            doctrine_fits.append(fit_info)
        elif db_fit["submitter"] == session["CharacterOwnerHash"]:
            personal_fits.append(fit_info)
        elif submitter["corporation_name"] == user_corporation:
            corporation_fits.append(fit_info)
        else:
            alliance_fits.append(fit_info)

        if db_fit["ship"] == "Pack":
            packs.append(fit_info)
        else:
            all_fits.append(fit_info)

    return render_template("fittings.html", doctrine_fits=doctrine_fits, corporation_fits=corporation_fits,
                           alliance_fits=alliance_fits, dna_string=dna_string, personal_fits=personal_fits,
                           all_fits=all_fits, error_string=error_string, admin=admin, packs=packs)


@fittings.route("/fit/<fit_id>", methods=["GET", "POST"])
@requires_sso("alliance")
def fit(fit_id=None):
    if not fit_id:
        abort(404)

    # Redirect if fit is purchased
    if request.method == "GET" and request.args.get("action") == "purchase":
        return redirect(url_for("ordering.home", item=fit_id + ";" + request.args.get("multiply", 1)))

    selected_fit = None
    try:
        selected_fit = g.mongo.db.fittings.find_one({"_id": ObjectId(fit_id)})
    except bson.errors.InvalidId:
        abort(404)

    if not selected_fit:
        return redirect(url_for("fittings.home", error="not_found"))
    elif request.method == "GET" and request.args.get("action") == "direct":
        # Use direct to cart
        session["fitting"] = selected_fit["fit"]
        return redirect(url_for("ordering.home"))

    # Check if fittings admin
    admin = auth_check("fittings_admin")

    # Delete Permissions
    if selected_fit["submitter"] == session["CharacterOwnerHash"] or admin:
        can_delete = True
    else:
        can_delete = False

    # Modifications
    notes_change = request.args.get("notes") if request.args.get("notes") else selected_fit["notes"]
    source_change = request.args.get("source") if request.args.get("source") else selected_fit.get("source")
    doctrine_change = bool(request.args.get("doctrine")) if request.args.get("doctrine") else False
    if request.args.get("action") == "delete" and can_delete:
        g.mongo.db.fittings.remove({"_id": ObjectId(fit_id)})
        return redirect(url_for("fittings.home"))
    elif request.args.get("action") == "edit" and can_delete:
        g.mongo.db.fittings.update({"_id": ObjectId(fit_id)},
                                   {"$set": {
                                       "notes": notes_change,
                                       "source": source_change,
                                       "doctrine": doctrine_change
                                   }})
        return redirect(url_for("fittings.fit", fit_id=fit_id))

    fit_by_line = selected_fit["fit"].splitlines()

    # ID Matching
    item_list = list(g.mongo.db.items.find({"name": {"$in": list(selected_fit["items"].keys())}}))
    item_prices, prices_usable = eve_central.market_hub_prices([x["_id"] for x in item_list])

    item_table = [["Name", "Qty", "Isk/Item", "Vol/Item", "Total Isk", "Total Volume"]]
    total_fit_isk = 0
    total_volume = 0
    multiply = 1 if not request.args.get("multiply") else int(request.args.get("multiply"))

    for fit_item in item_list:
        qty = selected_fit["items"][fit_item["name"]] * multiply
        isk_per_item = item_prices[fit_item["_id"]]["sell"]
        vol_per_item = fit_item["volume"]
        item_isk_total = qty * isk_per_item
        item_vol_total = qty * vol_per_item
        total_fit_isk += item_isk_total
        total_volume += item_vol_total
        # Formatting
        isk_per_item = "{:,.02f}".format(isk_per_item)
        vol_per_item = "{:,.02f}".format(vol_per_item)
        item_isk_total = "{:,.02f}".format(item_isk_total)
        item_vol_total = "{:,.02f}".format(item_vol_total)
        item_table.append([fit_item["name"], qty, isk_per_item, vol_per_item, item_isk_total, item_vol_total])

    if multiply == 1 and prices_usable:
        g.mongo.db.fittings.update({"_id": ObjectId(fit_id)}, {"$set": {
            "price": total_fit_isk, "volume": total_volume}})

    # List routes
    with open("configs/base.json") as base_config_file:
        base_config = json.load(base_config_file)

    market_hub_name = base_config["market_hub_name"]
    min_id_limit = base_config["market_hub_station"] * 100000000
    max_id_limit = base_config["market_hub_station"] * 100000000 + 100000000
    market_hub_routes = g.mongo.db.jf_routes.find({"_id": {"$gte": min_id_limit, "$lt": max_id_limit}})

    if request.args.get("end"):
        selected_route = int(request.args.get("end"))
    else:
        selected_route = 0

    valid_stations = []
    current_route = g.mongo.db.carts.find_one({"_id": session["CharacterOwnerHash"]})
    for route in market_hub_routes:
        if request.args.get("end") and route["_id"] == int(request.args.get("end")):
            valid_stations.append([route["_id"], route["end"], True])
            g.mongo.db.carts.update({"_id": session["CharacterOwnerHash"]},
                                    {"$set": {"route": route["_id"]}}, upsert=True)
        elif current_route:
            if route["_id"] == current_route.get("route"):
                valid_stations.append([route["_id"], route["end"], True])
                selected_route = route["_id"] if selected_route == 0 else selected_route
            else:
                valid_stations.append([route["_id"], route["end"], False])
        elif not request.args.get("end") and route["end"] == base_config["default_ship_to"]:
            valid_stations.append([route["_id"], route["end"], True])
            g.mongo.db.carts.update({"_id": session["CharacterOwnerHash"]},
                                    {"$set": {"route": route["_id"]}}, upsert=True)
            selected_route = route["_id"] if selected_route == 0 else selected_route
        else:
            valid_stations.append([route["_id"], route["end"], False])

    # JF Calculations
    selected_route_info = g.mongo.db.jf_routes.find_one({"_id": selected_route})
    if selected_route_info:
        rate_info = conversions.valid_value(selected_route_info["prices"], time.time())
        if session.get("UI_Corporation"):
            jf_rate = rate_info["corp"]
        else:
            jf_rate = rate_info["general"]

        jf_total = jf_rate * total_volume
    else:
        jf_rate = 0
        jf_total = 0
    order_total = jf_total + total_fit_isk

    # Formatting
    total_fit_isk = "{:,.02f}".format(total_fit_isk)
    total_volume = "{:,.02f}".format(total_volume)
    jf_total = "{:,.02f}".format(jf_total)
    jf_rate = "{:,.02f}".format(jf_rate)
    order_total = "{:,.02f}".format(order_total)

    return render_template("fittings_fit.html", item_table=item_table, fit_string=fit_by_line,
                           total_fit_isk=total_fit_isk, total_volume=total_volume, valid_stations=valid_stations,
                           market_hub_name=market_hub_name, jf_rate=jf_rate, jf_total=jf_total, order_total=order_total,
                           dna_string=selected_fit["dna"], fit_name=selected_fit["name"], multiply=multiply,
                           can_delete=can_delete, notes=selected_fit["notes"], source=selected_fit.get("source"),
                           admin=admin, doctrine=selected_fit["doctrine"], prices_usable=prices_usable)
