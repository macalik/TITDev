import json
import os

from flask import Blueprint, render_template, g, request, session
from bson.objectid import ObjectId

from helpers import caches, conversions
from views.auth import requires_sso, auth_check

security_dashboard = Blueprint("security_dashboard", __name__, template_folder="templates")

@security_dashboard.route("/", methods=["GET", "POST"])
@requires_sso("user_admin")

def load():
    # call cache
    caches.wallet_journal()

    pilot_list = []
    # All Users List
    for pilot in g.mongo.db.users.find():
        pilot_list.append(pilot)

    pilot_wallet_transactions = []
    for p_balance in g.mongo.db.wallet_journal.find({"ref_type_id":10}):
        pilot_wallet_transactions.append(p_balance)

    # print(pilot_wallet_transactions)

    return render_template("security/security.html", pilot_list=pilot_list, pilot_wallet_transactions=pilot_wallet_transactions)