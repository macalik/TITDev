import json
import time

from flask import Blueprint, render_template, session, g, request, redirect, url_for
from bson.objectid import ObjectId
import bson.errors
import requests

from views.auth import requires_sso
from helpers.eve_central import market_hub_prices
from helpers import conversions

ordering = Blueprint("ordering", __name__, template_folder="templates")


@ordering.route("/")
@ordering.route("/<item>")
@requires_sso("corporation")
def home(item=""):
    cart_item_list = {}

    # Add new item to database
    input_string = request.args.get("parse", session.get("fitting"))
    if item or input_string:
        bulk_op_update = g.mongo.db.carts.initialize_unordered_bulk_op()
        bulk_run_update = False
        if item:
            try:
                item_adjustment_list = item.split(":")
                for adjustment_item in item_adjustment_list:
                    adjustment_item_info = adjustment_item.split(";")
                    if request.args.get("action") == "edit":
                        bulk_op_update.find({"_id": session["CharacterOwnerHash"]}).upsert().update({
                            "$set": {"items." + adjustment_item_info[0]: int(adjustment_item_info[1])}})
                    else:
                        bulk_op_update.find({"_id": session["CharacterOwnerHash"]}).upsert().update({
                            "$inc": {"items." + adjustment_item_info[0]: int(adjustment_item_info[1])}})
                    bulk_run_update = True
            except IndexError:
                error_string = "Was not able to add {}".format(item)
        elif input_string:
            session.pop("fitting", None)
            parse_result = conversions.eft_parsing(input_string)[3]  # DNA String
            if not parse_result:
                return redirect(url_for("ordering.home"))
            parse_item_list = parse_result.split(":")
            for parse_item in parse_item_list:
                if parse_item:
                    direct_info = parse_item.split(";")
                    if len(direct_info) == 1:
                        bulk_op_update.find({"_id": session["CharacterOwnerHash"]}).upsert().update({
                            "$inc": {"items." + direct_info[0]: 1}})
                        bulk_run_update = True
                    else:
                        bulk_op_update.find({"_id": session["CharacterOwnerHash"]}).upsert().update({
                            "$inc": {"items." + direct_info[0]: int(direct_info[1])}})
                        bulk_run_update = True

        if bulk_run_update:
            bulk_op_update.execute()

    # Load cart
    current_cart = g.mongo.db.carts.find_one({"_id": session["CharacterOwnerHash"]})
    if current_cart:
        cart_item_list_pre = current_cart["items"]

        # Filter fittings from items
        fittings_id_list = []
        for cart_item_id, cart_item_qty in cart_item_list_pre.items():
            try:
                fittings_id_list.append(ObjectId(cart_item_id))
            except bson.errors.InvalidId:
                cart_item_list[cart_item_id] = cart_item_qty

        # Unpack fittings
        for selected_fit in g.mongo.db.fittings.find({"_id": {"$in": fittings_id_list}}):
            fit_item_list = selected_fit["dna"].split(":")
            for fit_item in fit_item_list:
                if fit_item:
                    item_info = fit_item.split(";")
                    cart_item_list.setdefault(item_info[0], 0)
                    if len(item_info) == 1:
                        cart_item_list[item_info[0]] += 1 * current_cart["items"][str(selected_fit["_id"])]
                    else:
                        cart_item_list[item_info[0]] += int(item_info[1]) * current_cart["items"][
                            str(selected_fit["_id"])]

    cart_item_list_int = [int(x) for x in cart_item_list.keys()]
    prices, prices_usable = market_hub_prices(cart_item_list_int)

    total_volume = 0
    sell_price = 0
    invoice_info = [["Name", "Qty", "Vol/Item", "Isk/Item", "Vol Subtotal", "Isk Subtotal"]]
    for db_item in g.mongo.db.items.find({"_id": {"$in": cart_item_list_int}}):
        invoice_info.append([
            db_item["_id"],
            db_item["name"],
            cart_item_list[str(db_item["_id"])],
            "{:,.02f}".format(db_item["volume"]),
            "{:,.02f}".format(prices[db_item["_id"]]["sell"]),
            "{:,.02f}".format(db_item["volume"] * cart_item_list[str(db_item["_id"])]),
            "{:,.02f}".format(prices[db_item["_id"]]["sell"] * cart_item_list[str(db_item["_id"])])
        ])
        total_volume += db_item["volume"] * cart_item_list[str(db_item["_id"])]
        sell_price += prices[db_item["_id"]]["sell"] * cart_item_list[str(db_item["_id"])]

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
    for route in market_hub_routes:
        if request.args.get("end") and route["_id"] == int(request.args.get("end")):
            valid_stations.append([route["_id"], route["end"], True])
        elif not request.args.get("end") and route["end"] == base_config["default_ship_to"]:
            valid_stations.append([route["_id"], route["end"], True])
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

    order_total = jf_total + sell_price

    # Formatting
    total_volume = "{:,.02f}".format(total_volume)
    sell_price = "{:,.02f}".format(sell_price)
    jf_total = "{:,.02f}".format(jf_total)
    order_total = "{:,.02f}".format(order_total)

    return render_template("ordering.html", invoice_info=invoice_info, total_volume=total_volume,
                           sell_price=sell_price, valid_stations=valid_stations, jf_rate=jf_rate,
                           jf_total=jf_total, order_total=order_total, market_hub_name=market_hub_name,
                           prices_usable=prices_usable)
