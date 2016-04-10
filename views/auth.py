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
user_agent = "TiT Corp Website by Kazuki Ishikawa"

if os.environ.get("EXTERNAL"):
    secrets = {
        "client_id": os.environ["client_id"],
        "secret_key": os.environ["secret_key"],
        "redirect_uri": os.environ["redirect_uri"],
        "discord_client_id": os.environ["discord_client_id"],
        "discord_secret_key": os.environ["discord_secret_key"],
        "discord_redirect_uri": os.environ["discord_redirect_uri"]
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
                    "User-Agent": user_agent
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
                                                "alliance_id": int(float(xml_tree[1][10].text)),
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


def highest_auth(user_id):
    db_user = g.mongo.db.users.find_one({"_id": user_id})

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    if db_user["corporation_id"] == base_config["corporation_id"]:
        return "corporation"
    elif db_user["alliance_id"] == base_config["alliance_id"]:
        return "alliance"
    else:
        return None


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
        try:
            if len(forum_response.json()) == 1:
                forum_id = forum_response.json()[0]["id"]
                forum_username = forum_response.json()[0]["username"]
                g.mongo.db.users.update({"_id": session["CharacterOwnerHash"]},
                                        {"$set": {"forum_id": forum_id, "forum_username": forum_username}})
                used_forum = True
        except json.JSONDecodeError:
            print(forum_response.text)
            print("API Connection Failed")
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


def auth_crest(code, refresh=False):
    # Code is CharacterOwnerHash on refresh and actual authorization code on non-refresh

    # SSO Authentication
    auth_headers = {
        "Authorization": "Basic " + str(base64.b64encode(
            bytes(secrets["client_id"] + ":" + secrets["secret_key"], "utf8")))[2:-1],
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "login.eveonline.com"
    }
    if not refresh:
        given_user = None
        auth_payload = {
            "grant_type": "authorization_code",
            "code": code
        }
    else:
        given_user = g.mongo.db.users.find_one({"_id": code})
        if given_user:
            auth_payload = {
                "grant_type": "refresh_token",
                "refresh_token": given_user["refresh_token"]
            }
        else:
            return None, None

    auth_response = requests.post("https://login.eveonline.com/oauth/token",
                                  data=auth_payload, headers=auth_headers)
    # Abort on EVE API server errors
    try:
        auth_token = auth_response.json()
        if not auth_token.get("access_token"):
            print(auth_token)
            g.mongo.db.users.update({"_id": code},
                                    {
                                        "$set": {
                                            "corporation_id": 0,
                                            "corporation_name": "",
                                            "alliance_id": 0,
                                            "alliance_name": "",
                                            "cached_until": 0
                                        }
                                    })
            if given_user and given_user.get("discord_id"):
                g.redis.publish("titdev-auth", "#" + given_user["discord_id"] + " None")
            return None, None
    except ValueError:
        auth_token = None
        if not refresh:
            abort(400)
        else:
            g.mongo.db.users.update({"_id": code},
                                    {
                                        "$set": {
                                            "corporation_id": 0,
                                            "corporation_name": "",
                                            "alliance_id": 0,
                                            "alliance_name": "",
                                            "cached_until": 0
                                        }
                                    })
            if given_user and given_user.get("discord_id"):
                g.redis.publish("titdev-auth", "#" + given_user["discord_id"] + " None")
            return None, None

    # CREST Authentication
    character_headers = {
        "User-Agent": user_agent,
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
            "User-Agent": user_agent
        }
        xml_char_response = requests.get("https://api.eveonline.com/eve/CharacterInfo.xml.aspx",
                                         data=xml_char_payload, headers=xml_char_headers)
        # XML Parse
        xml_tree = ElementTree.fromstring(xml_char_response.text)

        # Update Database
        xml_time_pattern = "%Y-%m-%d %H:%M:%S"
        if refresh:
            g.mongo.db.users.update({"_id": crest_char["CharacterOwnerHash"]},
                                    {
                                        "$set": {
                                            "character_id": crest_char["CharacterID"],
                                            "character_name": crest_char["CharacterName"],
                                            "corporation_id": int(xml_tree[1][7].text),
                                            "corporation_name": xml_tree[1][8].text.strip(),
                                            "alliance_id": int(float(xml_tree[1][10].text)),
                                            "alliance_name": xml_tree[1][11].text.strip(),
                                            "refresh_token": auth_token["refresh_token"],
                                            "cached_until": int(calendar.timegm(time.strptime(xml_tree[2].text,
                                                                                              xml_time_pattern)))
                                        }
                                    }, upsert=True)
            if db_user and db_user.get("discord_id"):
                g.redis.publish("titdev-auth", "#" + db_user["discord_id"] + " " +
                                highest_auth(crest_char["CharacterOwnerHash"]))

        else:
            g.mongo.db.users.update({"_id": crest_char["CharacterOwnerHash"]},
                                    {
                                        "$set": {
                                            "character_id": crest_char["CharacterID"],
                                            "character_name": crest_char["CharacterName"],
                                            "corporation_id": int(xml_tree[1][7].text),
                                            "corporation_name": xml_tree[1][8].text.strip(),
                                            "alliance_id": int(float(xml_tree[1][10].text)),
                                            "alliance_name": xml_tree[1][11].text.strip(),
                                            "refresh_token": auth_token["refresh_token"],
                                            "last_sign_on": int(time.time()),
                                            "cached_until": int(calendar.timegm(time.strptime(xml_tree[2].text,
                                                                                              xml_time_pattern)))
                                        }
                                    }, upsert=True)
            if db_user and db_user.get("discord_id"):
                g.redis.publish("titdev-auth", "#" + db_user["discord_id"] + " " +
                                highest_auth(crest_char["CharacterOwnerHash"]))

        # Refresh current user
        db_user = g.mongo.db.users.find_one({"_id": crest_char["CharacterOwnerHash"]})

    return db_user, crest_char


def auth_discord(user, code=None):
    # No code means use refresh code
    auth_headers = {
        "Authorization": "Basic " + str(base64.b64encode(
            bytes(secrets["discord_client_id"] + ":" + secrets["discord_secret_key"], "utf8")))[2:-1],
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "discordapp.com"
    }
    if code:
        auth_payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": secrets["discord_redirect_uri"]
        }
    else:
        given_user = g.mongo.db.users.find_one({"_id": user})
        if given_user and given_user.get("discord_refresh_token"):
            auth_payload = {
                "grant_type": "refresh_token",
                "refresh_token": given_user["discord_refresh_token"]
            }
        else:
            return
    auth_response = requests.post("https://discordapp.com/api/oauth2/token",
                                  data=auth_payload, headers=auth_headers)

    try:
        auth_token = auth_response.json()
        if not auth_token.get("access_token"):
            print(auth_token)
            return
    except ValueError:
        auth_token = None
        if code:
            abort(400)
        else:
            g.mongo.db.users.update({"_id": user},
                                    {
                                        "$set": {
                                            "discord_refresh_token": None
                                        }
                                    })
            return
    else:
        if code:
            g.mongo.db.users.update({"_id": user},
                                    {
                                        "$set": {
                                            "discord_refresh_token": auth_token["refresh_token"]
                                        }
                                    })

    # Check if has joined guild
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    info_headers = {
        "User-Agent": user_agent,
        "Authorization": "Bearer " + auth_token["access_token"],
        "Host": "discordapp.com"
    }
    discord_guilds_response = requests.get("https://discordapp.com/api/users/@me/guilds",
                                           headers=info_headers)
    guild_list = discord_guilds_response.json()
    joined = False
    for guild in guild_list:
        if guild["id"] == str(base_config["discord_server_id"]):
            joined = True
    if not joined:
        discord_prefs = g.mongo.db.preferences.find_one({"_id": "discord"})
        if discord_prefs and discord_prefs.get("invite_id"):
            requests.post("https://discordapp.com/api/invites/" +
                          discord_prefs.get("invite_id"), headers=info_headers)

    # Get ID
    discord_id_response = requests.get("https://discordapp.com/api/users/@me", headers=info_headers)
    discord_id = discord_id_response.json()["id"].strip()
    g.mongo.db.users.update({"_id": user},
                            {
                                "$set": {
                                    "discord_id": discord_id
                                }
                            })

    # Refresh roles
    all_roles = []
    applicable_roles = []
    super_admin = False
    for role in g.mongo.db.eve_auth.find():
        all_roles.append(role["_id"])
        if role["_id"] != "super_admin" and user in role["users"]:
            applicable_roles.append(role["_id"])
        elif role["_id"] == "super_admin" and user in role["users"]:
            super_admin = True
    if super_admin:
        g.redis.publish('titdev-auth', " ".join([discord_id] + all_roles))
    else:
        g.redis.publish('titdev-auth', " ".join([discord_id] + applicable_roles))
    g.redis.publish("titdev-auth", "#" + discord_id + " " + highest_auth(user))


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

        db_user, crest_char = auth_crest(code)

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


@auth.route("/discord_redirect")
def discord_redirect():
    return redirect("https://discordapp.com/api/oauth2/authorize" +
                    "?response_type=code" +
                    "&redirect_uri=" + secrets["discord_redirect_uri"] +
                    "&client_id=" + secrets["discord_client_id"] +
                    "&scope=identify guilds guilds.join" +
                    "&state=" + state)


@auth.route("/discord_endpoint")
def discord_response():
    if request.args.get("state") == state:  # Check against returned state
        code = request.args.get("code")

        auth_discord(session["CharacterOwnerHash"], code)

    return redirect(url_for("account.home"))


@auth.route("/log_out")
def log_out():
    if session.get("CharacterOwnerHash"):
        current_user = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})

        if current_user and current_user.get("email"):
            forum_edit(current_user, "log_out")

    session.clear()
    return redirect(url_for("home"))
