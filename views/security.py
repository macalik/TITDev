import json
from flask import Blueprint, render_template

from helpers import caches, conversions
from views.auth import requires_sso, auth_check

security = Blueprint("security", __name__, template_folder="templates")

@security.route("/")
@requires_sso(None)

def home():
    return render_template("security.html")