import calendar
import time
import os
import json

from flask import g
from defusedxml import ElementTree
import requests

xml_headers = {
    "User-Agent": "TiT Corp Website by Kazuki Ishikawa"
}

if os.environ.get("HEROKU"):
    secrets = {
        "jf_key_id": os.environ["jf_key_id"],
        "jf_vcode": os.environ["jf_vcode"]
    }
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)


def stations():
    db_stations_cache = g.mongo.db.stations.find_one({"_id": "cached_until"})
    if not db_stations_cache or db_stations_cache["time"] < time.time():
        xml_stations_response = requests.get("https://api.eveonline.com/eve/ConquerableStationList.xml.aspx",
                                             headers=xml_headers)
        # XML Parse
        xml_stations_tree = ElementTree.fromstring(xml_stations_response.text)
        # Store in database
        xml_time_pattern = "%Y-%m-%d %H:%M:%S"
        g.mongo.db.stations.update({"_id": "cached_until"}, {"time": int(calendar.timegm(time.strptime(
            xml_stations_tree[2].text, xml_time_pattern)))}, upsert=True)
        for station in xml_stations_tree[1][0]:
            g.mongo.db.stations.update({"_id": int(station.attrib["stationID"])},
                                       {"name": station.attrib["stationName"]}, upsert=True)


def character(char_ids):
    """
    Char IDs as ints.
    Because names don't change in EVE, only adds name to database if not found for now.
    Will rewrite if more character information is needed.
    """
    missing_names = []
    for char_id in char_ids:
        db_character_cache = g.mongo.db.characters.find_one({"_id": char_id})
        if not db_character_cache:
            missing_names.append(char_id)

    if missing_names:
        character_payload = {
            "ids": ",".join([str(x) for x in missing_names])
        }
        xml_character_response = requests.get("https://api.eveonline.com/eve/CharacterName.xml.aspx",
                                              data=character_payload, headers=xml_headers)
        # XML Parse
        xml_stations_tree = ElementTree.fromstring(xml_character_response.text)
        for name in xml_stations_tree[1][0]:
            g.mongo.db.characters.insert({"_id": int(name.attrib["characterID"]), "name": name.attrib["name"]})


def contracts(keys=None):
    if not keys:
        # Default Refreshes
        keys = [("jf_service", secrets["jf_key_id"], secrets["jf_vcode"])]
    for service in keys:
        db_contracts_cache = g.mongo.db.contracts.find_one({"_id": service[0]})
        if not db_contracts_cache or db_contracts_cache.get("cached_until", 0) < time.time():
            xml_contracts_payload = {
                "keyID": service[1],
                "vCode": service[2]
            }
            xml_contracts_response = requests.get("https://api.eveonline.com/Corp/Contracts.xml.aspx",
                                                  data=xml_contracts_payload, headers=xml_headers)
            # XML Parse
            xml_contracts_tree = ElementTree.fromstring(xml_contracts_response.text)
            # Store in database
            xml_time_pattern = "%Y-%m-%d %H:%M:%S"
            g.mongo.db.contracts.update({"_id": service[0]}, {"cached_until": int(calendar.timegm(time.strptime(
                xml_contracts_tree[2].text, xml_time_pattern))), "str_cache": xml_contracts_tree[2].text}, upsert=True)
            for contract in xml_contracts_tree[1][0]:
                g.mongo.db.contracts.update({"_id": int(contract.attrib["contractID"]),
                                             "service": service[0]},
                                            {
                                                "$set": {
                                                    "issuer_id": int(contract.attrib["issuerID"]),
                                                    "assignee_id": int(contract.attrib["assigneeID"]),
                                                    "acceptor_id": int(contract.attrib["acceptorID"]),
                                                    "start_station_id": int(contract.attrib["startStationID"]),
                                                    "end_station_id": int(contract.attrib["endStationID"]),
                                                    "type": contract.attrib["type"],
                                                    "status": contract.attrib["status"],
                                                    "title": contract.attrib["title"],
                                                    "for_corp": int(contract.attrib["forCorp"]),
                                                    "date_issued": contract.attrib["dateIssued"],
                                                    "date_expired": contract.attrib["dateExpired"],
                                                    "date_accepted": contract.attrib["dateAccepted"],
                                                    "num_days": int(contract.attrib["numDays"]),
                                                    "date_completed": contract.attrib["dateCompleted"],
                                                    "price": float(contract.attrib["price"]),
                                                    "reward": float(contract.attrib["reward"]),
                                                    "collateral": float(contract.attrib["collateral"]),
                                                    "volume": float(contract.attrib["volume"]),
                                                    "service": service[0]
                                                }
                                           }, upsert=True)
