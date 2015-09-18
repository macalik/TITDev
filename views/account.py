import json

from flask import Blueprint, render_template, session, request, g

from views.auth import requires_sso
from helpers import caches

account = Blueprint("account", __name__, template_folder="templates")


@account.route("/", methods=["GET", "POST"])
@requires_sso(None)
def home():

    # API Module
    error_list = []
    if request.method == "POST":
        if request.form.get("action") == "add":
            error_list = caches.api_keys([(request.form.get("key_id"), request.form.get("vcode"))])
        elif request.form.get("action") == "remove":
            print(request.form.get("key_id"))
            print(session["CharacterOwnerHash"])
            g.mongo.db.api_keys.update({"_id": session["CharacterOwnerHash"]},
                                       {
                                           "$pull": {
                                               "keys": {"key_id": int(request.form.get("key_id"))}
                                           }
                                       })

    # List of roles
    given_roles = []
    for role in g.mongo.db.eve_auth.find():
        if session["CharacterOwnerHash"] in role["users"]:
            given_roles.append(role["_id"])

    associated_keys = []
    # List of characters
    db_key_doc = g.mongo.db.api_keys.find_one({"_id": session["CharacterOwnerHash"]})
    if db_key_doc:
        for key in db_key_doc["keys"]:
            associated_keys.append([key["character_id"], key["character_name"], key["key_id"], key["vcode"],
                                    key["cached_str"]])

    # User Information
    db_user_info = g.mongo.db.users.find_one({"_id": session["CharacterOwnerHash"]})
    user_info = [db_user_info["_id"], db_user_info["character_name"], db_user_info["corporation_name"],
                 db_user_info["alliance_name"]]

    # Images
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    image_list = [base_config["image_server"] + "Character/" + str(db_user_info["character_id"]) + "_256.jpg",
                  base_config["image_server"] + "Corporation/" + str(db_user_info["corporation_id"]) + "_128.png",
                  base_config["image_server"] + "Alliance/" + str(db_user_info["alliance_id"]) + "_128.png"]

    # Away from EVE
    if request.method == "GET":
        if request.args.get("action") == "enable":
            g.mongo.db.personals.update({"_id": session["CharacterOwnerHash"],
                                         "character_name": db_user_info["character_name"],
                                         "character_id": db_user_info["character_id"]}, {
                "$set":
                    {
                        "corporation_id": db_user_info["corporation_id"],
                        "vacation": request.args.get("text")
                    }
            }, upsert=True)
        elif request.args.get("action") == "disable":
            g.mongo.db.personals.update({"_id": session["CharacterOwnerHash"],
                                         "character_name": db_user_info["character_name"],
                                         "character_id": db_user_info["character_id"]}, {
                "$unset":
                    {
                        "vacation": request.args.get("text")
                    }
            })

    db_personal = g.mongo.db.personals.find_one({"_id": session["CharacterOwnerHash"], "vacation": {"$exists": True}})
    if db_personal:
        vacation = True
        vacation_text = db_personal["vacation"]
    else:
        vacation = False
        vacation_text = ""

    return render_template("account.html", error_list=error_list, given_roles=given_roles,
                           associated_keys=associated_keys, user_info=user_info, image_list=image_list,
                           vacation=vacation, vacation_text=vacation_text)
