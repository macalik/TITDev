import calendar
import time
import os
import json

from flask import g, session
from defusedxml import ElementTree
import requests

from pymongo.errors import BulkWriteError

from helpers import conversions, error_handling

xml_headers = {
    "User-Agent": "TiT Corp Website by Kazuki Ishikawa"
}

if os.environ.get("HEROKU"):
    secrets = {
        "jf_key_id": os.environ["jf_key_id"],
        "jf_vcode": os.environ["jf_vcode"],
        "main_key_id": os.environ["main_key_id"],
        "main_vcode": os.environ["main_vcode"]
    }
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)


def stations():
    db_stations_cache = g.mongo.db.caches.find_one({"_id": "stations"})
    bulk_op = g.mongo.db.stations.initialize_unordered_bulk_op()
    bulk_run = False
    if not db_stations_cache or db_stations_cache["cached_until"] < time.time():
        xml_stations_response = requests.get("https://api.eveonline.com/eve/ConquerableStationList.xml.aspx",
                                             headers=xml_headers)
        # XML Parse
        try:
            xml_stations_tree = ElementTree.fromstring(xml_stations_response.text)
        except ElementTree.ParseError:
            print(xml_stations_response.text)
            return None

        # Store in database
        xml_time_pattern = "%Y-%m-%d %H:%M:%S"
        g.mongo.db.caches.update({"_id": "stations"}, {"cached_until": int(calendar.timegm(time.strptime(
            xml_stations_tree[2].text, xml_time_pattern)))}, upsert=True)
        for station in xml_stations_tree[1][0]:
            bulk_run = True
            bulk_op.find({"_id": int(station.attrib["stationID"])}).upsert().update(
                {"$set": {"name": station.attrib["stationName"]}})
    if bulk_run:
        bulk_op.execute()


def character(char_ids):
    """

    :param char_ids: [character_id, ...]
    :return:
    """

    missing_names = []
    for char_id in char_ids:
        db_character = g.mongo.db.characters.find_one({"_id": char_id})
        if not db_character:
            missing_names.append(char_id)

    db_characters_cache = g.mongo.db.caches.find_one({"_id": "characters"})
    bulk_op = g.mongo.db.characters.initialize_unordered_bulk_op()
    bulk_run = False
    if missing_names or not db_characters_cache or db_characters_cache["cached_until"] < time.time():
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
        try:
            xml_character_tree = ElementTree.fromstring(xml_character_response.text)
        except ElementTree.ParseError:
            print(xml_character_response.text)
            return None

        xml_time_pattern = "%Y-%m-%d %H:%M:%S"
        g.mongo.db.caches.update({"_id": "characters"}, {"cached_until": int(calendar.timegm(time.strptime(
            xml_character_tree[2].text, xml_time_pattern)))}, upsert=True)

        if xml_character_tree[1].tag == "error":
            print(xml_character_tree[1].attrib["code"], xml_character_tree[1].text)
        else:
            for name in xml_character_tree[1][0]:
                bulk_run = True
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
    """

    :param keys: [("jf_service" or "personal", key_id, vcode, character_id), (), ...]
    :return:
    """

    # If service is personal, uses key_caches database for cache values instead
    invalid_apis = set()

    if not keys:
        # Default Refreshes
        keys = [("jf_service", secrets["jf_key_id"], secrets["jf_vcode"])]
    bulk_op = g.mongo.db.contracts.initialize_unordered_bulk_op()
    bulk_run = False
    for service in keys:
        if service[0] == "personal":
            db_cache = g.mongo.db.key_caches.find_one({"_id": service[3]})
            cache_time = db_cache.get("contracts", 0) if db_cache else 0
        else:
            db_cache = g.mongo.db.caches.find_one({"_id": service[0]})
            cache_time = db_cache.get("cached_until", 0) if db_cache else 0
        if not db_cache or cache_time < time.time():

            # Clean contract history
            month_ago = int(time.time()) - 2629743  # Services are 1 month
            two_weeks_ago = int(time.time()) - 1512000  # Personals are 2 1/2 weeks
            g.mongo.db.contracts.remove({"issued_int": {"$lt": month_ago}})
            filter_time = month_ago
            if service[0] == "personal":
                g.mongo.db.contracts.remove({"_id.service": "personal", "issued_int": {"$lt": two_weeks_ago}})
                filter_time = two_weeks_ago

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
            try:
                xml_contracts_tree = ElementTree.fromstring(xml_contracts_response.text)
            except ElementTree.ParseError:
                print(xml_contracts_response.text)
                return list(invalid_apis)

            # Store in database
            xml_time_pattern = "%Y-%m-%d %H:%M:%S"

            if service[0] == "personal":
                g.mongo.db.key_caches.update({"_id": int(service[3])}, {"$set": {
                    "contracts": int(
                        calendar.timegm(time.strptime(xml_contracts_tree[2].text, xml_time_pattern))),
                    "contracts_str": xml_contracts_tree[2].text,
                    "key": int(service[1])}
                }, upsert=True)
            else:
                g.mongo.db.caches.update({"_id": service[0]}, {"cached_until": int(
                    calendar.timegm(time.strptime(xml_contracts_tree[2].text, xml_time_pattern))),
                    "cached_str": xml_contracts_tree[2].text}, upsert=True)

            if xml_contracts_tree[1].tag == "error":
                print(xml_contracts_tree[1].attrib["code"], xml_contracts_tree[1].text, service[1])
                conversions.invalidate_key([service[1]], session["CharacterOwnerHash"])
                invalid_apis.add(service[1])
            else:
                for contract in xml_contracts_tree[1][0]:
                    issue_time = int(calendar.timegm(time.strptime(contract.attrib["dateIssued"], xml_time_pattern)))
                    if issue_time > filter_time:
                        bulk_run = True
                        bulk_op.find({
                            "_id.id": int(contract.attrib["contractID"]), "_id.service": service[0]
                        }).upsert().update(
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
                                    "issued_int": issue_time
                                }
                            })
    if bulk_run:
        try:
            bulk_op.execute()
        except BulkWriteError as bulk_op_error:
            print("error", bulk_op_error.details)

    return list(invalid_apis)


