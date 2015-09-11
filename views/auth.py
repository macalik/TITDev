import random
import string
import json
import os
import base64
import time
import calendar
from functools import wraps

from defusedxml import ElementTree
from flask import redirect, request, Blueprint, abort, g, session, url_for
import requests

auth = Blueprint("auth", __name__, template_folder="templates")

state = "".join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(18))

if os.environ.get("HEROKU"):
    secrets = {
        "client_id": os.environ["client_id"],
        "secret_key": os.environ["secret_key"],
        "redirect_uri": os.environ["redirect_uri"]
    }
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)


def requires_sso(level):
    def decorator(function):
        @wraps(function)
        def decorated_function(*args, **kwargs):
            # Check session hash
            if session.get("CharacterOwnerHash", None):
                db_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})
            else:
                # Redirect if not logged in
                return redirect(url_for("auth.sso_redirect"))

            # Check cache
            if not db_user:
                # Redirect if user doesn't exist
                return redirect(url_for("auth.sso_redirect"))
            elif db_user["cached_until"] < time.time():
                # Refresh character if cache expires.
                # XML Character
                xml_char_payload = {
                    "characterID": session["CharacterID"]
                }
                xml_char_headers = {
                    "User-Agent": "TiT Corp Website by Kazuki Ishikawa"
                }
                xml_char_response = requests.get("https://api.eveonline.com/eve/CharacterInfo.xml.aspx",
                                                 data=xml_char_payload, headers=xml_char_headers)
                # XML Parse
                xml_tree = ElementTree.fromstring(xml_char_response.text)

                # Update Database
                xml_time_pattern = "%Y-%m-%d %H:%M:%S"
                g.mongo.db.users.update({"_id": db_user["_id"]},
                                        {"$set":
                                            {
                                                "corporation_id": int(xml_tree[1][7].text),
                                                "alliance_id": int(xml_tree[1][10].text),
                                                "cached_until": int(calendar.timegm(time.strptime(xml_tree[2].text,
                                                                                                  xml_time_pattern)))
                                            }})

            if not auth_check(level):
                abort(403)

            return function(*args, **kwargs)
        return decorated_function
    return decorator


def auth_check(level):
    db_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})  # User must exist before auth check
    db_eve_auth = g.mongo.db.eve_auth.find_one({"_id": level})

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    if level == "corporation":
        if db_user["corporation_id"] == base_config["corporation_id"]:
            return True
    elif level == "alliance":
        if db_user["alliance_id"] == base_config["alliance_id"]:
            return True
    elif db_eve_auth:  # Database Groups
        if db_user["character_id"] in db_eve_auth["users"]:
            return True
    elif level is None:
        return True

    return False


@auth.route("/")
def sso_redirect():
    return redirect("https://login.eveonline.com/oauth/authorize" +
                    "?response_type=code" +
                    "&redirect_uri=" + secrets["redirect_uri"] +
                    "&client_id=" + secrets["client_id"] +
                    "&scope=publicData" +
                    "&state=" + state)


@auth.route("/sso_endpoint")
def sso_response():
    if request.args.get("state") == state:  # Check against returned state
        code = request.args.get("code")

        # SSO Authentication
        auth_headers = {
            "Authorization": "Basic " + str(base64.b64encode(
                bytes(secrets["client_id"] + ":" + secrets["secret_key"], "utf8")))[2:-1],
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "login.eveonline.com"
        }
        auth_payload = {
            "grant_type": "authorization_code",
            "code": code
        }
        auth_response = requests.post("https://login.eveonline.com/oauth/token",
                                      data=auth_payload, headers=auth_headers)
        # Abort on EVE API server errors
        try:
            auth_token = auth_response.json()
        except ValueError:
            auth_token = None
            print(auth_response.text)
            abort(400)

        # CREST Authentication
        character_headers = {
            "User-Agent": "TiT Corp Website by Kazuki Ishikawa",
            "Authorization": "Bearer " + auth_token["access_token"],
            "Host": "login.eveonline.com"
        }
        crest_char_response = requests.get("https://login.eveonline.com/oauth/verify", headers=character_headers)
        crest_char = crest_char_response.json()

        # Check user cache
        db_user = g.mongo.db.users.find_one({"_id": crest_char["CharacterOwnerHash"]})

        # Update character info if cache has finished or character doesn't exist.
        if not db_user or db_user["cached_until"] < time.time():
            # XML Character
            xml_char_payload = {
                "characterID": crest_char["CharacterID"]
            }
            xml_char_headers = {
                "User-Agent": "TiT Corp Website by Kazuki Ishikawa"
            }
            xml_char_response = requests.get("https://api.eveonline.com/eve/CharacterInfo.xml.aspx",
                                             data=xml_char_payload, headers=xml_char_headers)
            # XML Parse
            xml_tree = ElementTree.fromstring(xml_char_response.text)

            # Update Database
            xml_time_pattern = "%Y-%m-%d %H:%M:%S"
            g.mongo.db.users.update({"_id": crest_char["CharacterOwnerHash"]},
                                    {"character_id": crest_char["CharacterID"],
                                     "character_name": crest_char["CharacterName"],
                                     "corporation_id": int(xml_tree[1][7].text),
                                     "alliance_id": int(xml_tree[1][10].text),
                                     "refresh_token": auth_token["refresh_token"],
                                     "cached_until": int(calendar.timegm(time.strptime(xml_tree[2].text,
                                                                                       xml_time_pattern)))
                                     }, upsert=True)

            # Refresh current user
            db_user = g.mongo.db.users.find_one({"_id": crest_char["CharacterOwnerHash"]})

        # Update Session
        session["CharacterName"] = crest_char["CharacterName"]
        session["CharacterOwnerHash"] = crest_char["CharacterOwnerHash"]
        # !!Warning: Use these variables for UI ONLY. Not to be used for page auth!! #
        with open("configs/base.json", "r") as base_config_file:
            base_config = json.load(base_config_file)
        if db_user["corporation_id"] == base_config["corporation_id"]:
            session["UI_Corporation"] = True
        if db_user["alliance_id"] == base_config["alliance_id"]:
            session["UI_Alliance"] = True

        return redirect(url_for("home"))

    else:
        print("wrong state")
        abort(400)


@auth.route("/log_out")
def log_out():
    session.clear()
    return redirect(url_for("home"))
