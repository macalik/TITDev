import json

from flask import Blueprint, render_template, request, session, g, redirect, url_for, flash
from pymongo import ReturnDocument
from bson.objectid import ObjectId
import bson

from views.auth import requires_sso, auth_check
from helpers import caches

recruitment = Blueprint("recruitment", __name__, template_folder="templates")


@recruitment.route("/", methods=["GET", "POST"])
def home():
    recruitment_prefs = g.mongo.db.preferences.find_one({"_id": "recruitment"})
    if recruitment_prefs:
        status = recruitment_prefs.get("status", "closed")
        info = recruitment_prefs.get("info", "No information available.").splitlines()
    else:
        status = "closed"
        info = ["No information available."]

    if status == "restricted":
        key = request.form.get("key")
        if key:
            return redirect(url_for("recruitment.form", key=key))
    elif status == "open":
        if request.form.get("action") == "apply":
            return redirect(url_for("recruitment.apply"))

    return render_template("recruitment.html", status=status, info=info)


@recruitment.route("/apply", methods=["GET", "POST"])
@requires_sso(None)
def apply():
    application = g.mongo.db.applications.find_one({"owner": session["CharacterOwnerHash"]})
    if application:
        return redirect(url_for("recruitment.form", key=application["_id"]))
    else:
        new_app = g.mongo.db.applications.insert_one({})
        return redirect(url_for("recruitment.form", key=new_app.inserted_id))


