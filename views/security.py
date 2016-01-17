import json
import itertools
import time

from flask import Blueprint, render_template, g, redirect, url_for

from views.auth import requires_sso
from helpers import caches

security = Blueprint("security", __name__, template_folder="templates")


@security.route("/")
@requires_sso("security_officer")
def home():
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    id_to_name = {}
    for user_info in g.mongo.db.users.find({"corporation_id": base_config["corporation_id"]}):
        id_to_name[user_info["_id"]] = user_info["character_name"]

    api_table = []
    characters = set()
    for api_user in g.mongo.db.api_keys.find({"_id": {"$in": list(id_to_name.keys())}}):
        user_characters = [x["character_name"] for x in api_user["keys"]]
        invalid = all([y.get("valid", True) for y in api_user["keys"]])
        api_table.append([invalid, api_user["_id"], id_to_name[api_user["_id"]], ", ".join(user_characters)])
        characters.update(user_characters)

    caches.security_characters()

    time_format = "%Y-%m-%d %H:%M:%S"
    missing_apis = []
    for corp_character in g.mongo.db.security_characters.find():
        if corp_character["name"] not in characters:
            missing_apis.append([
                corp_character["name"],
                time.strftime(time_format, time.gmtime(corp_character["join_time"])),
                time.strftime(time_format, time.gmtime(corp_character["log_on_time"])),
                time.strftime(time_format, time.gmtime(corp_character["log_off_time"]))
            ])
    missing_count = len(missing_apis)
    all_count = g.mongo.db.security_characters.count()

    return render_template("security.html", api_table=api_table, missing_apis=missing_apis, missing_count=missing_count,
                           all_count=all_count)


@security.route("/user/<path:site_id>")
def user(site_id=""):
    if not site_id:
        return redirect(url_for("security.home"))
    else:
        site_id = site_id.strip()

    user_apis = g.mongo.db.api_keys.find_one({"_id": site_id})
    user_info = g.mongo.db.users.find_one({"_id": site_id})
    if not user_apis and user_info:
        return redirect(url_for("security.home"))

    api_table = []
    id_list = []
    for api_key in user_apis["keys"]:
        api_table.append([api_key["character_name"], api_key["character_id"], api_key["key_id"], api_key["vcode"],
                          api_key["cached_str"], api_key.get("valid", True)])
        id_list.append(api_key["character_id"])

    time_format = "%Y-%m-%d %H:%M:%S"

    location_table = []
    for security_character in g.mongo.db.security_characters.find({"_id": {"$in": id_list}}):
        location_table.append([security_character["name"], security_character["last_location_str"],
                               security_character["last_ship_str"],
                               time.strftime(time_format, time.gmtime(security_character["log_on_time"])),
                               time.strftime(time_format, time.gmtime(security_character["log_off_time"]))])

    user_table = [site_id, user_info["character_name"],
                  time.strftime(time_format, time.gmtime(user_info["last_sign_on"]))]

    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    image = base_config["image_server"] + "/Character/" + str(user_info["character_id"]) + "_256.jpg"

    return render_template("security_user.html", api_table=api_table, user_table=user_table, image=image,
                           site_log_in=time.strftime(time_format, time.gmtime(user_info["last_sign_on"])),
                           site_id=site_id, character_name=user_info["character_name"], location_table=location_table)
