import os
import json

from flask import Blueprint, render_template, g, request, session
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
    start_list = []
    end_list = []
    for station in g.mongo.db.jfroutes.distinct("start"):
        if request.args.get("start") == station:
            start_list.append([station, True])
        else:
            start_list.append([station, False])
    for station in g.mongo.db.jfroutes.distinct("end"):
        if request.args.get("end") == station:
            end_list.append([station, True])
        else:
            end_list.append([station, False])
    start_list.sort()
    end_list.sort()

    # Contract Calculations
    if request.args.get("start") and request.args.get("end"):
        selected_route = g.mongo.db.jfroutes.find_one({"start": request.args.get("start"),
                                                       "end": request.args.get("end")})
        if selected_route:
            m3 = selected_route["m3"]
            extra = selected_route["extra"]

            volume = request.args.get("volume")
            collateral = request.args.get("collateral")
            volume = 0 if not volume else float(volume)
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
            users_set.update([contract["issuer_id"], contract["acceptor_id"]])

    # Check Caches
    caches.stations()
    caches.contracts()
    caches.character(users_set)

    contract_list = [["Issuer", "Acceptor", "Start", "End", "Status", "Date Issued", "Expiration Date", "Volume"]]
    personal_contract_list = [["Acceptor", "Start", "End", "Status", "Date Issued", "Expiration Date", "Volume",
                               "Reward", "Collateral"]]

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
            acceptor_query = g.mongo.db.characters.find_one({"_id": contract["acceptor_id"]})

            # Check if contract is valid
            validation_query = g.mongo.db.jfroutes.find_one({
                "start": start_station.strip(),
                "end": end_station.strip()})
            validation_failed = ["Failed", "Cancelled", "Rejected", "Reversed", "Deleted"]
            validation_completed = ["Completed", "CompletedByIssuer", "CompletedByContractor"]
            color = ""  # Default color, used for outstanding

            if validation_query:
                validation_calc = max(float(validation_query["m3"]) * float(contract["volume"]) +
                                      float(validation_query["extra"]) + float(contract["collateral"]) * 0.1, 1000000)
                if float(contract["reward"]) < validation_calc or volume > 300000:
                    color = "info"
            else:
                color = "active"

            if contract["status"] in validation_failed:
                color = "danger"
            elif contract["status"] == "InProgress":
                color = "warning"
            elif contract["status"] in validation_completed:
                color = "success"

            # Fix no acceptor
            if acceptor_query["name"] == "Unknown Item":
                acceptor = "None"
            elif acceptor_query:
                acceptor = acceptor_query["name"]
            else:
                acceptor = ""

            issuer = issuer_query["name"] if issuer_query else ""

            contract_list.append([
                color,
                issuer,
                acceptor,
                start_station,
                end_station,
                contract["status"],
                contract["date_issued"],
                contract["date_expired"],
                "{:0,.2f}".format(float(contract["volume"]))
            ])

            if issuer == session["CharacterName"]:
                personal_contract_list.append([
                    color,
                    acceptor,
                    start_station,
                    end_station,
                    contract["status"],
                    contract["date_issued"],
                    contract["date_expired"],
                    "{:0,.2f}".format(float(contract["volume"])),
                    "{:0,.2f}".format(float(contract["reward"])),
                    "{:0,.2f}".format(float(contract["collateral"]))
                ])

    # Warnings
    warning_list = []
    if price < 1000000:
        warning_list.append("Rewards must be at least 1M Isk")
        price = 1000000
    if volume > 300000:
        warning_list.append("Contracts must be less than 300k M3")
    if price > 1000000000:
        warning_list.append("Contracts should be below 1B isk")

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
    volume = "{:0.2f}".format(float(volume)) if volume else volume
    collateral = "{:0.2f}".format(float(collateral)) if collateral else collateral

    # Check admin
    jf_admin = auth_check("jf_admin")

    return render_template("jf.html", start_list=start_list, end_list=end_list, m3=m3, extra=extra, price=price,
                           volume=volume, contract_list=contract_list, next_update=next_update, admin=jf_admin,
                           collateral=collateral, volume_cost=volume_cost, collateral_cost=collateral_cost,
                           warning_list=warning_list, personal_contract_list=personal_contract_list)


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
        if request.form.get("action") == "single":
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
        elif request.form.get("action") == "multiple":
            documents = []
            station_list = [x.strip() for x in request.form.get("stations").split("\n")]
            for start_station in station_list:
                for end_station in station_list:
                    if start_station != end_station:
                        documents.append({
                            "name": start_station.split(" - ")[0] + " >> " + end_station.split(" - ")[0],
                            "m3": 0,
                            "extra": 0,
                            "start": start_station,
                            "end": end_station
                        })
            g.mongo.db.jfroutes.insert(documents)

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