def api_keys(api_key_list, unassociated=False):
    """

    :param api_key_list: [(key_id, vcode), (), ...]
    :param unassociated: True to add to unassociated API keys
    :return:
    """
    api_owner = "unassociated" if unassociated else session["CharacterOwnerHash"]

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    errors_list = []
    bulk_op = g.mongo.db.api_keys.initialize_ordered_bulk_op()
    bulk_run = False

    for key_id, vcode in api_key_list:
        db_api_cache = g.mongo.db.api_keys.find_one({"_id": api_owner,
                                                     "keys.key_id": {"$eq": int(key_id)}})
        cache_timer = 0
        if db_api_cache and api_owner != "unassociated":
            cache_timer_list = [key["cached_until"] for key in db_api_cache["keys"] if key["key_id"] == int(key_id)]
            cache_timer = max(cache_timer_list)
        elif api_owner == "unassociated":
            cache_timer = 0
        if not db_api_cache or cache_timer < time.time():

            xml_contracts_payload = {
                "keyID": key_id,
                "vCode": vcode
            }
            xml_api_key_response = requests.get("https://api.eveonline.com/account/APIKeyInfo.xml.aspx",
                                                data=xml_contracts_payload, headers=xml_headers)
            # XML Parse
            try:
                xml_api_key_tree = ElementTree.fromstring(xml_api_key_response.text)
            except ElementTree.ParseError:
                print(xml_api_key_response.text)
                return errors_list

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
            bulk_op.find({"_id": api_owner}).upsert().update(
                {
                    "$pull": {
                        "keys": {"key_id": int(key_id)}
                    }
                })
            if api_owner != "unassociated":
                # Remove keys from unassociated if found
                bulk_op.find({"_id": "unassociated"}).upsert().update(
                    {
                        "$pull": {
                            "keys": {"key_id": int(key_id)}
                        }
                    }
                )

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
                if api_owner != "unassociated" or (api_owner == "unassociated" and not g.mongo.db.api_keys.find_one(
                        {"keys.key_id": {"$eq": int(key_id)}, "_id": {"$ne": "unassociated"}})):
                    bulk_op.find({"_id": api_owner}).upsert().update(update_request)

    if bulk_run:
        bulk_op.execute()

    return errors_list


def wallet_journal(keys=None):
    """

    :param keys: [("personal", key_id, vcode), (), ...] or None for jf_wallet
    :return:
    """

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    if not keys:
        # Default Refreshes
        keys = [("jf_wallet", secrets["jf_key_id"], secrets["jf_vcode"])]
    bulk_op = g.mongo.db.wallet_journal.initialize_unordered_bulk_op()
    bulk_run = False
    for service in keys:
        if service[0] == "jf_wallet":
            db_wallet_journal_cache = g.mongo.db.caches.find_one({"_id": service[0]})
        else:
            db_wallet_journal_cache = g.mongo.db.key_caches.find_one({"_id": "wallet_journal"})
        if not db_wallet_journal_cache or db_wallet_journal_cache.get("cached_until", 0) < time.time():
            if service[0] == "jf_wallet":
                xml_wallet_journal_payload = {
                    "keyID": service[1],
                    "vCode": service[2],
                    "accountKey": base_config["jf_account_key"]
                }
            else:
                xml_wallet_journal_payload = {
                    "keyID": service[1],
                    "vCode": service[2]
                }
            xml_wallet_journal_response = requests.get("https://api.eveonline.com/corp/WalletJournal.xml.aspx",
                                                       data=xml_wallet_journal_payload, headers=xml_headers)
            # XML Parse
            try:
                xml_wallet_journal_tree = ElementTree.fromstring(xml_wallet_journal_response.text)
            except ElementTree.ParseError:
                print(xml_wallet_journal_response.text)
                return None

            # Store in database
            xml_time_pattern = "%Y-%m-%d %H:%M:%S"
            g.mongo.db.caches.update({"_id": service[0]}, {"cached_until": int(calendar.timegm(
                time.strptime(xml_wallet_journal_tree[2].text, xml_time_pattern))),
                "cached_str": xml_wallet_journal_tree[2].text}, upsert=True)
            for transaction in xml_wallet_journal_tree[1][0]:
                bulk_run = True
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


