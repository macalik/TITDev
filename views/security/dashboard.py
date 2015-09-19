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
    caches.character_balances()

    pilot_list = []
    # All Users List
    for pilot in g.mongo.db.users.find():
        pilot_list.append(pilot)

    pilot_balances = []
    for p_balance in g.mongo.db.char_balances.find():
        pilot_balances.append(p_balance)

    print(pilot_balances)

    return render_template("security/security.html", pilot_list=pilot_list, pilot_balances=pilot_balances)