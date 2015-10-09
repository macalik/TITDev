import json
import os

from flask import Blueprint, render_template, g, request, session

from helpers import caches, api
from views.auth import requires_sso, auth_check

api_manager = Blueprint("api_manager", __name__, template_folder="templates")

@api_manager.route("/", methods=["GET", "POST"])
@requires_sso("user_admin")

def load():

    # if post call api helper
    if request.method == "POST":
        api.add_api(request)

    return render_template("security/api_manager.html")