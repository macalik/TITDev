import random
import string
import json
import os
import base64
import time

from flask import redirect, request, Blueprint, abort, render_template, g
import requests

auth_blueprint = Blueprint("auth", __name__, template_folder="templates")

state = "".join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(18))

if os.environ.get("HEROKU"):
    secrets = {
        "client_id": os.environ["client_id"],
        "secret_key": os.environ["secret_key"]
    }
else:
    with open("../Other-Secrets/TITDev.json") as secrets_file:
        secrets = json.load(secrets_file)


@auth_blueprint.route("/")
def sso_redirect():
    return redirect("https://login.eveonline.com/oauth/authorize" +
                    "?response_type=code" +
                    "&redirect_uri=http://localhost:5000/login/sso" +
                    "&client_id=" + secrets["client_id"] +
                    "&scope=publicData" +
                    "&state=" + state)


@auth_blueprint.route("/sso")
def sso_response():
    if request.args.get("state") == state:
        code = request.args.get("code")

        auth_headers = {
            "Authorization": "Basic " + str(base64.b64encode(
                bytes(secrets["client_id"] + ":" + secrets["secret_key"], "utf8")))[2:-1],
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "login.eveonline.com"
        }

        auth_payload = {
            "grant_type": "authorization_code",
            "code": code
        }

        auth_response = requests.post("https://login.eveonline.com/oauth/token",
                                      data=auth_payload, headers=auth_headers)

        try:
            auth_token = json.loads(auth_response.text)
        except ValueError:
            auth_token = None
            abort(400)

        g.mongo.db.users.insert({"access_token": auth_token["access_token"],
                                 "expiration": time.time() + int(auth_token["expires_in"]),
                                 "refresh_token": auth_token["refresh_token"]})

        return render_template("output.html", output=auth_response.text)

    else:
        abort(400)
