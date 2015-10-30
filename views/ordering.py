import json
import time
import re

from flask import Blueprint, render_template, session, g, request, redirect, url_for

from bson.objectid import ObjectId
import bson.errors
import requests

from views.auth import requires_sso
from helpers.eve_central import market_hub_prices
from helpers import conversions

ordering = Blueprint("ordering", __name__, template_folder="templates")


@ordering.route("/", methods=["GET", "POST"])
@ordering.route("/<item>", methods=["GET", "POST"])
@requires_sso("corporation")
def home(item=""):
    cart_item_list = {}
    error_string = None

    bulk_op_update = g.mongo.db.carts.initialize_unordered_bulk_op()
    bulk_run_update = False

    # Change qty if post from this page
    if request.method == "POST" and request.form.get("action") == "qty":
        for key, value in request.form.items():
            if key != "action" and not key.startswith("DataTables"):
                if int(float(value)) != 0:
                    bulk_op_update.find({"_id": session["CharacterOwnerHash"]}).upsert().update({
                        "$set": {"items." + key: int(float(value))}})
                else:
                    bulk_op_update.find({"_id": session["CharacterOwnerHash"]}).upsert().update({
                        "$unset": {"items." + key: int(float(value))}})
                bulk_run_update = True
    if request.method == "POST" and request.form.get("action") == "clear":
        g.mongo.db.carts.remove({"_id": session["CharacterOwnerHash"]})

    # Add new item to database
    input_string = request.form.get("parse", session.get("fitting"))
    if item or input_string:
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

    if item or input_string:
        return redirect(url_for("ordering.home"))

    # Load cart
    total_volume = 0
    sell_price = 0
    current_cart = g.mongo.db.carts.find_one({"_id": session["CharacterOwnerHash"]})
    fittings_info = []
    fittings_breakdown = {}
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
            fittings_info.append([str(selected_fit["_id"]),
                                  "[Fit] " + selected_fit["name"],
                                  current_cart["items"][str(selected_fit["_id"])],
                                  "{:,.02f}".format(selected_fit["volume"]),
                                  "{:,.02f}".format(selected_fit["price"]),
                                  "{:,.02f}".format(selected_fit["volume"] *
                                                    current_cart["items"][str(selected_fit["_id"])]),
                                  "{:,.02f}".format(selected_fit["price"] *
                                                    current_cart["items"][str(selected_fit["_id"])])
                                  ])
            total_volume += selected_fit["volume"] * current_cart["items"][str(selected_fit["_id"])]
            sell_price += selected_fit["price"] * current_cart["items"][str(selected_fit["_id"])]
            for fit_item in fit_item_list:
                if fit_item:
                    item_info = fit_item.split(";")
                    fittings_breakdown.setdefault(item_info[0], 0)
                    if len(item_info) == 1:
                        fittings_breakdown[item_info[0]] += 1 * current_cart["items"][str(selected_fit["_id"])]
                    else:
                        fittings_breakdown[item_info[0]] += int(item_info[1]) * current_cart["items"][
                            str(selected_fit["_id"])]

    cart_item_list_int = [int(x) for x in cart_item_list.keys()]
    fittings_breakdown_int = [int(x) for x in fittings_breakdown.keys()]
    prices_int = cart_item_list_int + fittings_breakdown_int
    prices, prices_usable = market_hub_prices(prices_int) if prices_int else ({}, True)

    full_cart = {}

    invoice_info = [["Name", "Qty", "Vol/Item", "Isk/Item", "Vol Subtotal", "Isk Subtotal"]] + fittings_info
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
        full_cart[str(db_item["_id"])] = {
            "name": db_item["name"],
            "qty": cart_item_list[str(db_item["_id"])],
            "volume": db_item["volume"],
            "price": prices[db_item["_id"]]["sell"],
            "volume_total": db_item["volume"] * cart_item_list[str(db_item["_id"])],
            "price_total": prices[db_item["_id"]]["sell"] * cart_item_list[str(db_item["_id"])]
        }
        total_volume += db_item["volume"] * cart_item_list[str(db_item["_id"])]
        sell_price += prices[db_item["_id"]]["sell"] * cart_item_list[str(db_item["_id"])]

    breakdown_info = [["Name", "Qty", "Vol/Item", "Isk/Item", "Vol Subtotal", "Isk Subtotal"]]
    for db_item_breakdown in g.mongo.db.items.find({"_id": {"$in": fittings_breakdown_int}}):
        breakdown_info.append([
            db_item_breakdown["_id"],
            db_item_breakdown["name"],
            fittings_breakdown[str(db_item_breakdown["_id"])],
            "{:,.02f}".format(db_item_breakdown["volume"]),
            "{:,.02f}".format(prices[int(db_item_breakdown["_id"])]["sell"]),
            "{:,.02f}".format(db_item_breakdown["volume"] * fittings_breakdown[str(db_item_breakdown["_id"])]),
            "{:,.02f}".format(prices[int(db_item_breakdown["_id"])]["sell"] *
                              fittings_breakdown[str(db_item_breakdown["_id"])])
        ])
        if full_cart.get(str(db_item_breakdown["_id"])):
            full_cart[str(db_item_breakdown["_id"])]["qty"] += fittings_breakdown[str(db_item_breakdown["_id"])]
            full_cart[str(db_item_breakdown["_id"])]["volume_total"] += (db_item_breakdown["volume"] *
                                                                         fittings_breakdown[
                                                                             str(db_item_breakdown["_id"])])
            full_cart[str(db_item_breakdown["_id"])]["price_total"] += (prices[int(db_item_breakdown["_id"])]["sell"] *
                                                                        fittings_breakdown[
                                                                            str(db_item_breakdown["_id"])])
        else:
            full_cart[str(db_item_breakdown["_id"])] = {
                "id": db_item_breakdown["_id"],
                "name": db_item_breakdown["name"],
                "qty": fittings_breakdown[str(db_item_breakdown["_id"])],
                "volume": db_item_breakdown["volume"],
                "price": prices[int(db_item_breakdown["_id"])]["sell"],
                "volume_total": db_item_breakdown["volume"] * fittings_breakdown[str(db_item_breakdown["_id"])],
                "price_total": (prices[int(db_item_breakdown["_id"])]["sell"] *
                                fittings_breakdown[str(db_item_breakdown["_id"])])
            }

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
    route_name = ""
    current_route = g.mongo.db.carts.find_one({"_id": session["CharacterOwnerHash"]})
    for route in market_hub_routes:
        if request.args.get("end") and route["_id"] == int(request.args.get("end")):
            valid_stations.append([route["_id"], route["end"], True])
            route_name = route["end"]
        elif current_route:
            if route["_id"] == current_route.get("route"):
                valid_stations.append([route["_id"], route["end"], True])
                selected_route = route["_id"] if selected_route == 0 else selected_route
                route_name = route["end"]
            else:
                valid_stations.append([route["_id"], route["end"], False])
        elif not request.args.get("end") and route["end"] == base_config["default_ship_to"]:
            valid_stations.append([route["_id"], route["end"], True])
            selected_route = route["_id"] if selected_route == 0 else selected_route
            route_name = route["end"]
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

    order_db = g.mongo.db.preferences.find_one({"_id": "ordering"})
    order_tax = order_db.get("tax", 0) if order_db else 0
    order_tax_total = sell_price * order_tax / 100

    order_total = jf_total + sell_price + order_tax_total

    # Update DB
    g.mongo.db.carts.update({"_id": session["CharacterOwnerHash"]},
                            {"$set": {
                                "item_table": full_cart,
                                "route": selected_route,
                                "volume": total_volume,
                                "jf_rate": jf_rate,
                                "jf_total": jf_total,
                                "sell_price": sell_price,
                                "order_total": order_total,
                                "jf_end": route_name,
                                "order_tax": order_tax,
                                "order_tax_total": order_tax_total,
                                "prices_usable": prices_usable
                            }}, upsert=True)

    if request.args.get("action") == "order":
        return redirect(url_for("ordering.invoice"))

    # Formatting
    total_volume = "{:,.02f}".format(total_volume)
    sell_price = "{:,.02f}".format(sell_price)
    jf_total = "{:,.02f}".format(jf_total)
    order_total = "{:,.02f}".format(order_total)
    order_tax = "{:,.02f}".format(order_tax)
    order_tax_total = "{:,.02f}".format(order_tax_total)

    return render_template("ordering.html", invoice_info=invoice_info, total_volume=total_volume,
                           sell_price=sell_price, valid_stations=valid_stations, jf_rate=jf_rate,
                           jf_total=jf_total, order_total=order_total, market_hub_name=market_hub_name,
                           prices_usable=prices_usable, error_string=error_string, breakdown_info=breakdown_info,
                           order_tax=order_tax, order_tax_total=order_tax_total)


