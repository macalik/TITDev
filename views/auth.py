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

state = "TiTEveWebV1"

if os.environ.get("EXTERNAL"):
    secrets = {
        "client_id": os.environ["client_id"],
        "secret_key": os.environ["secret_key"],
        "redirect_uri": os.environ["redirect_uri"]
    }
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)


def requires_sso(*roles):
    def decorator(function):
        @wraps(function)
        def decorated_function(*args, **kwargs):
            # Check session hash
            if session.get("CharacterOwnerHash", None):
                db_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})
            else:
                # Redirect if not logged in
                if "forum" in roles:
                    session["redirect"] = "forum"
                    session["client_id"] = request.args.get("client_id")
                    session["redirect_uri"] = request.args.get("redirect_uri")
                    session["response_type"] = request.args.get("response_type")
                    session["scope"] = request.args.get("scope")
                    session["state"] = request.args.get("state")
                else:
                    session["redirect"] = request.path
                return redirect(url_for("auth.sso_redirect"))

            # Check cache
            if not db_user:
                # Redirect if user doesn't exist
                if "forum" in roles:
                    session["redirect"] = "forum"
                else:
                    session["redirect"] = request.path
                return redirect(url_for("auth.sso_redirect"))
            elif db_user["cached_until"] < time.time():
                # Refresh character if cache expires.
                # XML Character
                xml_char_payload = {
                    "characterID": db_user["character_id"]
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
                                                "corporation_name": xml_tree[1][8].text,
                                                "alliance_id": int(xml_tree[1][10].text),
                                                "alliance_name": xml_tree[1][11].text,
                                                "last_sign_on": int(time.time()),
                                                "cached_until": int(calendar.timegm(time.strptime(xml_tree[2].text,
                                                                                                  xml_time_pattern)))
                                            }})
                # Refresh db_user
                db_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})

                # Update UI
                # !!Warning: Use these variables for UI ONLY. Not to be used for page auth!! #
                with open("configs/base.json", "r") as base_config_file:
                    base_config = json.load(base_config_file)
                if db_user["corporation_id"] == base_config["corporation_id"]:
                    session["UI_Corporation"] = True
                else:
                    session["UI_Corporation"] = False
                    forum_edit(db_user, "log_out")
                if db_user["alliance_id"] == base_config["alliance_id"]:
                    session["UI_Alliance"] = True
                else:
                    session["UI_Alliance"] = False

            # Update UI after cache check
            session["UI_Roles"] = []
            for role_ui in g.mongo.db.eve_auth.find():
                if session["CharacterOwnerHash"] in role_ui["users"]:
                    session["UI_Roles"].append(role_ui["_id"])
            # Super User
            db_super_admins = g.mongo.db.eve_auth.find_one({"_id": "super_admin"})
            if db_super_admins and session["CharacterOwnerHash"] in db_super_admins["users"]:
                session["UI_Roles"] = []
                for role_ui in g.mongo.db.eve_auth.find():
                    session["UI_Roles"].append(role_ui["_id"])

            # Auth check after checking if user exists and updating cache if necessary
            if not any([auth_check(x) for x in roles]) and "forum" not in roles:
                abort(403)

            return function(*args, **kwargs)

        return decorated_function

    return decorator


def auth_check(role):
    db_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})  # User must exist before auth check
    db_eve_auth = g.mongo.db.eve_auth.find_one({"_id": role})
    db_super_admins = g.mongo.db.eve_auth.find_one({"_id": "super_admin"})

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    if db_super_admins and db_user["_id"] in db_super_admins["users"]:
        return True
    elif role == "corporation":
        if db_user["corporation_id"] == base_config["corporation_id"]:
            return True
    elif role == "alliance":
        if db_user["alliance_id"] == base_config["alliance_id"]:
            return True
    elif db_eve_auth:  # Database Groups
        if db_user["_id"] in db_eve_auth["users"]:
            return True
    elif role is None:
        return True

    return False


