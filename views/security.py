import json
import os

from flask import Blueprint, render_template, g, request, session
from bson.objectid import ObjectId

from helpers import caches, conversions
from views.auth import requires_sso, auth_check

security = Blueprint("security", __name__, template_folder="templates")

@security.route("/")
@requires_sso("user_admin")

def load():

    pilot_list = []
    # All Users List
    for pilot in g.mongo.db.characters.find():
       pilot_list.append(pilot["_id"])


    return render_template("security/security.html", pilot_list=pilot_list)