@ordering.route("/search")
@requires_sso("corporation")
def search():
    if request.args.get("id"):
        return redirect(url_for("ordering.home",
                                item=request.args.get("id") + ";" +
                                     request.args.get("qty-" + request.args.get("id"), 1)))
    elif not request.args.get("name"):
        return redirect(url_for("ordering.home"))

    regex_search = re.compile(request.args.get("name", ""), re.IGNORECASE)
    item_list = {}
    for item in g.mongo.db.items.find({"name": regex_search}):
        item_list[item["_id"]] = [item["name"], "{:,.02f}".format(item["volume"])]

    prices, prices_usable = market_hub_prices(list(item_list.keys()))
    search_table = []
    for key, value in item_list.items():
        search_table.append(value + ["{:,.02f}".format(prices[key]["sell"]), 1, key])

    with open("configs/base.json") as base_config_file:
        base_config = json.load(base_config_file)

    market_hub_name = base_config["market_hub_name"]

    return render_template("ordering_search.html", search_table=search_table, market_hub_name=market_hub_name,
                           prices_usable=prices_usable)


@ordering.route("/invoice/<invoice_id>")
@ordering.route("/invoice")
@requires_sso("corporation")
def invoice(invoice_id=""):

    with open("configs/base.json") as base_config_file:
        base_config = json.load(base_config_file)
    market_hub_name = base_config["market_hub_name"]

    if not invoice_id:
        cart = g.mongo.db.carts.find_one({"_id": session["CharacterOwnerHash"]})
        if request.args.get("action") == "order":
            cart["user"] = cart.pop("_id")
            invoice_id = g.mongo.db.invoices.insert(cart)
            # g.mongo.db.carts.remove({"_id": cart["user"]})

            # Slack Integration
            if (base_config.get("slack_enable") and
                    (base_config.get("marketeer_slack_url") or base_config.get("market_service_slack_url"))):
                user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})
                if base_config.get("marketeer_slack_url"):
                    payload = {"text": "@channel: " + user["character_name"] + " created a invoice. <" +
                               url_for("ordering.invoice", invoice_id=invoice_id, _external=True) + "|Invoice Link>"}
                    requests.post(base_config["marketeer_slack_url"], json=payload)
                if base_config.get("market_service_slack_url") and user.get("slack"):
                    payload = {"text": "@" + user["slack"] + ": You created a invoice. <" +
                               url_for("ordering.invoice", invoice_id=invoice_id, _external=True) + "|Invoice Link>"}
                    requests.post(base_config["market_service_slack_url"], json=payload)

            return redirect(url_for("account.home"))
    else:
        cart = g.mongo.db.invoices.find_one({"_id": invoice_id})

    invoice_info = [["Name", "Qty", "Vol/Item", "Isk/Item", "Vol Subtotal", "Isk Subtotal"]]
    for item in cart["item_table"].values():
        invoice_info.append([item["name"], item["qty"], "{:,.02f}".format(item["volume"]),
                             "{:,.02f}".format(item["price"]), "{:,.02f}".format(item["volume_total"]),
                             "{:,.02f}".format(item["price_total"])])

    return render_template("ordering_invoice.html", invoice_info=invoice_info, market_hub_name=market_hub_name,
                           prices_usable=cart["prices_usable"], total_volume="{:,.02f}".format(cart["volume"]),
                           sell_price="{:,.02f}".format(cart["sell_price"]),
                           order_tax_total="{:,.02f}".format(cart["order_tax_total"]),
                           order_tax="{:,.02f}".format(cart["order_tax"]), jf_end=cart["jf_end"],
                           jf_rate="{:,.02f}".format(cart["jf_rate"]),
                           jf_total="{:,.02f}".format(cart["jf_total"]),
                           order_total="{:,.02f}".format(cart["order_total"]))