@recruitment.route("/form/<key>", methods=["GET", "POST"])
@requires_sso(None)
def form(key):
    # Highest Role
    role = None
    if auth_check("security_officer"):
        role = "security_officer"
    elif auth_check("recruiter"):
        role = "recruiter"

    # Recruitment Info
    try:
        if request.form.get("action") == "submit":
            insert = {}
            for question_key, value in request.form.items():
                if question_key not in ["action", "submitted"]:
                    key_split = question_key.split("_")
                    if key_split[1] == "bool":
                        insert[key_split[0]] = value == "True"
                    else:
                        insert[key_split[0]] = value.strip()
            app_info = g.mongo.db.applications.find_one_and_update({"_id": ObjectId(key)},
                                                                   {"$set": {"questions": insert,
                                                                             "submitted": True}},
                                                                   return_document=ReturnDocument.AFTER)
            if request.form.get("submitted") == "True":
                flash("Application edited", "success")
            else:
                flash("Application submitted", "success")
        elif request.form.get("action") in [
            "process", "interview", "accept", "reject", "release"
        ] and role == "security_officer":
            status_strings = {
                "process": "Processing",
                "interview": "Interview Required",
                "accept": "Accepted",
                "reject": "Rejected",
                "release": "Submitted" if request.form.get("submitted") == "True" else "Not Submitted"
            }
            app_info = g.mongo.db.applications.find_one_and_update(
                    {"_id": ObjectId(key)},
                    {
                        "$set": {
                            "status": status_strings[request.form.get("action")],
                            "reason": request.form.get("reason")
                        }
                    },
                    return_document=ReturnDocument.AFTER)
        elif request.form.get("action") == "flag" and role:
            app_info = g.mongo.db.applications.find_one_and_update(
                    {"_id": ObjectId(key)},
                    {
                        "$set":
                            {
                                "met_recruiter": request.form.get("met_recruiter") == "False"
                            }
                    }, return_document=ReturnDocument.AFTER)
        elif request.form.get("action") == "delete" and role == "security_officer":
            if request.form.get("confirm") == key:
                g.mongo.db.applications.delete_one({"_id": ObjectId(key)})
                flash("Application Deleted", "success")
                return redirect(url_for("recruitment.home"))
            else:
                app_info = g.mongo.db.applications.find_one({"_id": ObjectId(key)})
                flash("Key doesn't match", "error")
        elif request.form.get("action") == "officer_edit" and role == "security_officer":
            app_info = g.mongo.db.applications.find_one_and_update(
                    {"_id": ObjectId(key)},
                    {
                        "$set":
                            {
                                "officer_notes": request.form.get("officer_edit")
                            }
                    }, return_document=ReturnDocument.AFTER)
            flash("Officer Notes Edited", "success")
        elif request.form.get("action") == "recruiter_edit" and role:
            app_info = g.mongo.db.applications.find_one_and_update(
                    {"_id": ObjectId(key)},
                    {
                        "$set":
                            {
                                "recruiter_notes": request.form.get("recruiter_edit")
                            }
                    }, return_document=ReturnDocument.AFTER)
            flash("Recruiter Notes Edited", "success")
        elif request.form.get("action") == "recruiter":
            app_info = g.mongo.db.applications.find_one_and_update(
                    {"_id": ObjectId(key)},
                    {
                        "$set":
                            {
                                "recruiter": request.form.get("recruiter")
                            }
                    }, return_document=ReturnDocument.AFTER)
            flash("Recruiter Changed", "success")
        else:
            app_info = g.mongo.db.applications.find_one({"_id": ObjectId(key)})
    except bson.errors.InvalidId:
        flash("Invalid Key", "error")
        return redirect(url_for("recruitment.home"))

    if app_info:
        key_owner = app_info.get("owner")
        if not key_owner:
            g.mongo.db.applications.update_one({"_id": ObjectId(key)}, {"$set": {
                "owner": session["CharacterOwnerHash"],
                "character_name": session["CharacterName"]
            }})
            key_owner = session["CharacterOwnerHash"]
        if key_owner == session["CharacterOwnerHash"] or role:
            app_key = key.strip()
            app_status = app_info.get("status", "Not submitted")
            app_reason = app_info.get("reason")
        else:
            flash("Key Already Used", "error")
            return redirect(url_for("recruitment.home"))
    else:
        flash("Key Not Found", "error")
        return redirect(url_for("recruitment.home"))

    # APIs
    error_list = []
    if request.method == "POST":
        if request.form.get("action") == "add":
            error_list = caches.api_keys([(request.form.get("key_id"), request.form.get("vcode"))],
                                         dashboard_id=key_owner)
        elif request.form.get("action") == "remove":
            g.mongo.db.api_keys.update_one({"_id": key_owner},
                                           {
                                               "$pull": {
                                                   "keys": {"key_id": int(request.form.get("key_id"))}
                                               }
                                           })

    associated_keys = []
    # List of characters
    db_key_doc = g.mongo.db.api_keys.find_one({"_id": key_owner})
    if db_key_doc:
        for key in db_key_doc["keys"]:
            associated_keys.append([key["character_id"], key["character_name"], key["key_id"], key["vcode"],
                                    key["cached_str"], key.get("valid", True)])

    # User Information
    db_user_info = g.mongo.db.users.find_one({"_id": key_owner})
    user_info = [db_user_info["_id"], db_user_info["character_name"], db_user_info["corporation_name"],
                 db_user_info["alliance_name"]]

    # Images
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    image_list = [base_config["image_server"] + "/Character/" + str(db_user_info["character_id"]) + "_256.jpg",
                  base_config["image_server"] + "/Corporation/" + str(db_user_info["corporation_id"]) + "_128.png",
                  base_config["image_server"] + "/Alliance/" + str(db_user_info["alliance_id"]) + "_128.png"]
    access_mask = base_config["access_mask"]

    # Questions
    question_list = g.mongo.db.app_questions.find()
    question_pre_table = []
    question_table = []
    if question_list:
        for question in question_list:
            if question["bool"]:
                question_type = "bool"
            elif question["long"]:
                question_type = "long"
            else:
                question_type = "text"
            question_pre_table.append([question["text"], question_type,
                                       "{0}_{1}".format(str(question["_id"]), question_type)])
    answers = app_info.get("questions")
    for row in question_pre_table:
        if answers:
            reply = answers.get(row[2].split("_")[0], "")
            if row[1] == "long":
                question_table.append(row + [reply, reply.splitlines()])
            else:
                question_table.append(row + [reply])
        else:
            question_table.append(row + [""])

    # Recruiters
    recruiter_users = g.mongo.db.eve_auth.find_one({"_id": "recruiter"})
    recruiter_list = [user["character_name"] for user in g.mongo.db.users.find(
            {"_id": {"$in": recruiter_users["users"]}})]

    return render_template("recruitment_form.html", error_list=error_list, image_list=image_list,
                           access_mask=access_mask, user_info=user_info, associated_keys=associated_keys,
                           app_key=app_key, app_status=app_status, app_reason=app_reason, role=role,
                           recruiter_notes=[app_info.get("recruiter_notes", "").splitlines(),
                                            app_info.get("recruiter_notes", "")],
                           officer_notes=[app_info.get("officer_notes", "").splitlines(),
                                          app_info.get("officer_notes", "")],
                           question_table=question_table,
                           met_recruiter=app_info.get("met_recruiter", False),
                           submitted=app_info.get("submitted", False),
                           recruiter_list=recruiter_list, app_recruiter=app_info.get("recruiter"))


