import json
import datetime

from flask import Blueprint, render_template, g, session
from bson.objectid import ObjectId

from views.auth import requires_sso

corp = Blueprint("corp", __name__, template_folder="templates")


@corp.route("/")
@requires_sso("corporation")
def home():
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    # Missing APIs
    missing_apis = []
    corp_ids = []
    api_characters = set()
    # Determine accounts in corp
    for user_info in g.mongo.db.users.find({"corporation_id": base_config["corporation_id"]}):
        if g.mongo.db.security_characters.find_one({"_id": user_info["character_id"]}):
            corp_ids.append(user_info["_id"])
    # Determine characters with an api
    for api_user in g.mongo.db.api_keys.find({"_id": {"$in": corp_ids}}):
        for key in api_user["keys"]:
            api_characters.add(key["character_name"])
    # Determine characters in corp without an api from a corp account
    for corp_character in g.mongo.db.security_characters.find():
        if corp_character["name"] not in api_characters:
            missing_apis.append(corp_character["name"])

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
        invoice_table.append([invoice_color, invoice_timestamp, invoice["_id"], invoice["jf_end"],
                              "{:,.02f}".format(invoice["order_total"]), invoice.get("marketeer"), invoice_status])

    # Away from EVE
    db_vacation = g.mongo.db.personals.find({"vacation": {"$exists": True}})
    away_from_eve = []
    for character in db_vacation:
        if character["corporation_id"] == base_config["corporation_id"]:
            away_from_eve.append([character["character_name"], character["vacation"], character["vacation_date"]])

    return render_template("corp.html", away_from_eve=away_from_eve, invoice_table=invoice_table,
                           missing_apis=missing_apis)
