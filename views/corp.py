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

    return render_template("corp.html", away_from_eve=away_from_eve, invoice_table=invoice_table)