@recruitment.route("/admin", methods=["GET", "POST"])
@requires_sso("security_officer", "recruiter")
def admin():
    if request.form.get("action") == "add":
        g.mongo.db.app_questions.insert_one({
            "text": request.form.get("text"),
            "long": bool(request.form.get("long", False)),
            "bool": bool(request.form.get("bool", False))
        })
    elif request.form.get("action") == "remove":
        g.mongo.db.app_questions.delete_one({"_id": ObjectId(request.form.get("id"))})

    if request.form.get("action") == "restricted":
        recruitment_prefs = g.mongo.db.preferences.find_one_and_update({"_id": "recruitment"},
                                                                       {"$set": {"status": "restricted"}},
                                                                       upsert=True,
                                                                       return_document=ReturnDocument.AFTER)
    elif request.form.get("action") == "open":
        recruitment_prefs = g.mongo.db.preferences.find_one_and_update({"_id": "recruitment"},
                                                                       {"$set": {"status": "open"}},
                                                                       upsert=True,
                                                                       return_document=ReturnDocument.AFTER)
    elif request.form.get("action") == "closed":
        recruitment_prefs = g.mongo.db.preferences.find_one_and_update({"_id": "recruitment"},
                                                                       {"$set": {"status": "closed"}},
                                                                       upsert=True,
                                                                       return_document=ReturnDocument.AFTER)
    elif request.form.get("action") == "info_edit":
        recruitment_prefs = g.mongo.db.preferences.find_one_and_update({"_id": "recruitment"},
                                                                       {"$set": {"info": request.form.get("info")}},
                                                                       upsert=True,
                                                                       return_document=ReturnDocument.AFTER)
    else:
        recruitment_prefs = g.mongo.db.preferences.find_one({"_id": "recruitment"})

    if recruitment_prefs:
        status = recruitment_prefs.get("status", "closed")
        info = recruitment_prefs.get("info", "")
    else:
        status = "closed"
        info = ""

    question_list = g.mongo.db.app_questions.find()
    question_table = [["Question", "Long", "Boolean"]]
    if question_list:
        for question in question_list:
            question_table.append([question["text"], question["long"], question["bool"], question["_id"]])
    return render_template("recruitment_admin.html", question_table=question_table, status=status, info=info)


@recruitment.route("/applications", methods=["GET", "POST"])
@requires_sso("security_officer", "recruiter")
def applications():
    recruitment_prefs = g.mongo.db.preferences.find_one({"_id": "recruitment"})
    restricted = True if recruitment_prefs and recruitment_prefs.get("status") == "restricted" else False
    if restricted:
        if request.form.get("action") == "create":
            g.mongo.db.applications.insert_one({"recruiter": session["CharacterName"]})
        elif request.form.get("action") == "delete":
            g.mongo.db.applications.delete_one({"_id": ObjectId(request.form.get("key"))})
        new_key_list = []
        for new_key in g.mongo.db.applications.find({"owner": {"$exists": False}}):
            new_key_list.append([new_key["_id"], new_key["recruiter"]])
    else:
        new_key_list = []

    app_table = []
    in_progress_table = []
    accepted_table = []
    rejected_table = []
    for app in g.mongo.db.applications.find({"owner": {"$exists": True}}):
        row = [app["_id"], app["character_name"], app.get("submitted", False), app.get("recruiter"),
               app.get("met_recruiter", False), app.get("status", "Not Submitted"), app.get("reason")]
        app_table.append(row)
        if app.get("status") == "Accepted":
            accepted_table.append(row)
        elif app.get("status") == "Rejected":
            rejected_table.append(row)
        else:
            in_progress_table.append(row)
    return render_template("recruitment_apps.html", app_table=app_table, in_progress_table=in_progress_table,
                           accepted_table=accepted_table, rejected_table=rejected_table, restricted=restricted,
                           new_key_list=new_key_list)
