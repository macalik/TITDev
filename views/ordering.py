"""
main.py
-------
from views.{page} import {Blueprint()}
app.register_blueprint({Blueprint()}, url_prefix="/{view}")
"""

from flask import Blueprint, render_template

from views.auth import requires_sso

view = Blueprint("jf", __name__, template_folder="templates")


@view.route("/")
@requires_sso(None)
def home():
    return render_template("base.html")
