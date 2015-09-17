import json
import os

from flask import Blueprint, render_template

from helpers import caches, conversions
from views.auth import requires_sso, auth_check

security = Blueprint("security", __name__, template_folder="templates")

@security.route("/")
@requires_sso("user_admin")

def load():
    return render_template("security/security.html")