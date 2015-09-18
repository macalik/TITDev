import calendar
import time
import os
import json

from flask import g, session
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
    db_stations_cache = g.mongo.db.caches.find_one({"_id": "stations"})
    bulk_op = g.mongo.db.stations.initialize_unordered_bulk_op()
    bulk_run = False
    if not db_stations_cache or db_stations_cache["cached_until"] < time.time():
        bulk_run = True
        xml_stations_response = requests.get("https://api.eveonline.com/eve/ConquerableStationList.xml.aspx",
                                             headers=xml_headers)
        # XML Parse
        xml_stations_tree = ElementTree.fromstring(xml_stations_response.text)
        # Store in database
        xml_time_pattern = "%Y-%m-%d %H:%M:%S"
        g.mongo.db.caches.update({"_id": "stations"}, {"cached_until": int(calendar.timegm(time.strptime(
            xml_stations_tree[2].text, xml_time_pattern)))}, upsert=True)
        for station in xml_stations_tree[1][0]:
            bulk_op.find({"_id": int(station.attrib["stationID"])}).upsert().update(
                {"$set": {"name": station.attrib["stationName"]}})
    if bulk_run:
        bulk_op.execute()


def character(char_ids):
    missing_names = []
    for char_id in char_ids:
        db_character = g.mongo.db.characters.find_one({"_id": char_id})
        if not db_character:
            missing_names.append(char_id)

    db_characters_cache = g.mongo.db.caches.find_one({"_id": "characters"})
    bulk_op = g.mongo.db.characters.initialize_unordered_bulk_op()
    bulk_run = False
    if missing_names or not db_characters_cache or db_characters_cache["cached_until"] < time.time():
        bulk_run = True
        if db_characters_cache and db_characters_cache["cached_until"] > time.time():
            character_payload = {
                "ids": ",".join([str(x) for x in missing_names])
            }
        else:
            character_payload = {
                "ids": ",".join([str(x) for x in char_ids])
            }

        xml_character_response = requests.get("https://api.eveonline.com/eve/CharacterAffiliation.xml.aspx",
                                              data=character_payload, headers=xml_headers)
        # XML Parse
        xml_character_tree = ElementTree.fromstring(xml_character_response.text)
        xml_time_pattern = "%Y-%m-%d %H:%M:%S"
        g.mongo.db.caches.update({"_id": "characters"}, {"cached_until": int(calendar.timegm(time.strptime(
            xml_character_tree[2].text, xml_time_pattern)))}, upsert=True)

        if xml_character_tree[1].tag == "error":
            print(xml_character_tree[1].attrib["code"], xml_character_tree[1].text)
        else:
            for name in xml_character_tree[1][0]:
                bulk_op.find({"_id": int(name.attrib["characterID"])}).upsert().update({"$set": {
                    "name": name.attrib["characterName"],
                    "corporation_id": int(name.attrib["corporationID"]),
                    "corporation_name": name.attrib["corporationName"],
                    "alliance_id": int(name.attrib["allianceID"]),
                    "alliance_name": name.attrib["allianceName"]
                }})

    if bulk_run:
        bulk_op.execute()


def contracts(keys=None):
    if not keys:
        # Default Refreshes
        keys = [("jf_service", secrets["jf_key_id"], secrets["jf_vcode"])]
    bulk_op = g.mongo.db.contracts.initialize_unordered_bulk_op()
    bulk_run = False
    for service in keys:
        db_contracts_cache = g.mongo.db.caches.find_one({"_id": service[0]})
        if not db_contracts_cache or db_contracts_cache.get("cached_until", 0) < time.time():
            bulk_run = True
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
            g.mongo.db.caches.update({"_id": service[0]}, {"cached_until": int(calendar.timegm(
                time.strptime(xml_contracts_tree[2].text, xml_time_pattern))),
                "cached_str": xml_contracts_tree[2].text}, upsert=True)
            for contract in xml_contracts_tree[1][0]:
                bulk_op.find({"_id": int(contract.attrib["contractID"]), "service": service[0]}).upsert().update(
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
                            "volume": float(contract.attrib["volume"])
                        }
                    })
    if bulk_run:
        bulk_op.execute()


def api_keys(api_key_list):
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    errors = []
    bulk_op = g.mongo.db.api_keys.initialize_ordered_bulk_op()
    bulk_run = False

    for key_id, vcode in api_key_list:
        db_api_cache = g.mongo.db.api_keys.find_one({"_id": session["CharacterOwnerHash"],
                                                     "keys.key_id": {"$eq": int(key_id)}})
        cache_timer = 0
        if db_api_cache:
            cache_timer_list = [key["cached_until"] for key in db_api_cache["keys"] if key["key_id"] == int(key_id)]
            cache_timer = max(cache_timer_list)
        print(cache_timer)
        if not db_api_cache or cache_timer < time.time():

            xml_contracts_payload = {
                "keyID": key_id,
                "vCode": vcode
            }
            xml_api_key_response = requests.get("https://api.eveonline.com/account/APIKeyInfo.xml.aspx",
                                                data=xml_contracts_payload, headers=xml_headers)
            # XML Parse
            xml_api_key_tree = ElementTree.fromstring(xml_api_key_response.text)
            # Store in database
            xml_time_pattern = "%Y-%m-%d %H:%M:%S"
            if xml_api_key_tree[1].tag == "error":
                errors.append("CCP gave an error for key with id " +
                              "{}. Ensure the key is not expired and is valid.".format(key_id))
                continue
            elif xml_api_key_tree[1][0].attrib["accessMask"] != str(base_config["access_mask"]):
                errors.append("Key with id {} is not (or no longer) a full API key.".format(key_id))
                continue
            elif xml_api_key_tree[1][0].attrib["type"] != "Account":
                errors.append("Key with id {} is not an Account API key.".format(key_id))
                continue
            elif xml_api_key_tree[1][0].attrib["expires"].strip():
                errors.append("Key with id {} expires. Must be a non-expiring API key.".format(key_id))
                continue

            for api_character in xml_api_key_tree[1][0][0]:
                bulk_run = True
                # If same character is input, remove old keys first
                bulk_op.find({"_id": session["CharacterOwnerHash"]}).upsert().update(
                    {
                        "$pull": {
                            "keys": {"key_id": int(key_id)}
                        }
                    })
                update_request = {"$push": {"keys": {
                                      "key_id": int(key_id),
                                      "vcode": vcode,
                                      "character_id": int(api_character.attrib["characterID"]),
                                      "character_name": api_character.attrib["characterName"],
                                      "cached_until": int(calendar.timegm(time.strptime(xml_api_key_tree[2].text,
                                                                                        xml_time_pattern))),
                                      "cached_str": xml_api_key_tree[2].text
                                  }}}
                bulk_op.find({"_id": session["CharacterOwnerHash"]}).upsert().update(update_request)

    if bulk_run:
        bulk_op.execute()

    return errors
