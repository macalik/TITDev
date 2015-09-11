import os
import json

from flask import Blueprint, render_template, g, request
from bson.objectid import ObjectId

from helpers import caches
from views.auth import requires_sso

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

    if request.args.get("volume"):
        selected_route = g.mongo.db.jfroutes.find_one({"_id": ObjectId(request.args.get("route"))})
        m3 = selected_route["m3"]
        extra = selected_route["extra"]
        price = "{:0,.2f}".format(m3 * float(request.args.get("volume")) + extra)
        volume = request.args.get("volume")
        result = True
    else:
        m3 = 0
        extra = 0
        price = 0
        volume = 0
        result = False

    users_set = set()
    # Find all users
    for contract in g.mongo.db.contracts.find():
        if contract["_id"] != "cached_until":
            users_set.update([contract["issuer_id"], contract["assignee_id"], contract["acceptor_id"]])

    # Check Caches
    caches.stations()
    caches.contracts()
    caches.character(users_set)

    contract_list = [["Contract ID", "Issuer", "Assignee", "Acceptor", "Start", "End", "Status", "Date Issued",
                     "Date Expired", "Date Accepted"]]
    # Final output
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
            if contract["acceptor_id"] == "0":
                acceptor = "None"
            else:
                acceptor_query = g.mongo.db.characters.find_one({"_id": contract["acceptor_id"]})
                acceptor = acceptor_query["name"] if acceptor_query else ""

            issuer_query = g.mongo.db.characters.find_one({"_id": contract["issuer_id"]})
            assignee_query = g.mongo.db.characters.find_one({"_id": contract["assignee_id"]})
            contract_list.append([
                contract["_id"],
                issuer_query["name"] if issuer_query else "",
                assignee_query["name"] if assignee_query else "",
                acceptor,
                start_station,
                end_station,
                contract["status"],
                contract["date_issued"],
                contract["date_expired"],
                contract["date_accepted"]
            ])

    return render_template("jf.html", route_list=route_list, m3=m3, extra=extra, price=price,
                           volume=volume, result=result, contract_list=contract_list, next_update=next_update)
