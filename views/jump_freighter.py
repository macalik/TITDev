import os
import json

from flask import Blueprint, render_template, g, request
from bson.objectid import ObjectId

from helpers import caches
from views.auth import requires_sso, auth_check

jf = Blueprint("jf", __name__, template_folder="templates")

if os.environ.get("HEROKU"):
    secrets = {
        "jf_key_id": os.environ["jf_key_id"],
        "jf_vcode": os.environ["jf_vcode"]
    }
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)


@jf.route("/")
@requires_sso("alliance")
def home():
    route_list = []
    for route in g.mongo.db.jfroutes.find():
        route_list.append([route["_id"], route["name"]])

    # Contract Calculations
    if request.args.get("route"):
        selected_route = g.mongo.db.jfroutes.find_one({"_id": ObjectId(request.args.get("route"))})
        m3 = selected_route["m3"]
        extra = selected_route["extra"]

        volume = request.args.get("volume")
        collateral = request.args.get("collateral")
        volume = 0 if not volume else volume
        collateral = 0 if not collateral else collateral

        volume_cost = m3 * float(volume)
        collateral_cost = float(collateral) * 0.1
        price = extra + volume_cost + collateral_cost
    else:
        m3 = 0
        extra = 0
        volume = 0
        volume_cost = 0
        collateral = 0
        collateral_cost = 0
        price = 0

    users_set = set()
    # Find all users
    for contract in g.mongo.db.contracts.find():
        if contract["_id"] != "cached_until":
            users_set.update([contract["issuer_id"]])

    # Check Caches
    caches.stations()
    caches.contracts()
    caches.character(users_set)

    contract_list = [["Issuer", "Start", "End", "Status", "Date Issued", "Expiration Date",
                      "Reward", "Collateral", "Volume"]]

    next_update_query = g.mongo.db.contracts.find_one({"_id": "cached_until"})
    next_update = next_update_query["str_time"] if next_update_query else "Unknown"
    for contract in g.mongo.db.contracts.find():
        if contract["_id"] != "cached_until":
            # Check for non-static stations
            start_station = g.mongo.db.stations.find_one({"_id": contract["start_station_id"]})
            end_station = g.mongo.db.stations.find_one({"_id": contract["end_station_id"]})
            if not start_station:
                start_station = g.staStations[contract["start_station_id"]]
            else:
                start_station = start_station["name"]
            if not end_station:
                end_station = g.staStations[contract["end_station_id"]]
            else:
                end_station = end_station["name"]

            issuer_query = g.mongo.db.characters.find_one({"_id": contract["issuer_id"]})

            # Check if contract is valid
            validation_query = g.mongo.db.jfroutes.find_one({
                "start": start_station.strip(),
                "end": end_station.strip()})
            validation_failed = ["Failed", "Cancelled", "Rejected", "Reversed", "Deleted"]
            validation_completed = ["Completed", "CompletedByIssuer", "CompletedByContractor"]
            color = ""  # Default color, used for outstanding

            if validation_query:
                validation_calc = (float(validation_query["m3"]) * float(contract["volume"]) +
                                   float(validation_query["extra"]) + float(contract["collateral"]) * 0.1)
                if float(contract["reward"]) < validation_calc:
                    color = "info"
            else:
                color = "active"

            if contract["status"] in validation_failed:
                color = "danger"
            elif contract["status"] == "InProgress":
                color = "warning"
            elif contract["status"] in validation_completed:
                color = "success"

            contract_list.append([
                color,
                issuer_query["name"] if issuer_query else "",
                start_station,
                end_station,
                contract["status"],
                contract["date_issued"],
                contract["date_expired"],
                "{:0,.2f}".format(float(contract["reward"])),
                "{:0,.2f}".format(float(contract["collateral"])),
                "{:0,.2f}".format(float(contract["volume"]))
            ])

    # Empty volume if volume is 0
    if volume == 0:
        volume = ""
    if collateral == 0:
        collateral = ""

    # Formatting
    extra = "{:0,.2f}".format(extra)
    volume_cost = "{:0,.2f}".format(volume_cost)
    collateral_cost = "{:0,.2f}".format(collateral_cost)
    price = "{:0,.2f}".format(price)

    # Check admin
    jf_admin = auth_check("jf_admin")

    return render_template("jf.html", route_list=route_list, m3=m3, extra=extra, price=price,
                           volume=volume, contract_list=contract_list, next_update=next_update, admin=jf_admin,
                           collateral=collateral, volume_cost=volume_cost, collateral_cost=collateral_cost)


@jf.route('/admin', methods=["GET", "POST"])
@requires_sso('jf_admin')
def admin():
    route_list = []  # route = [_id, name, m3, extra]
    m3 = ""
    extra = ""
    _id = ""
    name = ""
    start = ""
    end = ""
    edit = False

    if request.method == "GET":
        if request.args.get("action") == "delete":
            g.mongo.db.jfroutes.remove({"_id": ObjectId(request.args.get("_id"))})
        elif request.args.get("action") == "edit":
            selected_route = g.mongo.db.jfroutes.find_one({"_id": ObjectId(request.args.get("_id"))})
            edit = True
            _id = request.args.get("_id")
            name = selected_route["name"]
            m3 = "{:0,.2f}".format(selected_route["m3"])
            extra = "{:0,.2f}".format(selected_route["extra"])
            start = selected_route["start"]
            end = selected_route["end"]
    elif request.method == "POST":
        m3 = request.form.get("m3") if request.form.get("m3") else 0
        extra = request.form.get("extra") if request.form.get("extra") else 0
        if request.form.get("_id"):
            g.mongo.db.jfroutes.update({"_id": ObjectId(request.form.get("_id"))},
                                       {
                                           "name": request.form.get("name"),
                                           "m3": float(m3),
                                           "extra": float(extra),
                                           "start": request.form.get("start").strip(),
                                           "end": request.form.get("end").strip()
                                       }, upsert=True)
        else:
            g.mongo.db.jfroutes.insert({
                                           "name": request.form.get("name"),
                                           "m3": float(m3),
                                           "extra": float(extra),
                                           "start": request.form.get("start"),
                                           "end": request.form.get("end")
                                       })

        # Clear all after post
        m3 = ""
        extra = ""
        _id = ""
        name = ""
        start = ""
        end = ""
        edit = False

    for route in g.mongo.db.jfroutes.find():
        route_list.append([route["_id"], route["name"],
                           "{:0,.2f}".format(route["m3"]), "{:0,.2f}".format(route["extra"]),
                           route["start"], route["end"]])

    return render_template("jf_admin.html", route_list=route_list, m3=m3, extra=extra, _id=_id, name=name,
                           start=start, end=end, edit=edit)
