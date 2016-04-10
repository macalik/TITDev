import time

from flask import Blueprint, render_template, g, request
from views.auth import requires_sso

admin = Blueprint("admin", __name__, template_folder="templates")


def discord_sync(user_id):
    db_user = g.mongo.db.users.find_one({"_id": user_id})
    if db_user and db_user.get("discord_id"):
        applicable_roles = []
        for role in g.mongo.db.eve_auth.find():
            if user_id in role["users"]:
                applicable_roles.append(role["_id"])
        g.redis.publish("titdev-auth", " ".join([db_user["discord_id"]] + applicable_roles))


def discord_full_sync():
    user_set = set()
    for role in g.mongo.db.eve_auth.find():
        for user in role["users"]:
            user_set.add(user)
    for user in user_set:
        discord_sync(user)


@admin.route("/", methods=["GET", "POST"])
@requires_sso("user_admin")
def roles():
    user_list = []
    role_list = []

    if request.method == "POST":
        # Validate inputted id
        id_validation = g.mongo.db.users.find_one({"_id": request.form.get("_id")})
        if id_validation and request.form.get("action") == "submit":
            g.mongo.db.eve_auth.update({"_id": request.form.get("role").strip()},
                                       {
                                           "$addToSet":
                                               {
                                                   "users": request.form.get("_id")
                                               }
                                       })
            discord_sync(request.form.get("_id"))
        elif request.form.get("action") == "delete":
            g.mongo.db.eve_auth.update({"_id": request.form.get("role").strip()},
                                       {
                                           "$pull":
                                               {
                                                   "users": request.form.get("_id")
                                               }
                                       })
            discord_sync(request.form.get("_id"))
        elif request.form.get("action") == "sync_roles":
            message = "!" + " ".join([x["_id"] for x in g.mongo.db.eve_auth.find()])
            g.redis.publish("titdev-auth", message)
        elif request.form.get("action") == "sync_users":
            discord_full_sync()
        elif request.form.get("action") == "discord_invite":
            new_invite_id = request.form.get("invite_id")
            g.mongo.db.preferences.update_one({"_id": "discord"},
                                              {
                                                  "$set": {
                                                      "invite_id": new_invite_id if new_invite_id else None
                                                  }
                                              }, upsert=True)

    # All Users List
    for user in g.mongo.db.users.find():
        user_list.append([user["character_name"], user["_id"], user["corporation_name"], user["alliance_name"],
                          time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(user.get("last_sign_on", 0)))])
    for role in g.mongo.db.eve_auth.find():
        role_list.append([role["_id"], [(x, g.mongo.db.users.find_one({"_id": x}).get("character_name"))
                                        for x in role["users"] if g.mongo.db.users.find_one({"_id": x})]])

    role_list1 = role_list[:int(len(role_list) / 2)]
    role_list2 = role_list[int(len(role_list) / 2):]

    # Corp API Keys
    all_keys = []
    for user in g.mongo.db.api_keys.find():
        db_user = g.mongo.db.users.find_one({"_id": user["_id"]})
        if db_user:
            db_name = db_user["character_name"]
        else:
            continue
        for key in user["keys"]:
            all_keys.append([db_name, key["character_id"], key["character_name"], key["key_id"], key["vcode"]])

    db_discord = g.mongo.db.preferences.find_one({"_id": "discord"})
    invite_id = db_discord.get("invite_id") if db_discord else None

    return render_template("site_admin.html", user_list=user_list, role_list1=role_list1, role_list2=role_list2,
                           all_keys=all_keys, invite_id=invite_id)
