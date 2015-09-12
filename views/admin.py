from flask import Blueprint, render_template, g, request
from views.auth import requires_sso

admin = Blueprint("admin", __name__, template_folder="templates")


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
                                           "$push":
                                               {
                                                   "users": request.form.get("_id")
                                               }
                                       })
        elif request.form.get("action") == "delete":
            g.mongo.db.eve_auth.update({"_id": request.form.get("role").strip()},
                                       {
                                           "$pull":
                                               {
                                                   "users": request.form.get("_id")
                                               }
                                       })

    for user in g.mongo.db.users.find():
        user_list.append([user["character_name"], user["_id"], user["corporation_name"], user["alliance_name"]])
    for role in g.mongo.db.eve_auth.find():
        role_list.append([role["_id"], [(x, g.mongo.db.users.find_one({"_id": x}).get("character_name"))
                                        for x in role["users"] if g.mongo.db.users.find_one({"_id": x})]])

    return render_template("site_admin.html", user_list=user_list, role_list=role_list)
