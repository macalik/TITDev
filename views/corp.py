import json

from flask import Blueprint, render_template, g

from views.auth import requires_sso

corp = Blueprint("corp", __name__, template_folder="templates")


@corp.route("/")
@requires_sso("corporation")
def home():
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    db_vacation = g.mongo.db.personals.find({"vacation": {"$exists": True}})
    away_from_eve = []
    for character in db_vacation:
        if character["corporation_id"] == base_config["corporation_id"]:
            away_from_eve.append([character["character_name"], character["vacation"]])

    return render_template("corp.html", away_from_eve=away_from_eve)