def character_sheet(keys):
    """

    :param keys: [(key_id, vcode, character_id), (), ....]
    :return:
    """

    bulk_op = g.mongo.db.character_sheet.initialize_unordered_bulk_op()
    bulk_run = False
    for service in keys:
        db_character_sheet_cache = g.mongo.db.key_caches.find_one({"_id": service[2]})
        if not db_character_sheet_cache or db_character_sheet_cache.get("character_sheet", 0) < time.time():
            xml_character_sheet_payload = {
                "keyID": service[0],
                "vCode": service[1],
                "characterID": service[2]
            }
            xml_character_sheet_response = requests.get("https://api.eveonline.com/char/CharacterSheet.xml.aspx",
                                                        data=xml_character_sheet_payload, headers=xml_headers)
            # XML Parse
            try:
                xml_character_sheet_tree = ElementTree.fromstring(xml_character_sheet_response.text)
            except ElementTree.ParseError:
                print(xml_character_sheet_response.text)
                return None

            # Store in database
            xml_time_pattern = "%Y-%m-%d %H:%M:%S"
            g.mongo.db.key_caches.update({"_id": service[2]}, {
                "character_sheet": int(calendar.timegm(
                    time.strptime(xml_character_sheet_tree[2].text, xml_time_pattern))),
                "character_sheet_str": xml_character_sheet_tree[2].text,
                "key": int(service[0])
            }, upsert=True)

            for skill in xml_character_sheet_tree[1][33]:
                bulk_run = True
                bulk_op.find({"_id": service[2]}).upsert().update(
                    {
                        "$set": {
                            "skills." + skill.attrib["typeID"]: {
                                "skill_points": int(skill.attrib["skillpoints"]),
                                "level": int(skill.attrib["level"])
                            }
                        }
                    })

    if bulk_run:
        bulk_op.execute()


def security_characters():
    db_security_characters_cache = g.mongo.db.caches.find_one({"_id": "security_characters"})
    bulk_op = g.mongo.db.security_characters.initialize_unordered_bulk_op()
    bulk_run = False
    if not db_security_characters_cache or db_security_characters_cache["cached_until"] < time.time():
        xml_security_characters_payload = {
            "keyID": secrets["main_key_id"],
            "vCode": secrets["main_vcode"],
            "extended": 1
        }
        xml_security_characters_response = requests.get("https://api.eveonline.com/corp/MemberTracking.xml.aspx",
                                                        data=xml_security_characters_payload, headers=xml_headers)
        # XML Parse
        try:
            xml_security_characters_tree = ElementTree.fromstring(xml_security_characters_response.text)
        except ElementTree.ParseError:
            print(xml_security_characters_response.text)
            return None

        # Store in database
        if xml_security_characters_tree[1].tag == "error":
            raise error_handling.ConfigError("Main Corp API is not valid.")

        g.mongo.db.caches.update({"_id": "security_characters"}, {
            "cached_until": conversions.xml_time(xml_security_characters_tree[2].text),
            "cached_str": xml_security_characters_tree[2].text
        }, upsert=True)
        for corp_char in xml_security_characters_tree[1][0]:
            bulk_run = True
            bulk_op.find({"_id": int(corp_char.attrib["characterID"])}).upsert().update(
                {"$set": {
                    "name": corp_char.attrib["name"],
                    "join_time": conversions.xml_time(corp_char.attrib["startDateTime"]),
                    "title": corp_char.attrib["title"],
                    "log_on_time": conversions.xml_time(corp_char.attrib.get("logonDateTime")),
                    "log_off_time": conversions.xml_time(corp_char.attrib.get("logoffDateTime")),
                    "last_location_id": corp_char.attrib.get("locationID"),
                    "last_location_str": corp_char.attrib.get("location"),
                    "last_ship_id": corp_char.attrib.get("shipTypeID"),
                    "last_ship_str": corp_char.attrib.get("shipType")
                }})
    if bulk_run:
        # Clear entire database first
        g.mongo.db.security_characters.remove({})
        bulk_op.execute()