def forum_edit(current_user, action, *parameters):
    # current_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    used_forum = False
    if os.environ.get("EXTERNAL"):
        search_payload = {
            "api_key": os.environ.get("DISCOURSE_API_KEY"),
            "api_username": os.environ.get("DISCOURSE_API_USERNAME"),
            "filter": current_user.get("email", "")
        }
        api_payload = {
            "api_key": os.environ.get("DISCOURSE_API_KEY"),
            "api_username": os.environ.get("DISCOURSE_API_USERNAME")
        }
    else:
        with open("../Other-Secrets/TITDev.json") as log_out_secrets_file:
            log_out_secrets = json.load(log_out_secrets_file)
        search_payload = {
            "api_key": log_out_secrets.get("discourse_api_key"),
            "api_username": log_out_secrets.get("discourse_api_username"),
            "filter": current_user.get("email", "")
        }
        api_payload = {
            "api_key": log_out_secrets.get("discourse_api_key"),
            "api_username": log_out_secrets.get("discourse_api_username")
        }

    forum_id = None
    forum_username = None
    if not current_user.get("forum_id"):
        forum_response = requests.get(base_config["forum_url"] + "/admin/users/list/active.json",
                                      params=search_payload)
        if len(forum_response.json()) == 1:
            forum_id = forum_response.json()[0]["id"]
            forum_username = forum_response.json()[0]["username"]
            g.mongo.db.users.update({"_id": session["CharacterOwnerHash"]},
                                    {"$set": {"forum_id": forum_id, "forum_username": forum_username}})
            used_forum = True
    else:
        forum_id = current_user.get("forum_id")
        forum_username = current_user.get("forum_username").lower().strip()
        used_forum = True

    if used_forum:
        if action == "log_out":
            requests.post(base_config["forum_url"] + "/admin/users/" + str(forum_id) + "/log_out", params=api_payload)
        elif action == "email_edit":
            api_payload.update({"email": parameters[0]})
            requests.put(base_config["forum_url"] + "/users/" + forum_username + "/preferences/email",
                         params=api_payload)


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
            if not auth_token.get("access_token"):
                print(auth_token)
        except ValueError:
            auth_token = None
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
                                    {
                                        "$set": {
                                            "character_id": crest_char["CharacterID"],
                                            "character_name": crest_char["CharacterName"],
                                            "corporation_id": int(xml_tree[1][7].text),
                                            "corporation_name": xml_tree[1][8].text.strip(),
                                            "alliance_id": int(xml_tree[1][10].text),
                                            "alliance_name": xml_tree[1][11].text.strip(),
                                            "refresh_token": auth_token["refresh_token"],
                                            "last_sign_on": int(time.time()),
                                            "cached_until": int(calendar.timegm(time.strptime(xml_tree[2].text,
                                                                                              xml_time_pattern)))
                                        }
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
        else:
            session["UI_Corporation"] = False
        if db_user["alliance_id"] == base_config["alliance_id"]:
            session["UI_Alliance"] = True
        else:
            session["UI_Alliance"] = False
        session["UI_Roles"] = []
        for role in g.mongo.db.eve_auth.find():
            if session["CharacterOwnerHash"] in role["users"]:
                session["UI_Roles"].append(role["_id"])
        # Super User
        db_super_admins = g.mongo.db.eve_auth.find_one({"_id": "super_admin"})
        if db_super_admins and session["CharacterOwnerHash"] in db_super_admins["users"]:
            session["UI_Roles"] = []
            for role_ui in g.mongo.db.eve_auth.find():
                session["UI_Roles"].append(role_ui["_id"])

        if session.get("redirect") == "forum":
            session.pop("redirect", None)
            client_id = session.pop("client_id", None)
            redirect_uri = session.pop("redirect_uri", None)
            response_type = session.pop("response_type", None)
            scope = session.pop("scope", None)
            forum_state = session.pop("state", None)
            return redirect(url_for("authorize",
                                    client_id=client_id,
                                    redirect_uri=redirect_uri,
                                    response_type=response_type,
                                    scope=scope,
                                    state=forum_state))
        else:
            return redirect(session.pop("redirect", url_for("account.home")))

    else:
        abort(400)


@auth.route("/log_out")
def log_out():
    if session.get("CharacterOwnerHash"):
        current_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})

        if current_user and current_user.get("email"):
            forum_edit(current_user, "log_out")

    session.clear()
    return redirect(url_for("home"))
