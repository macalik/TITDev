import calendar
import time
import os
import json

from flask import g, session
from defusedxml import ElementTree
import requests

from pymongo.errors import BulkWriteError
from pprint import pprint

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
    # If service is personal, uses key_caches database for cache values instead
    invalid_apis = []

    if not keys:
        # Default Refreshes
        keys = [("jf_service", secrets["jf_key_id"], secrets["jf_vcode"])]
    bulk_op = g.mongo.db.contracts.initialize_unordered_bulk_op()
    bulk_run = False
    for service in keys:
        if service[0] == "personal":
            db_cache = g.mongo.db.key_caches.find_one({"_id": service[1]})
            cache_time = db_cache.get("contracts", 0) if db_cache else 0
        else:
            db_cache = g.mongo.db.caches.find_one({"_id": service[0]})
            cache_time = db_cache.get("cached_until", 0) if db_cache else 0
        if not db_cache or cache_time < time.time():

            if service[0] == "personal":
                xml_contracts_payload = {
                    "keyID": service[1],
                    "vCode": service[2],
                    "characterID": service[3]
                }
                xml_contracts_response = requests.get("https://api.eveonline.com/char/Contracts.xml.aspx",
                                                      data=xml_contracts_payload, headers=xml_headers)
            else:
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

            if service[0] == "personal":
                g.mongo.db.key_caches.update({"_id": service[1]}, {"$set": {"contracts": int(
                    calendar.timegm(time.strptime(xml_contracts_tree[2].text, xml_time_pattern))),
                    "contracts_str": xml_contracts_tree[2].text}}, upsert=True)
            else:
                g.mongo.db.caches.update({"_id": service[0]}, {"cached_until": int(
                    calendar.timegm(time.strptime(xml_contracts_tree[2].text, xml_time_pattern))),
                    "cached_str": xml_contracts_tree[2].text}, upsert=True)

            if xml_contracts_tree[1].tag == "error":
                print(xml_contracts_tree[1].attrib["code"], xml_contracts_tree[1].text, service[1])
                g.mongo.db.api_keys.update({}, {"$pull": {"keys": {"key_id": service[1]}}}, multi=True)
                invalid_apis.append(service[1])
            else:
                for contract in xml_contracts_tree[1][0]:
                    bulk_run = True
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
        try:
            bulk_op.execute()
        except BulkWriteError as bulk_op_error:
            pprint(bulk_op_error.details)

    return invalid_apis


def api_keys(api_key_list):
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    errors_list = []
    bulk_op = g.mongo.db.api_keys.initialize_ordered_bulk_op()
    bulk_run = False

    for key_id, vcode in api_key_list:
        db_api_cache = g.mongo.db.api_keys.find_one({"_id": session["CharacterOwnerHash"],
                                                     "keys.key_id": {"$eq": int(key_id)}})
        cache_timer = 0
        if db_api_cache:
            cache_timer_list = [key["cached_until"] for key in db_api_cache["keys"] if key["key_id"] == int(key_id)]
            cache_timer = max(cache_timer_list)
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
                errors_list.append("CCP gave an error for key with id " +
                                   "{}. Ensure the key is not expired and is valid.".format(key_id))
                continue
            elif xml_api_key_tree[1][0].attrib["accessMask"] != str(base_config["access_mask"]):
                errors_list.append("Key with id {} is not (or no longer) a full API key.".format(key_id))
                continue
            elif xml_api_key_tree[1][0].attrib["type"] != "Account":
                errors_list.append("Key with id {} is not an Account API key.".format(key_id))
                continue
            elif xml_api_key_tree[1][0].attrib["expires"].strip():
                errors_list.append("Key with id {} expires. Must be a non-expiring API key.".format(key_id))
                continue

            # If same character is input, remove old keys first
            bulk_op.find({"_id": session["CharacterOwnerHash"]}).upsert().update(
                {
                    "$pull": {
                        "keys": {"key_id": int(key_id)}
                    }
                })

            for api_character in xml_api_key_tree[1][0][0]:
                bulk_run = True
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

    return errors_list


def wallet_journal(keys=None):
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    if not keys:
        # Default Refreshes
        keys = [("jf_wallet", secrets["jf_key_id"], secrets["jf_vcode"])]
    bulk_op = g.mongo.db.wallet_journal.initialize_unordered_bulk_op()
    bulk_run = False
    for service in keys:
        db_wallet_journal_cache = g.mongo.db.caches.find_one({"_id": service[0]})
        if not db_wallet_journal_cache or db_wallet_journal_cache.get("cached_until", 0) < time.time():
            bulk_run = True
            xml_wallet_journal_payload = {
                "keyID": service[1],
                "vCode": service[2],
                "accountKey": base_config["jf_account_key"]
            }
            xml_wallet_journal_response = requests.get("https://api.eveonline.com/corp/WalletJournal.xml.aspx",
                                                       data=xml_wallet_journal_payload, headers=xml_headers)
            # XML Parse
            xml_wallet_journal_tree = ElementTree.fromstring(xml_wallet_journal_response.text)
            # Store in database
            xml_time_pattern = "%Y-%m-%d %H:%M:%S"
            g.mongo.db.caches.update({"_id": service[0]}, {"cached_until": int(calendar.timegm(
                time.strptime(xml_wallet_journal_tree[2].text, xml_time_pattern))),
                "cached_str": xml_wallet_journal_tree[2].text}, upsert=True)
            for transaction in xml_wallet_journal_tree[1][0]:
                bulk_op.find({"_id": int(transaction.attrib["refID"]), "service": service[0]}).upsert().update(
                    {
                        "$set": {
                            "ref_type_id": int(transaction.attrib["refTypeID"]),
                            "owner_name_1": transaction.attrib["ownerName1"],
                            "owner_id_1": int(transaction.attrib["ownerID1"]),
                            "owner_name_2": transaction.attrib["ownerName2"],
                            "owner_id_2": int(transaction.attrib["ownerID2"]),
                            "amount": float(transaction.attrib["amount"]),
                            "reason": transaction.attrib["reason"]
                        }
                    })

    if bulk_run:
        bulk_op.execute()
