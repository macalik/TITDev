import json
import datetime

from flask import Blueprint, render_template, session, request, g
from bson.objectid import ObjectId

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
            g.mongo.db.api_keys.update({"_id": session["CharacterOwnerHash"]},
                                       {
                                           "$pull": {
                                               "keys": {"key_id": int(request.form.get("key_id"))}
                                           }
                                       })
        elif request.form.get("action") == "email":
            g.mongo.db.users.update({"_id": session["CharacterOwnerHash"]},
                                    {
                                        "$set": {
                                            "email": request.form.get("email", "").strip()
                                        }
                                    })
        elif request.form.get("action") == "slack":
            g.mongo.db.users.update({"_id": session["CharacterOwnerHash"]},
                                    {
                                        "$set": {
                                            "slack": request.form.get("slack", "").strip()
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
                 db_user_info["alliance_name"], db_user_info.get("email"), db_user_info.get("slack")]

    # Images
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)
    image_list = [base_config["image_server"] + "Character/" + str(db_user_info["character_id"]) + "_256.jpg",
                  base_config["image_server"] + "Corporation/" + str(db_user_info["corporation_id"]) + "_128.png",
                  base_config["image_server"] + "Alliance/" + str(db_user_info["alliance_id"]) + "_128.png"]

    access_mask = base_config["access_mask"]

    # Away from EVE
    if request.method == "GET":
        if request.args.get("action") == "enable":
            g.mongo.db.personals.update({"_id": session["CharacterOwnerHash"],
                                         "character_name": db_user_info["character_name"],
                                         "character_id": db_user_info["character_id"]}, {
                "$set":
                    {
                        "corporation_id": db_user_info["corporation_id"],
                        "vacation": request.args.get("text"),
                        "vacation_date": request.args.get("date")
                    }
            }, upsert=True)
        elif request.args.get("action") == "disable":
            g.mongo.db.personals.update({"_id": session["CharacterOwnerHash"],
                                         "character_name": db_user_info["character_name"],
                                         "character_id": db_user_info["character_id"]}, {
                "$unset":
                    {
                        "vacation": request.args.get("text"),
                        "vacation_date": request.args.get("date")
                    }
            })

    db_personal = g.mongo.db.personals.find_one({"_id": session["CharacterOwnerHash"], "vacation": {"$exists": True}})
    if db_personal:
        vacation = True
        vacation_text = db_personal["vacation"]
        vacation_date = db_personal["vacation_date"]
    else:
        vacation = False
        vacation_text = ""
        vacation_date = ""

    keys = request.args.get("keys")
    if keys:
        keys = keys.split(",")

    # Personal Invoices
    one_month_oid = ObjectId.from_datetime(datetime.datetime.today() - datetime.timedelta(30))
    invoice_table = []
    for invoice in g.mongo.db.invoices.find({"_id": {"$gt": one_month_oid}, "user": session["CharacterOwnerHash"]}):
        invoice_status = invoice.get("status", "Not Processed")
        invoice_timestamp = ObjectId(invoice["_id"]).generation_time.strftime("%Y-%m-%d %H:%M:%S")
        invoice_color = ""
        if invoice_status == "Shipping - Completed":
            invoice_color = "primary"
        elif invoice_status == "Processing" or invoice_status.startswith("Shipping"):
            invoice_color = "warning"
        elif invoice_status in ["Failed", "Rejected"]:
            invoice_color = "danger"
        elif invoice_status == "Completed":
            invoice_color = "success"
        invoice_table.append([invoice_color, invoice_timestamp, invoice["_id"], invoice["jf_end"],
                              "{:,.02f}".format(invoice["order_total"]), invoice.get("marketeer"), invoice_status])

    return render_template("account.html", error_list=error_list, given_roles=given_roles,
                           associated_keys=associated_keys, user_info=user_info, image_list=image_list,
                           vacation=vacation, vacation_text=vacation_text, keys=keys, access_mask=access_mask,
                           vacation_date=vacation_date, invoice_table=invoice_table)
