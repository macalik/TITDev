import json
import itertools


from flask import Blueprint, render_template, g

from views.auth import requires_sso
from helpers import caches

security = Blueprint("security", __name__, template_folder="templates")


@security.route("/")
@requires_sso("security_officer")
def home():
    with open("configs/base.json", "r") as base_config_file:
        base_config = json.load(base_config_file)

    id_to_name = {}
    for user in g.mongo.db.users.find({"corporation_id": base_config["corporation_id"]}):
        id_to_name[user["_id"]] = user["character_name"]

    api_table = []
    characters = set()
    for api_user in g.mongo.db.api_keys.find({"_id": {"$in": list(id_to_name.keys())}}):
        user_characters = [(x["character_name"], x["key_id"], x.get("valid", True)) for x in api_user["keys"]]
        api_table.append(list(itertools.chain(*[
            [id_to_name[api_user["_id"]]],
            user_characters
        ])))
        [characters.add(y[0]) for y in user_characters]

    print(api_table)
    print(characters)
    print("Kazuki Ishikawa" in characters)

    caches.security_characters()

    return render_template("base.html")
